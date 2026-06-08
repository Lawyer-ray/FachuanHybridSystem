"""Tests for CaseFolderScanService."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from apps.cases.models.folder_scan_session import CaseFolderScanStatus
from apps.cases.services.material.folder_scan_service import CaseFolderScanService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**overrides: Any) -> Any:
    from apps.cases.services.material.folder_scan_service import CaseFolderScanService
    defaults: dict[str, Any] = {
        "scan_service": MagicMock(),
    }
    defaults.update(overrides)
    return CaseFolderScanService(**defaults)


def _make_binding(*, resolved_folder_path: str = "/test/root", storage_type: str = "local",
                  relative_path: str = "sub") -> MagicMock:
    b = MagicMock()
    b.resolved_folder_path = resolved_folder_path
    b.storage_type = storage_type
    b.relative_path = relative_path
    return b


def _make_session(
    *,
    session_id: Any = None,
    case_id: int = 1,
    status: Any = CaseFolderScanStatus.COMPLETED,
    progress: int = 100,
    current_file: str = "",
    result_payload: dict | None = None,
    error_message: str = "",
    started_by_id: int | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = session_id or uuid4()
    s.case_id = case_id
    s.status = status
    s.progress = progress
    s.current_file = current_file
    s.result_payload = result_payload or {"summary": {}, "candidates": [], "scan_scope": {}, "scan_options": {}}
    s.error_message = error_message
    s.started_by_id = started_by_id
    return s


# ---------------------------------------------------------------------------
# _ensure_case_exists
# ---------------------------------------------------------------------------

class TestEnsureCaseExists:
    @patch("apps.cases.services.material.folder_scan_service.Case")
    def test_raises_when_not_found(self, MockCase):
        MockCase.objects.filter.return_value.exists.return_value = False
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            CaseFolderScanService._ensure_case_exists(999)

    @patch("apps.cases.services.material.folder_scan_service.Case")
    def test_passes_when_found(self, MockCase):
        MockCase.objects.filter.return_value.exists.return_value = True
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        CaseFolderScanService._ensure_case_exists(1)


# ---------------------------------------------------------------------------
# _get_accessible_binding
# ---------------------------------------------------------------------------

class TestGetAccessibleBinding:
    @patch("apps.cases.services.material.folder_scan_service.CaseFolderBinding")
    def test_raises_when_no_binding(self, MockBinding):
        MockBinding.objects.filter.return_value.first.return_value = None
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="未绑定文件夹"):
            CaseFolderScanService._get_accessible_binding(1)

    @patch("apps.cases.services.material.folder_scan_service.CaseFolderBinding")
    def test_raises_when_local_folder_inaccessible(self, MockBinding):
        binding = _make_binding(resolved_folder_path="/nonexistent")
        MockBinding.objects.filter.return_value.first.return_value = binding
        with patch("apps.cases.services.material.folder_scan_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            MockPath.return_value = mock_path
            from apps.core.exceptions import ValidationException
            with pytest.raises(ValidationException, match="绑定文件夹不可访问"):
                CaseFolderScanService._get_accessible_binding(1)

    @patch("apps.cases.services.material.folder_scan_service.CaseFolderBinding")
    def test_returns_binding_when_accessible(self, MockBinding):
        binding = _make_binding()
        MockBinding.objects.filter.return_value.first.return_value = binding
        with patch("apps.cases.services.material.folder_scan_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.is_dir.return_value = True
            MockPath.return_value = mock_path
            result = CaseFolderScanService._get_accessible_binding(1)
            assert result is binding


# ---------------------------------------------------------------------------
# _normalize_scan_subfolder
# ---------------------------------------------------------------------------

class TestNormalizeScanSubfolder:
    def test_empty_returns_empty(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("") == ""
        assert svc._normalize_scan_subfolder("  ") == ""

    def test_absolute_path_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="必须使用相对路径"):
            svc._normalize_scan_subfolder("/etc/passwd")

    def test_tilde_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="必须使用相对路径"):
            svc._normalize_scan_subfolder("~/secret")

    def test_windows_drive_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="必须使用相对路径"):
            svc._normalize_scan_subfolder("C:/Windows")

    def test_dotdot_raises(self):
        svc = _make_service()
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="路径非法"):
            svc._normalize_scan_subfolder("a/../b")

    def test_normalizes_slashes(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a/b") == "a/b"

    def test_strips_leading_slash_and_dots(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("./a/./b") == "a/b"

    def test_backslash_to_slash(self):
        svc = _make_service()
        assert svc._normalize_scan_subfolder("a\\b") == "a/b"


# ---------------------------------------------------------------------------
# _resolve_scan_scope
# ---------------------------------------------------------------------------

class TestResolveScanScope:
    def test_local_root_only(self):
        svc = _make_service()
        with patch("apps.cases.services.material.folder_scan_service.Path") as MockPath:
            mock_path = MagicMock()
            mock_path.expanduser.return_value.resolve.return_value = MagicMock(
                as_posix=MagicMock(return_value="/root")
            )
            MockPath.return_value = mock_path
            result = svc._resolve_scan_scope("/root", "")
            assert result["scan_folder"] == "/root"


# ---------------------------------------------------------------------------
# _extract_scan_subfolder
# ---------------------------------------------------------------------------

class TestExtractScanSubfolder:
    def test_extracts_from_payload(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "sub"}}
        assert svc._extract_scan_subfolder(payload) == "sub"

    def test_returns_empty_for_none(self):
        svc = _make_service()
        assert svc._extract_scan_subfolder(None) == ""


# ---------------------------------------------------------------------------
# _extract_enable_recognition
# ---------------------------------------------------------------------------

class TestExtractEnableRecognition:
    def test_returns_true_when_not_set(self):
        svc = _make_service()
        assert svc._extract_enable_recognition({}) is True

    def test_returns_true_when_enabled(self):
        svc = _make_service()
        assert svc._extract_enable_recognition({"scan_options": {"enable_recognition": True}}) is True

    def test_returns_false_when_disabled(self):
        svc = _make_service()
        assert svc._extract_enable_recognition({"scan_options": {"enable_recognition": False}}) is False


# ---------------------------------------------------------------------------
# _is_within_root
# ---------------------------------------------------------------------------

class TestIsWithinRoot:
    def test_within_root(self):
        svc = _make_service()
        root = MagicMock()
        root.as_posix.return_value = "/root"
        target = MagicMock()
        target.as_posix.return_value = "/root/sub"
        with patch("apps.cases.services.material.folder_scan_service.os.path.commonpath", return_value="/root"):
            assert svc._is_within_root(root, target) is True

    def test_outside_root(self):
        svc = _make_service()
        root = MagicMock()
        root.as_posix.return_value = "/root"
        target = MagicMock()
        target.as_posix.return_value = "/other"
        with patch("apps.cases.services.material.folder_scan_service.os.path.commonpath", return_value="/"):
            assert svc._is_within_root(root, target) is False


# ---------------------------------------------------------------------------
# _to_int
# ---------------------------------------------------------------------------

class TestToInt:
    def test_valid_int(self):
        assert CaseFolderScanService._to_int("42") == 42

    def test_zero_returns_none(self):
        assert CaseFolderScanService._to_int("0") is None

    def test_negative_returns_none(self):
        assert CaseFolderScanService._to_int("-1") is None

    def test_none_returns_none(self):
        assert CaseFolderScanService._to_int(None) is None

    def test_non_numeric_returns_none(self):
        assert CaseFolderScanService._to_int("abc") is None


# ---------------------------------------------------------------------------
# _contains_force_our_party_folder_keyword
# ---------------------------------------------------------------------------

class TestContainsForceOurPartyFolderKeyword:
    def test_returns_true_for_keyword(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("立案材料") is True
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("递交给法院的资料") is True
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("提交给法院的资料") is True

    def test_returns_false_for_normal(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("普通目录") is False

    def test_empty_returns_false(self):
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("") is False


# ---------------------------------------------------------------------------
# _should_force_our_party_for_filing_materials
# ---------------------------------------------------------------------------

class TestShouldForceOurPartyForFiling:
    def test_true_when_scan_subfolder_matches(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "立案材料"}}
        assert svc._should_force_our_party_for_filing_materials(payload) is True

    def test_true_when_scan_folder_matches(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_folder": "/root/递交给法院的资料"}}
        assert svc._should_force_our_party_for_filing_materials(payload) is True

    def test_false_when_no_match(self):
        svc = _make_service()
        payload = {"scan_scope": {"scan_subfolder": "普通目录"}}
        assert svc._should_force_our_party_for_filing_materials(payload) is False


# ---------------------------------------------------------------------------
# _should_force_our_party_for_candidate
# ---------------------------------------------------------------------------

class TestShouldForceOurPartyForCandidate:
    def test_true_when_source_path_matches(self):
        svc = _make_service()
        candidate = {"source_path": "/root/立案材料/file.pdf"}
        assert svc._should_force_our_party_for_candidate(candidate) is True

    def test_false_when_no_match(self):
        svc = _make_service()
        candidate = {"source_path": "/root/普通目录/file.pdf"}
        assert svc._should_force_our_party_for_candidate(candidate) is False

    def test_false_when_empty(self):
        svc = _make_service()
        assert svc._should_force_our_party_for_candidate(None) is False


# ---------------------------------------------------------------------------
# _normalize_candidates_for_scan_scope
# ---------------------------------------------------------------------------

class TestNormalizeCandidatesForScanScope:
    def test_no_force_when_no_keyword(self):
        svc = _make_service()
        candidates = [{"suggested_category": "party", "reason": ""}]
        payload = {"scan_scope": {"scan_subfolder": "普通目录"}}
        result = svc._normalize_candidates_for_scan_scope(candidates, payload)
        assert result[0].get("suggested_side") is None

    def test_force_our_when_keyword_in_scope(self):
        svc = _make_service()
        candidates = [{"suggested_category": "archive_document", "reason": ""}]
        payload = {"scan_scope": {"scan_subfolder": "立案材料"}}
        result = svc._normalize_candidates_for_scan_scope(candidates, payload)
        assert result[0]["suggested_category"] == "party"
        assert result[0]["suggested_side"] == "our"
        assert result[0]["reason"] != ""

    def test_empty_candidates(self):
        svc = _make_service()
        result = svc._normalize_candidates_for_scan_scope([], None)
        assert result == []


# ---------------------------------------------------------------------------
# _build_classification_context
# ---------------------------------------------------------------------------

class TestBuildClassificationContext:
    def test_groups_parties_by_our_flag(self):
        svc = _make_service()
        c_our = MagicMock()
        c_our.id = 10
        c_our.name = "张三"
        c_our.is_our_client = True
        p_our = MagicMock()
        p_our.id = 1
        p_our.client = c_our

        c_opp = MagicMock()
        c_opp.id = 20
        c_opp.name = "李四"
        c_opp.is_our_client = False
        p_opp = MagicMock()
        p_opp.id = 2
        p_opp.client = c_opp

        auth = MagicMock()
        auth.id = 100

        case = MagicMock()
        case.parties.all.return_value = [p_our, p_opp]
        case.supervising_authorities.all.return_value = [auth]

        result = svc._build_classification_context(case)
        assert result["our_party_ids"] == [1]
        assert result["opponent_party_ids"] == [2]
        assert result["our_party_names"] == ["张三"]
        assert result["opponent_party_names"] == ["李四"]
        assert result["supervising_authority_ids"] == [100]
        assert result["primary_supervising_authority_id"] == 100

    def test_empty_authority(self):
        svc = _make_service()
        case = MagicMock()
        case.parties.all.return_value = []
        case.supervising_authorities.all.return_value = []
        result = svc._build_classification_context(case)
        assert result["primary_supervising_authority_id"] is None


# ---------------------------------------------------------------------------
# _make_provider_for_binding
# ---------------------------------------------------------------------------

class TestMakeProviderForBinding:
    def test_returns_none_for_local(self):
        svc = _make_service()
        binding = _make_binding(storage_type="local")
        assert svc._make_provider_for_binding(binding) is None


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

class TestGetSession:
    def test_returns_session(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = _make_service()
        s = _make_session()
        with patch("apps.cases.services.material.folder_scan_service.CaseFolderScanSession") as MockSession:
            MockSession.objects.get.return_value = s
            result = svc.get_session(case_id=1, session_id=s.id)
            assert result is s

    def test_raises_not_found(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = _make_service()
        MockSessionCls = MagicMock()
        MockSessionCls.DoesNotExist = type("DoesNotExist", (Exception,), {})
        with patch("apps.cases.services.material.folder_scan_service.CaseFolderScanSession", MockSessionCls):
            MockSessionCls.objects.get.side_effect = MockSessionCls.DoesNotExist
            from apps.core.exceptions import NotFoundError
            with pytest.raises(NotFoundError):
                svc.get_session(case_id=1, session_id=uuid4())


# ---------------------------------------------------------------------------
# build_status_payload
# ---------------------------------------------------------------------------

class TestBuildStatusPayload:
    def test_builds_payload(self):
        session = _make_session(
            status=CaseFolderScanStatus.COMPLETED,
            progress=100,
            result_payload={
                "summary": {"total_files": 5, "deduped_files": 3, "classified_files": 4},
                "candidates": [],
                "scan_scope": {"scan_subfolder": "sub"},
                "scan_options": {"enable_recognition": True},
            },
        )
        svc = _make_service()
        result = svc.build_status_payload(session=session)
        assert result["status"] == CaseFolderScanStatus.COMPLETED
        assert result["summary"]["total_files"] == 5
        assert result["scan_subfolder"] == "sub"
        assert result["enable_recognition"] is True

    def test_handles_none_payload(self):
        session = _make_session(result_payload=None)
        session.result_payload = None
        svc = _make_service()
        result = svc.build_status_payload(session=session)
        assert result["candidates"] == []


# ---------------------------------------------------------------------------
# run_case_folder_scan_task (module function)
# ---------------------------------------------------------------------------

class TestRunCaseFolderScanTask:
    def test_calls_service(self):
        from apps.cases.services.material.folder_scan_service import run_case_folder_scan_task
        with patch("apps.cases.services.material.folder_scan_service.CaseFolderScanService") as MockSvc:
            run_case_folder_scan_task("test-id")
            MockSvc.return_value.run_scan_task.assert_called_once_with(session_id="test-id")


# ---------------------------------------------------------------------------
# list_scan_subfolders (local)
# ---------------------------------------------------------------------------

class TestListScanSubfoldersLocal:
    def test_lists_subfolders(self):
        binding = _make_binding(resolved_folder_path="/root")
        svc = _make_service()
        svc._ensure_case_exists = MagicMock()
        svc._get_accessible_binding = MagicMock(return_value=binding)
        with patch("apps.cases.services.material.folder_scan_service.Path") as MockPath, \
             patch("apps.cases.services.material.folder_scan_service.os.path.commonpath", return_value="/root"):
            mock_root = MagicMock()
            child1 = MagicMock()
            child1.name = "folder_a"
            child1.is_dir.return_value = True
            child1.resolve.return_value = child1
            child2 = MagicMock()
            child2.name = "folder_b"
            child2.is_dir.return_value = True
            child2.resolve.return_value = child2
            mock_file = MagicMock()
            mock_file.name = "file.pdf"
            mock_file.is_dir.return_value = False
            mock_root.iterdir.return_value = [child1, child2, mock_file]
            mock_root.expanduser.return_value.resolve.return_value = mock_root
            mock_root.as_posix.return_value = "/root"
            MockPath.return_value = mock_root
            result = svc.list_scan_subfolders(case_id=1)
            assert len(result["subfolders"]) == 2
            assert result["root_path"] == "/root"

    def test_skips_hidden_folders(self):
        binding = _make_binding(resolved_folder_path="/root")
        svc = _make_service()
        svc._ensure_case_exists = MagicMock()
        svc._get_accessible_binding = MagicMock(return_value=binding)
        with patch("apps.cases.services.material.folder_scan_service.Path") as MockPath, \
             patch("apps.cases.services.material.folder_scan_service.os.path.commonpath", return_value="/root"):
            mock_root = MagicMock()
            hidden = MagicMock()
            hidden.name = ".hidden"
            hidden.is_dir.return_value = True
            visible = MagicMock()
            visible.name = "visible"
            visible.is_dir.return_value = True
            visible.resolve.return_value = visible
            mock_root.iterdir.return_value = [hidden, visible]
            mock_root.expanduser.return_value.resolve.return_value = mock_root
            mock_root.as_posix.return_value = "/root"
            MockPath.return_value = mock_root
            result = svc.list_scan_subfolders(case_id=1)
            assert len(result["subfolders"]) == 1
            assert result["subfolders"][0]["display_name"] == "visible"


# ---------------------------------------------------------------------------
# _try_repair_binding_path
# ---------------------------------------------------------------------------

class TestTryRepairBindingPath:
    def test_noop_when_no_relative_path(self):
        binding = _make_binding(relative_path="")
        CaseFolderScanService._try_repair_binding_path(binding)

    def test_noop_when_no_case(self):
        binding = _make_binding(relative_path="sub")
        binding.case = MagicMock(side_effect=AttributeError)
        CaseFolderScanService._try_repair_binding_path(binding)

    def test_noop_when_no_contract(self):
        case = MagicMock()
        case.contract_id = None
        binding = _make_binding(relative_path="sub")
        binding.case = case
        CaseFolderScanService._try_repair_binding_path(binding)
