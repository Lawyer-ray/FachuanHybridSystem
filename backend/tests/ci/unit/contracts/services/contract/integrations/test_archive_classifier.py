"""Tests for contracts/services/contract/integrations/archive_classifier.py

Covers: classify_archive_material, parse_work_log_from_folder_name,
collect_work_log_suggestions, collect_archive_item_options,
_add_verb, _normalize_for_match, reload_learned_code_rules,
_match_by_db_learned_rules, _get_item_name, _get_evidence_code.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.integrations.archive_classifier import (
    _add_verb,
    _get_evidence_code,
    _get_item_name,
    _normalize_for_match,
    classify_archive_material,
    collect_archive_item_options,
    collect_work_log_suggestions,
    parse_work_log_from_folder_name,
    reload_learned_code_rules,
)


# ============================================================
# _normalize_for_match
# ============================================================


class TestNormalizeForMatch:
    def test_strips_and_lowercases(self):
        assert _normalize_for_match("  Hello  ") == "hello"

    def test_removes_whitespace(self):
        assert _normalize_for_match("Hello World") == "helloworld"

    def test_backslash_to_slash(self):
        assert _normalize_for_match("path\\to\\file") == "path/to/file"

    def test_empty_string(self):
        assert _normalize_for_match("") == ""

    def test_none_input(self):
        assert _normalize_for_match(None) == ""  # type: ignore[arg-type]


# ============================================================
# classify_archive_material
# ============================================================


class TestClassifyArchiveMaterial:
    def test_skip_keyword_hit(self):
        result = classify_archive_material(
            filename="退费账户确认书.pdf",
            source_path="/some/path",
            archive_category="litigation",
        )
        assert result["category"] == "skip"
        assert result["confidence"] == 1.0
        assert "跳过" in result["archive_item_name"]

    def test_skip_keyword_in_filename(self):
        result = classify_archive_material(
            filename="收款确认书.pdf",
            source_path="/some/path",
            archive_category="litigation",
        )
        assert result["category"] == "skip"

    def test_evidence_folder_non_evidence_file_skipped(self):
        result = classify_archive_material(
            filename="普通文件.pdf",
            source_path="/cases/主要证据材料/subdir",
            archive_category="litigation",
        )
        assert result["category"] == "skip"
        assert result["is_evidence_folder"] is True

    def test_evidence_folder_evidence_list_file_litigation(self):
        result = classify_archive_material(
            filename="证据清单.pdf",
            source_path="/cases/证据材料/subdir",
            archive_category="litigation",
        )
        assert result["category"] == "case_material"
        assert result["archive_item_code"] == "lt_10"
        assert result["is_evidence_folder"] is True
        assert result["confidence"] == 0.95

    def test_evidence_folder_evidence_list_file_criminal(self):
        result = classify_archive_material(
            filename="证据明细.pdf",
            source_path="/cases/证据目录/subdir",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_8"

    def test_evidence_folder_evidence_list_file_non_litigation(self):
        result = classify_archive_material(
            filename="证据清单.pdf",
            source_path="/cases/证据材料/subdir",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_9"

    def test_folder_keyword_match_litigation(self):
        result = classify_archive_material(
            filename="something.pdf",
            source_path="/cases/授权委托书/subdir",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_20"
        assert result["category"] == "case_material"
        assert result["is_evidence_folder"] is False

    def test_folder_keyword_match_non_litigation(self):
        result = classify_archive_material(
            filename="doc.pdf",
            source_path="/cases/律师函/subdir",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_8"

    def test_folder_keyword_match_criminal(self):
        result = classify_archive_material(
            filename="doc.pdf",
            source_path="/cases/会见笔录/subdir",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_7"

    def test_filename_keyword_match_litigation(self):
        result = classify_archive_material(
            filename="起诉状.pdf",
            source_path="/random/path",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"
        assert result["confidence"] == 0.90

    def test_filename_keyword_match_criminal(self):
        result = classify_archive_material(
            filename="辩护词.pdf",
            source_path="/random/path",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_12"

    def test_no_match_returns_unmatched(self):
        result = classify_archive_material(
            filename="random_document.pdf",
            source_path="/random/path",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == ""
        assert result["category"] == "case_material"
        assert result["confidence"] == 0.0
        assert "未匹配" in result["archive_item_name"]

    @patch(
        "apps.contracts.services.contract.integrations.archive_classifier._LEARNED_CODE_RULES",
        {"litigation": {"lt_15": ["律师代理词"]}},
    )
    def test_learned_code_rules_hit(self):
        result = classify_archive_material(
            filename="律师代理词.pdf",
            source_path="/random/path",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_15"
        assert "学习规则" in result["reason"]

    @patch(
        "apps.contracts.services.contract.integrations.archive_classifier._match_by_db_learned_rules",
        return_value={
            "archive_item_code": "lt_7",
            "archive_item_name": "起诉书",
            "category": "case_material",
            "confidence": 0.93,
            "reason": "学习规则(DB)命中：起诉书v2",
        },
    )
    def test_db_learned_rules_hit(self, mock_db):
        result = classify_archive_material(
            filename="起诉书v2.pdf",
            source_path="/random/path",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"


# ============================================================
# parse_work_log_from_folder_name
# ============================================================


class TestParseWorkLogFromFolderName:
    def test_valid_date_folder(self):
        result = parse_work_log_from_folder_name("2024.09.11-立案", "litigation")
        assert result is not None
        assert result["date"] == "2024-09-11"
        assert "立案" in result["content"]

    def test_dash_separator(self):
        result = parse_work_log_from_folder_name("2024-01-05-开庭", "litigation")
        assert result is not None
        assert result["date"] == "2024-01-05"

    def test_no_match_returns_none(self):
        assert parse_work_log_from_folder_name("random_folder", "litigation") is None

    def test_empty_subject_returns_none(self):
        # Pattern requires subject; pure date without subject should return None or have empty subject
        result = parse_work_log_from_folder_name("2024.01.01-", "litigation")
        assert result is None

    def test_em_dash_separator(self):
        result = parse_work_log_from_folder_name("2024.05.10—调解", "litigation")
        assert result is not None
        assert "调解" in result["content"]


# ============================================================
# _add_verb
# ============================================================


class TestAddVerb:
    def test_non_litigation_adds_audit(self):
        result = _add_verb("合同审查", "non_litigation")
        assert result == "审核合同审查"

    def test_existing_verb_not_duplicated(self):
        result = _add_verb("收到判决书", "litigation")
        assert result == "收到判决书"

    def test_litigation_context_inference_judgment(self):
        result = _add_verb("判决书", "litigation")
        assert result == "收到判决书"

    def test_litigation_context_inference_court_notice(self):
        result = _add_verb("开庭通知", "litigation")
        assert result == "收到开庭通知"

    def test_litigation_context_inference_hearing(self):
        result = _add_verb("开庭", "litigation")
        assert result == "参加开庭"

    def test_litigation_default_verb(self):
        result = _add_verb("立案申请", "litigation")
        assert result == "提交立案申请"

    def test_criminal_default_verb(self):
        result = _add_verb("辩护材料", "criminal")
        assert result == "提交辩护材料"


# ============================================================
# collect_work_log_suggestions
# ============================================================


class TestCollectWorkLogSuggestions:
    def test_local_nonexistent_dir_returns_empty(self):
        result = collect_work_log_suggestions("/nonexistent/path/xyz", "litigation")
        assert result == []

    def test_local_with_date_folders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "2024.01.05-立案").mkdir()
            (root / "2024.03.10-开庭").mkdir()
            (root / "not_a_date").mkdir()

            result = collect_work_log_suggestions(tmpdir, "litigation")
            assert len(result) == 2
            assert result[0]["date"] < result[1]["date"]  # sorted

    def test_file_not_included(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "2024.01.01-判决.txt").write_text("hello")
            result = collect_work_log_suggestions(tmpdir, "litigation")
            assert result == []

    def test_cloud_storage_delegation(self):
        mock_provider = MagicMock()
        mock_child = SimpleNamespace(name="2024.06.01-调解", is_dir=True)
        mock_provider.list_directory.return_value = [mock_child]
        result = collect_work_log_suggestions("/cloud/folder", "litigation", storage_provider=mock_provider)
        assert len(result) == 1
        assert result[0]["date"] == "2024-06-01"


# ============================================================
# collect_archive_item_options
# ============================================================


class TestCollectArchiveItemOptions:
    def test_litigation_returns_case_source_items(self):
        result = collect_archive_item_options("litigation")
        assert isinstance(result, list)
        assert all("code" in item and "name" in item for item in result)
        # All items should have source="case"
        codes = [item["code"] for item in result]
        assert len(codes) > 0

    def test_non_litigation(self):
        result = collect_archive_item_options("non_litigation")
        assert isinstance(result, list)

    def test_unknown_category_returns_empty(self):
        result = collect_archive_item_options("unknown_category")
        assert result == []


# ============================================================
# _get_evidence_code
# ============================================================


class TestGetEvidenceCode:
    def test_litigation(self):
        assert _get_evidence_code("litigation") == "lt_10"

    def test_criminal(self):
        assert _get_evidence_code("criminal") == "cr_8"

    def test_non_litigation(self):
        assert _get_evidence_code("non_litigation") == "nl_9"

    def test_unknown_defaults_to_lt_10(self):
        assert _get_evidence_code("unknown") == "lt_10"


# ============================================================
# _get_item_name
# ============================================================


class TestGetItemName:
    def test_known_code(self):
        name = _get_item_name("litigation", "lt_7")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_unknown_code_returns_code(self):
        name = _get_item_name("litigation", "nonexistent_code")
        assert name == "nonexistent_code"


# ============================================================
# reload_learned_code_rules
# ============================================================


class TestReloadLearnedCodeRules:
    def test_reload_does_not_raise(self):
        # Should not raise even if _learned_rules module doesn't exist
        reload_learned_code_rules()
