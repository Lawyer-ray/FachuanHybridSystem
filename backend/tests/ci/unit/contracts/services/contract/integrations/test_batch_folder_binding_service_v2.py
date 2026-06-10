"""Tests for ContractBatchFolderBindingService."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.models.enums import CaseType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**overrides: Any) -> Any:
    from apps.contracts.services.contract.integrations.batch_folder_binding_service import (
        ContractBatchFolderBindingService,
    )
    defaults: dict[str, Any] = {
        "folder_binding_service": MagicMock(),
    }
    defaults.update(overrides)
    return ContractBatchFolderBindingService(**defaults)


def _make_contract(*, contract_id: int = 1, name: str = "合同A", case_type: str = "litigation",
                   filing_number: str = "", oa_case_number: str = "", **extra: Any) -> MagicMock:
    c = MagicMock()
    c.id = contract_id
    c.name = name
    c.case_type = case_type
    c.filing_number = filing_number
    c.law_firm_oa_case_number = oa_case_number
    for k, v in extra.items():
        setattr(c, k, v)
    c.cases.all.return_value = []
    return c


def _make_candidate(*, name: str = "folder", path: str = "/root/folder") -> dict[str, str]:
    return {"name": name, "path": path}


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_strips_and_lowercases(self):
        svc = _make_service()
        assert svc._normalize_text("  Hello World  ") == "hello world"

    def test_empty_returns_empty(self):
        svc = _make_service()
        assert svc._normalize_text("") == ""
        assert svc._normalize_text(None) == ""

    def test_strips_punctuation(self):
        svc = _make_service()
        result = svc._normalize_text("公司（北京）有限公司")
        assert "（" not in result
        assert "）" not in result

    def test_strips_leading_date(self):
        svc = _make_service()
        result = svc._normalize_text("2026-01-15 合同")
        assert result == "合同"

    def test_strips_leading_labels(self):
        svc = _make_service()
        result = svc._normalize_text("[ABC] [DEF] 合同")
        assert result == "合同"


# ---------------------------------------------------------------------------
# _normalize_alias
# ---------------------------------------------------------------------------

class TestNormalizeAlias:
    def test_removes_company_suffixes(self):
        svc = _make_service()
        result = svc._normalize_alias("北京科技有限公司")
        assert "有限公司" not in result
        assert "科技" in result

    def test_removes_case_keywords(self):
        svc = _make_service()
        result = svc._normalize_alias("案件")
        assert result == ""

    def test_empty_returns_empty(self):
        svc = _make_service()
        assert svc._normalize_alias("") == ""


# ---------------------------------------------------------------------------
# _strip_leading_date
# ---------------------------------------------------------------------------

class TestStripLeadingDate:
    def test_strips_date_prefix(self):
        svc = _make_service()
        assert svc._strip_leading_date("2026.01.15 - 合同") == "合同"

    def test_no_date_unchanged(self):
        svc = _make_service()
        assert svc._strip_leading_date("合同A") == "合同A"


# ---------------------------------------------------------------------------
# _strip_leading_labels
# ---------------------------------------------------------------------------

class TestStripLeadingLabels:
    def test_strips_bracket_labels(self):
        svc = _make_service()
        assert svc._strip_leading_labels("[ABC] [DEF] text") == "text"

    def test_no_labels_unchanged(self):
        svc = _make_service()
        assert svc._strip_leading_labels("text") == "text"


# ---------------------------------------------------------------------------
# _looks_like_number
# ---------------------------------------------------------------------------

class TestLooksLikeNumber:
    def test_has_digit(self):
        svc = _make_service()
        assert svc._looks_like_number("abc123") is True

    def test_no_digit(self):
        svc = _make_service()
        assert svc._looks_like_number("abc") is False

    def test_empty(self):
        svc = _make_service()
        assert svc._looks_like_number("") is False


# ---------------------------------------------------------------------------
# _sequence_ratio
# ---------------------------------------------------------------------------

class TestSequenceRatio:
    def test_identical(self):
        svc = _make_service()
        assert svc._sequence_ratio("abc", "abc") == 1.0

    def test_empty_returns_zero(self):
        svc = _make_service()
        assert svc._sequence_ratio("", "abc") == 0.0
        assert svc._sequence_ratio("abc", "") == 0.0


# ---------------------------------------------------------------------------
# _is_non_contract_dir
# ---------------------------------------------------------------------------

class TestIsNonContractDir:
    def test_returns_true_for_keyword(self):
        svc = _make_service()
        assert svc._is_non_contract_dir("未成交") is True
        assert svc._is_non_contract_dir("归档") is True
        assert svc._is_non_contract_dir("模板") is True

    def test_returns_false_for_normal(self):
        svc = _make_service()
        assert svc._is_non_contract_dir("合同A") is False


# ---------------------------------------------------------------------------
# _score_candidate
# ---------------------------------------------------------------------------

class TestScoreCandidate:
    def test_exact_match(self):
        svc = _make_service()
        targets = [("合同A", "合同名称", 1.0)]
        result = svc._score_candidate(candidate_name="合同A", targets=targets)
        assert result["score"] >= 0.9

    def test_partial_match(self):
        svc = _make_service()
        targets = [("北京科技有限公司", "合同名称", 1.0)]
        result = svc._score_candidate(candidate_name="北京", targets=targets)
        assert 0.0 < result["score"] < 1.0

    def test_empty_targets(self):
        svc = _make_service()
        result = svc._score_candidate(candidate_name="合同A", targets=[])
        assert result["score"] == 0.0

    def test_number_bonus(self):
        svc = _make_service()
        targets = [("12345", "合同编号", 1.0)]
        result = svc._score_candidate(candidate_name="12345", targets=targets)
        assert result["score"] >= 0.3


# ---------------------------------------------------------------------------
# _recommend_folder
# ---------------------------------------------------------------------------

class TestRecommendFolder:
    def test_returns_no_match_when_empty(self):
        svc = _make_service()
        result = svc._recommend_folder(
            contract_name="", contract_filing_number="", oa_case_number="",
            case_names=[], case_filing_numbers=[], candidates=[]
        )
        assert result["auto_selected"] is False
        assert result["confidence"] == 0.0

    def test_returns_recommendation_with_match(self):
        svc = _make_service()
        candidates = [_make_candidate(name="合同A", path="/root/合同A")]
        result = svc._recommend_folder(
            contract_name="合同A", contract_filing_number="", oa_case_number="",
            case_names=[], case_filing_numbers=[], candidates=candidates
        )
        assert result["recommended_folder_path"] == "/root/合同A"
        assert result["confidence"] > 0.7

    def test_non_contract_dir_penalized(self):
        svc = _make_service()
        candidates = [_make_candidate(name="未成交", path="/root/未成交")]
        result = svc._recommend_folder(
            contract_name="未成交", contract_filing_number="", oa_case_number="",
            case_names=[], case_filing_numbers=[], candidates=candidates
        )
        assert result["confidence"] <= 0.75


# ---------------------------------------------------------------------------
# _ensure_accessible_directory
# ---------------------------------------------------------------------------

class TestEnsureAccessibleDirectory:
    def test_returns_path_when_exists(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.is_dir.return_value = True
            mock_path.expanduser.return_value.resolve.return_value = mock_path
            MockPath.return_value = mock_path
            result = svc._ensure_accessible_directory("/test")
            assert result is mock_path

    def test_raises_when_not_exists(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_path.expanduser.return_value.resolve.return_value = mock_path
            MockPath.return_value = mock_path
            from apps.core.exceptions import ValidationException
            with pytest.raises(ValidationException, match="目录不可访问"):
                svc._ensure_accessible_directory("/nonexistent")


# ---------------------------------------------------------------------------
# _validate_selected_folder
# ---------------------------------------------------------------------------

class TestValidateSelectedFolder:
    def test_valid_first_level_child(self):
        svc = _make_service()
        root = MagicMock()
        root.as_posix.return_value = "/root"
        target = MagicMock()
        target.as_posix.return_value = "/root/child"
        target.relative_to.return_value = target
        target.parent = root
        with patch.object(svc, "_ensure_accessible_directory") as mock_ensure:
            mock_ensure.side_effect = [root, target]
            result = svc._validate_selected_folder(root_path="/root", selected_folder_path="/root/child")
            assert result is target

    def test_raises_when_not_first_level(self):
        svc = _make_service()
        root = MagicMock()
        root.as_posix.return_value = "/root"
        target = MagicMock()
        target.as_posix.return_value = "/root/a/b"
        target.relative_to.return_value = target
        target.parent = MagicMock()
        target.parent.as_posix.return_value = "/root/a"
        with patch.object(svc, "_ensure_accessible_directory") as mock_ensure:
            mock_ensure.side_effect = [root, target]
            from apps.core.exceptions import ValidationException
            with pytest.raises(ValidationException, match="一级子文件夹"):
                svc._validate_selected_folder(root_path="/root", selected_folder_path="/root/a/b")

    def test_cloud_valid_first_level(self):
        svc = _make_service()
        result = svc._validate_selected_folder(
            root_path="/contracts", selected_folder_path="/contracts/case1", storage_type="s3"
        )
        assert result == "/contracts/case1"

    def test_cloud_rejects_not_child(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="不在根目录"):
            svc._validate_selected_folder(
                root_path="/contracts", selected_folder_path="/other/path", storage_type="s3"
            )

    def test_cloud_rejects_deep_nesting(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="一级子文件夹"):
            svc._validate_selected_folder(
                root_path="/contracts", selected_folder_path="/contracts/a/b", storage_type="webdav"
            )


# ---------------------------------------------------------------------------
# _list_local_first_level_dirs
# ---------------------------------------------------------------------------

class TestListLocalFirstLevelDirs:
    def test_returns_sorted_dicts(self):
        svc = _make_service()
        d1 = type("Dir", (), {"name": "b_folder", "is_dir": lambda s: True, "resolve": lambda s: s, "as_posix": lambda s: "/root/b_folder"})()
        d2 = type("Dir", (), {"name": "a_folder", "is_dir": lambda s: True, "resolve": lambda s: s, "as_posix": lambda s: "/root/a_folder"})()
        d3 = type("Dir", (), {"name": ".hidden", "is_dir": lambda s: True, "resolve": lambda s: s, "as_posix": lambda s: ""})()
        d4 = type("Dir", (), {"name": "file.txt", "is_dir": lambda s: False, "resolve": lambda s: s, "as_posix": lambda s: ""})()
        with patch.object(svc, "_ensure_accessible_directory") as mock_ensure:
            mock_root = MagicMock()
            mock_root.iterdir.return_value = [d1, d2, d3, d4]
            mock_ensure.return_value = mock_root
            result = svc._list_local_first_level_dirs("/root")
            assert len(result) == 2
            assert result[0]["name"] == "a_folder"
            assert result[1]["name"] == "b_folder"


# ---------------------------------------------------------------------------
# list_unbound_case_type_cards
# ---------------------------------------------------------------------------

class TestListUnboundCaseTypeCards:
    def test_returns_cards(self):
        svc = _make_service()
        data = [{"case_type": "litigation", "unbound_count": 5}]
        def _iter_factory():
            return iter(list(data))
        chain = MagicMock()
        chain.__iter__ = MagicMock(side_effect=_iter_factory)
        chain.filter.return_value = chain
        chain.exclude.return_value = chain
        chain.values.return_value = chain
        chain.annotate.return_value = chain
        chain.order_by.return_value = chain
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Contract") as MockContract:
            MockContract.objects.filter.return_value = chain
            with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.ContractTypeFolderRootPreset") as MockPreset:
                MockPreset.objects.filter.return_value = []
                result = svc.list_unbound_case_type_cards()
                assert len(result) == 1
                assert result[0]["case_type"] == "litigation"
                assert result[0]["unbound_count"] == 5
                assert result[0]["storage_type"] == "local"


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

class TestPreview:
    def test_empty_input(self):
        svc = _make_service()
        result = svc.preview(case_type_roots=[])
        assert result["items"] == []
        assert result["summary"]["total_contracts"] == 0

    def test_skips_empty_case_type(self):
        svc = _make_service()
        result = svc.preview(case_type_roots=[{"case_type": "", "root_path": "/x"}])
        assert len(result["items"]) == 0


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

class TestSave:
    def test_saves_root_presets(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.only.return_value = []
            with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.ContractTypeFolderRootPreset") as MockPreset:
                MockPreset.objects.update_or_create.return_value = (MagicMock(), True)
                with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.transaction"):
                    result = svc.save(
                        case_type_roots=[{"case_type": "litigation", "root_path": ""}],
                        contract_selections=[],
                    )
                    assert result["bound_count"] == 0

    def test_skips_when_no_apply(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.only.return_value = []
            with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.ContractTypeFolderRootPreset") as MockPreset:
                MockPreset.objects.update_or_create.return_value = (MagicMock(), True)
                with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.transaction"):
                    result = svc.save(
                        case_type_roots=[],
                        contract_selections=[{"contract_id": 1, "apply": False}],
                    )
                    assert result["skipped_count"] == 1


# ---------------------------------------------------------------------------
# open_folder
# ---------------------------------------------------------------------------

class TestOpenFolder:
    def test_calls_subprocess_runner(self, tmp_path):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.SubprocessRunner") as MockRunner, \
             patch.object(svc, "_validate_selected_folder") as mock_validate:
            mock_validate.return_value = tmp_path / "target"
            svc.open_folder(root_path="/root", folder_path="/root/sub")
            MockRunner.return_value.run.assert_called_once()

    def test_cloud_skips_open(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.SubprocessRunner") as MockRunner:
            svc.open_folder(root_path="/root", folder_path="/root/sub", storage_type="webdav")
            MockRunner.assert_not_called()


# ---------------------------------------------------------------------------
# AUTO_SCORE_THRESHOLD and constants
# ---------------------------------------------------------------------------

class TestClassConstants:
    def test_threshold(self):
        from apps.contracts.services.contract.integrations.batch_folder_binding_service import (
            ContractBatchFolderBindingService,
        )
        assert ContractBatchFolderBindingService.AUTO_SCORE_THRESHOLD == 0.72
        assert ContractBatchFolderBindingService.AUTO_SCORE_GAP == 0.08

    def test_non_contract_keywords(self):
        from apps.contracts.services.contract.integrations.batch_folder_binding_service import (
            ContractBatchFolderBindingService,
        )
        assert "未成交" in ContractBatchFolderBindingService.NON_CONTRACT_DIR_KEYWORDS


# ---------------------------------------------------------------------------
# _preview_single_case_type
# ---------------------------------------------------------------------------

class TestPreviewSingleCaseType:
    def test_empty_root_returns_error(self):
        svc = _make_service()
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.prefetch_related.return_value.order_by.return_value = []
            result = svc._preview_single_case_type(case_type="litigation", root_path="")
            assert result["error"] == "请先填写根目录"
            assert result["contract_count"] == 0

    def test_returns_rows_for_contracts(self):
        svc = _make_service()
        contract = _make_contract(name="合同A")
        with patch("apps.contracts.services.contract.integrations.batch_folder_binding_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.prefetch_related.return_value.order_by.return_value = [contract]
            with patch.object(svc, "_list_first_level_dirs_for_storage") as mock_list:
                mock_list.return_value = []
                result = svc._preview_single_case_type(case_type="litigation", root_path="/root")
                assert result["contract_count"] == 1
                assert len(result["rows"]) == 1
                assert result["rows"][0]["contract_id"] == 1
