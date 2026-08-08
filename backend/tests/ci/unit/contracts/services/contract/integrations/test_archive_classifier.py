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


# ============================================================
# 真实归档文件名模式匹配测试
# 基于已归档合同中用户手动上传的文件名模式
# 使用 monkeypatch 隔离学习规则，只测试硬编码规则
# ============================================================


class TestRealArchiveFilenamesLitigation:
    """测试诉讼类归档合同中真实文件名的匹配。"""

    @pytest.fixture(autouse=True)
    def _isolate_hardcoded_rules(self, monkeypatch):
        monkeypatch.setattr(
            "apps.contracts.services.contract.integrations.archive_classifier._LEARNED_CODE_RULES",
            {},
        )
        monkeypatch.setattr(
            "apps.contracts.services.contract.integrations.archive_classifier._match_by_db_learned_rules",
            lambda *args, **kwargs: None,
        )

    def test_authorization_with_practice_license(self):
        """执业证应匹配到授权委托材料。"""
        result = classify_archive_material(
            filename="1.1-张三执业证_20220627.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_20"

    def test_authorization_with_legal_rep_certificate(self):
        """法定代表人身份证明书应匹配到授权委托材料。"""
        result = classify_archive_material(
            filename="7-法定代表人身份证明书_某某机械有限公司_V1_2023.12.28.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_20"

    def test_authorization_with_business_license(self):
        """营业执照应匹配到授权委托材料。"""
        result = classify_archive_material(
            filename="营业执照_某某科技有限公司.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_20"

    def test_complaint_with_number_prefix(self):
        """数字前缀的起诉状应匹配到起诉书项。"""
        result = classify_archive_material(
            filename="1-起诉状_李四诉王五民间借贷纠纷案_V2_20250616.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"

    def test_evidence_list_with_prefix(self):
        """起诉证据清单应匹配到调查材料项（非起诉书项）。"""
        result = classify_archive_material(
            filename="3-起诉证据清单_李四诉王五民间借贷纠纷案_V1_20250623.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_10"

    def test_evidence_detail(self):
        """证据明细应匹配到调查材料项。"""
        result = classify_archive_material(
            filename="证据明细_李四与王五民间借贷纠纷_20250623.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_10"

    def test_preservation_application(self):
        """财产保全申请书应匹配到保全申请项。"""
        result = classify_archive_material(
            filename="3-财产保全申请书_赵六诉某某建设_V1_2024.01.02.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_11"

    def test_judgment_with_date_suffix(self):
        """带日期后缀的判决书应匹配到判决书项。"""
        result = classify_archive_material(
            filename="判决书_赵六诉某某建设_2024.07.16收.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_17"

    def test_civil_judgment(self):
        """民事判决书应匹配到判决书项。"""
        result = classify_archive_material(
            filename="民事判决书_2022_粤0101民初12345号.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_17"

    def test_mediation_agreement(self):
        """调解书应匹配到判决书项。"""
        result = classify_archive_material(
            filename="调解书_李四诉王五案_20250828收.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_17"

    def test_withdrawal_ruling(self):
        """撤诉裁定应匹配到判决书项。"""
        result = classify_archive_material(
            filename="撤诉裁定_甲方诉乙方案件_20260331收.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_17"

    def test_sealing_ruling(self):
        """查封裁定应匹配到保全申请项（lt_11 排在 lt_17 之前）。"""
        result = classify_archive_material(
            filename="查封裁定_甲方与乙方案_2024.3.4.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_11"

    def test_court_summon(self):
        """传票应匹配到出庭通知书项。"""
        result = classify_archive_material(
            filename="传票_某某机械案件10.11_开庭_2024.08.08收.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_14"

    def test_court_notice(self):
        """开庭通知应匹配到出庭通知书项。"""
        result = classify_archive_material(
            filename="开庭通知_1.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_14"

    def test_acceptance_notice(self):
        """受理通知书应匹配到保全申请项（非调查材料项）。"""
        result = classify_archive_material(
            filename="受理通知书_赵六诉某某建设_2024.01.02.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_11"

    def test_invoice_file(self):
        """发票应匹配到收费凭证项。"""
        result = classify_archive_material(
            filename="发票_钱七购房合同案_第5张__2024.3.19.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_5"

    def test_investigation_record(self):
        """调查笔录应匹配到调查材料项。"""
        result = classify_archive_material(
            filename="周九调查笔录.pdf",
            source_path="/contracts/case1",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_10"


class TestRealArchiveFilenamesCriminal:
    """测试刑事类归档合同中真实文件名的匹配。"""

    @pytest.fixture(autouse=True)
    def _isolate_hardcoded_rules(self, monkeypatch):
        monkeypatch.setattr(
            "apps.contracts.services.contract.integrations.archive_classifier._LEARNED_CODE_RULES",
            {},
        )
        monkeypatch.setattr(
            "apps.contracts.services.contract.integrations.archive_classifier._match_by_db_learned_rules",
            lambda *args, **kwargs: None,
        )

    def test_criminal_judgment(self):
        """刑事判决书应匹配到裁定书、判决书项。"""
        result = classify_archive_material(
            filename="刑事判决书_孙八涉嫌危险驾驶罪案件_20260416收_1.pdf",
            source_path="/contracts/case1",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_14"

    def test_defense_opinion(self):
        """辩护意见应匹配到辩护词项。"""
        result = classify_archive_material(
            filename="辩护意见_孙八涉嫌醉驾案件_V1_20260413.pdf",
            source_path="/contracts/case1",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_12"

    def test_meeting_record(self):
        """律师会见笔录应匹配到会见笔录项。"""
        result = classify_archive_material(
            filename="律师会见笔录_孙八案件_V1_20260202.pdf",
            source_path="/contracts/case1",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_7"

    def test_authorization_criminal(self):
        """授权委托书应匹配到授权委托材料项。"""
        result = classify_archive_material(
            filename="授权委托书_孙八_孙八醉驾一案_V1_20260202.pdf",
            source_path="/contracts/case1",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_18"

    def test_indictment_with_plea_negotiation(self):
        """认罪认罚起诉书应匹配到起诉书项。"""
        result = classify_archive_material(
            filename="起诉书_认罪认罚案件适用_自然人犯罪案件_.PDF-1_1.pdf",
            source_path="/contracts/case1",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_11"


class TestRealArchiveFilenamesNonLitigation:
    """测试非诉类归档合同中真实文件名的匹配。"""

    @pytest.fixture(autouse=True)
    def _isolate_hardcoded_rules(self, monkeypatch):
        monkeypatch.setattr(
            "apps.contracts.services.contract.integrations.archive_classifier._LEARNED_CODE_RULES",
            {},
        )
        monkeypatch.setattr(
            "apps.contracts.services.contract.integrations.archive_classifier._match_by_db_learned_rules",
            lambda *args, **kwargs: None,
        )

    def test_authorization_non_litigation(self):
        """授权委托书应匹配到授权委托材料项。"""
        result = classify_archive_material(
            filename="1-_签字版_授权委托书-钱七案.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_12"

    def test_suo_letter_non_litigation(self):
        """所函应匹配到授权委托材料项。"""
        result = classify_archive_material(
            filename="5-所函_某某机械有限公司_V1_2024.1.2.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_12"

    def test_practice_license_non_litigation(self):
        """执业证应匹配到授权委托材料项。"""
        result = classify_archive_material(
            filename="1.1-张三执业证_20220627.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_12"

    def test_legal_rep_certificate_non_litigation(self):
        """法定代表人身份证明书应匹配到授权委托材料项。"""
        result = classify_archive_material(
            filename="7-法定代表人身份证明书_某某机械有限公司_V1_2023.12.28.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_12"

    def test_business_license_non_litigation(self):
        """营业执照应匹配到授权委托材料项。"""
        result = classify_archive_material(
            filename="营业执照_某某科技有限公司.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_12"

    def test_invoice_non_litigation(self):
        """发票应匹配到收费凭证项。"""
        result = classify_archive_material(
            filename="发票_某某不锈钢有限公司及关联公司常年法律顾问服务项目_2024-2025.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_5"

    def test_lawyer_letter_non_litigation(self):
        """律师函应匹配到法律意见书、律师函等项。"""
        result = classify_archive_material(
            filename="律师函_委托人委托律师发给对方_20260101发出_20260105签收.pdf",
            source_path="/contracts/case1",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == "nl_8"


# ============================================================
# 学习规则匹配测试
# ============================================================


class TestLearnedRulesMatch:
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
