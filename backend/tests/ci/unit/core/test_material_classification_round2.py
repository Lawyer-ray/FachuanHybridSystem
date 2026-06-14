"""Coverage tests for material_classification_service uncovered branches."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


class TestClassifyContractMaterial:
    """Test classify_contract_material uncovered branches."""

    def test_non_contract_invoice_folder_returns_case_material(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="起诉状.pdf",
            text_excerpt="some text",
            source_path="/data/cases/起诉状.pdf",
        )
        assert result["category"] == "case_material"
        assert result["confidence"] == 0.95

    def test_contract_invoice_folder_default(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="unknown_file.pdf",
            text_excerpt="text",
            source_path="/data/合同发票/unknown_file.pdf",
        )
        assert result["category"] == "contract_original"
        assert result["confidence"] == 0.5

    def test_contract_invoice_folder_supervision_card(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="律师办案服务质量监督卡.pdf",
            text_excerpt="",
            source_path="/data/合同发票/监督卡.pdf",
        )
        assert result["category"] == "supervision_card"

    def test_contract_invoice_folder_supplementary(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="补充协议.pdf",
            text_excerpt="",
            source_path="/data/合同及发票/补充.pdf",
        )
        assert result["category"] == "supplementary_agreement"

    def test_contract_invoice_folder_invoice(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="增值税发票.pdf",
            text_excerpt="",
            source_path="/data/合同发票/发票.pdf",
        )
        assert result["category"] == "invoice"

    def test_contract_invoice_folder_contract(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="服务合同.pdf",
            text_excerpt="",
            source_path="/data/合同发票/合同.pdf",
        )
        assert result["category"] == "contract_original"

    def test_contract_false_positive_pattern(self):
        svc = MaterialClassificationService()
        result = svc.classify_contract_material(
            filename="合同纠纷起诉状.pdf",
            text_excerpt="",
            source_path="/data/合同发票/合同纠纷.pdf",
        )
        # "合同纠纷" is a false positive, should not match contract_original
        assert result["category"] == "contract_original"  # defaults since no other keyword matched


class TestClassifyContractByFilename:
    def test_empty_filename(self):
        svc = MaterialClassificationService()
        assert svc._classify_contract_by_filename("") is None
        assert svc._classify_contract_by_filename("   ") is None


class TestNormalizeForMatch:
    def test_backslash_replacement(self):
        assert MaterialClassificationService._normalize_for_match("a\\b") == "a/b"

    def test_whitespace_removal(self):
        assert MaterialClassificationService._normalize_for_match("  hello  world  ") == "helloworld"

    def test_empty(self):
        assert MaterialClassificationService._normalize_for_match("") == ""
        assert MaterialClassificationService._normalize_for_match(None) == ""  # type: ignore[arg-type]


class TestExtractSubfolderHint:
    def test_numbered_prefix(self):
        assert MaterialClassificationService._extract_subfolder_hint("2-立案材料") == "立案材料"

    def test_underscore_prefix(self):
        assert MaterialClassificationService._extract_subfolder_hint("3_执行依据") == "执行依据"

    def test_dot_prefix(self):
        assert MaterialClassificationService._extract_subfolder_hint("1.证据材料") == "证据材料"

    def test_no_prefix(self):
        assert MaterialClassificationService._extract_subfolder_hint("立案材料") == "立案材料"

    def test_empty(self):
        assert MaterialClassificationService._extract_subfolder_hint("") == ""
        assert MaterialClassificationService._extract_subfolder_hint(None) == ""  # type: ignore[arg-type]

    def test_multilevel_path(self):
        assert MaterialClassificationService._extract_subfolder_hint("parent/2-子目录") == "子目录"


class TestToConfidence:
    def test_normal_value(self):
        svc = MaterialClassificationService()
        assert svc._to_confidence(0.8) == 0.8

    def test_negative_clamped(self):
        svc = MaterialClassificationService()
        assert svc._to_confidence(-0.5) == 0.0

    def test_above_one_clamped(self):
        svc = MaterialClassificationService()
        assert svc._to_confidence(1.5) == 1.0

    def test_none_returns_zero(self):
        svc = MaterialClassificationService()
        assert svc._to_confidence(None) == 0.0

    def test_string_returns_zero(self):
        svc = MaterialClassificationService()
        assert svc._to_confidence("abc") == 0.0

    def test_int_value(self):
        svc = MaterialClassificationService()
        assert svc._to_confidence(1) == 1.0


class TestExtractJson:
    def test_valid_json(self):
        result = MaterialClassificationService._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_text(self):
        result = MaterialClassificationService._extract_json('Here is the result: {"key": "value"} done')
        assert result == {"key": "value"}

    def test_fenced_json(self):
        result = MaterialClassificationService._extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_empty_returns_none(self):
        assert MaterialClassificationService._extract_json("") is None
        assert MaterialClassificationService._extract_json(None) is None  # type: ignore[arg-type]

    def test_invalid_json(self):
        assert MaterialClassificationService._extract_json("not json at all") is None

    def test_non_dict_json(self):
        assert MaterialClassificationService._extract_json("[1, 2, 3]") is None

    def test_fenced_non_json(self):
        assert MaterialClassificationService._extract_json("```\nnot json\n```") is None


class TestExtractPartyIdsBySide:
    def test_our_side(self):
        context = {"our_party_ids": [1, 2, 3]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2, 3]

    def test_opponent_side(self):
        context = {"opponent_party_ids": [10, 20]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="opponent", context=context)
        assert result == [10, 20]

    def test_invalid_ids_filtered(self):
        context = {"our_party_ids": [1, -1, 0, "bad", 2]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_duplicate_ids(self):
        context = {"our_party_ids": [1, 1, 2]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_non_list_returns_empty(self):
        context = {"our_party_ids": "not a list"}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == []

    def test_missing_key(self):
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context={})
        assert result == []


class TestExtractPrimarySupervisingAuthorityId:
    def test_valid_id(self):
        context = {"primary_supervising_authority_id": 42}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) == 42

    def test_string_id(self):
        context = {"primary_supervising_authority_id": "42"}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) == 42

    def test_zero_returns_none(self):
        context = {"primary_supervising_authority_id": 0}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) is None

    def test_negative_returns_none(self):
        context = {"primary_supervising_authority_id": -1}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) is None

    def test_none_returns_none(self):
        assert MaterialClassificationService._extract_primary_supervising_authority_id({}) is None

    def test_invalid_string_returns_none(self):
        context = {"primary_supervising_authority_id": "abc"}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) is None


class TestInferCaseSide:
    def test_empty_text(self):
        svc = MaterialClassificationService()
        assert svc._infer_case_side(match_text="", context={}) == "unknown"

    def test_opponent_hint(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(match_text="被告某某公司", context={})
        assert result == "opponent"

    def test_our_hint(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(match_text="原告某某", context={})
        assert result == "our"

    def test_both_hints(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(match_text="原告和被告", context={})
        assert result == "unknown"

    def test_context_party_ids_fallback(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(match_text="某公司", context={"our_party_ids": [1]})
        assert result == "our"

    def test_context_opponent_ids_fallback(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(match_text="某公司", context={"opponent_party_ids": [1]})
        assert result == "opponent"

    def test_context_party_names(self):
        svc = MaterialClassificationService()
        result = svc._infer_case_side(
            match_text="某某科技有限公司文件",
            context={"opponent_party_names": ["某某科技有限公司"]},
        )
        assert result == "opponent"


class TestClassifyCaseMaterial:
    def test_rule_based_match(self):
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="执行申请书.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["confidence"] >= 0.9

    def test_no_rule_no_ai(self):
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="random.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "unknown"
        assert "未启用识别" in result["reason"]

    def test_no_rule_no_ai_with_folder_hint(self):
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="random.pdf",
            text_excerpt="",
            enable_ai=False,
            parent_folder_hint="立案材料",
        )
        assert result["type_name_hint"] == "立案材料"

    @patch("apps.core.services.material_classification_service.MaterialClassificationService._complete", return_value="")
    def test_ai_returns_empty(self, mock_complete):
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="some text",
            enable_ai=True,
        )
        assert "AI 分类不可用" in result["reason"]

    @patch("apps.core.services.material_classification_service.MaterialClassificationService._complete")
    def test_ai_returns_non_dict(self, mock_complete):
        mock_complete.return_value = "not json"
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="some text",
            enable_ai=True,
        )
        assert "解析失败" in result["reason"]

    @patch("apps.core.services.material_classification_service.MaterialClassificationService._complete")
    def test_ai_success(self, mock_complete):
        mock_complete.return_value = '{"category": "party", "side": "our", "type_name_hint": "起诉状", "confidence": 0.9, "reason": "test"}'
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="some text",
            enable_ai=True,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    @patch("apps.core.services.material_classification_service.MaterialClassificationService._complete")
    def test_ai_non_party_normalizes_side(self, mock_complete):
        mock_complete.return_value = '{"category": "non_party", "side": "our", "confidence": 0.8, "reason": "test"}'
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="text",
            enable_ai=True,
        )
        assert result["category"] == "non_party"
        assert result["side"] == "unknown"

    @patch("apps.core.services.material_classification_service.MaterialClassificationService._complete")
    def test_ai_invalid_category(self, mock_complete):
        mock_complete.return_value = '{"category": "invalid_cat", "side": "our", "confidence": 0.8, "reason": "test"}'
        svc = MaterialClassificationService()
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="text",
            enable_ai=True,
        )
        assert result["category"] == "unknown"


class TestClassifyCaseByFilenameAndPath:
    def test_filing_material_folder(self):
        svc = MaterialClassificationService()
        result = svc._classify_case_by_filename_and_path(
            filename="",
            source_path="/data/案件/1-立案材料/",
            context={},
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_filing_material_folder_with_filename(self):
        svc = MaterialClassificationService()
        result = svc._classify_case_by_filename_and_path(
            filename="执行申请书.pdf",
            source_path="/data/案件/1-立案材料/",
            context={},
        )
        assert result["category"] == "party"

    def test_empty_match_text(self):
        svc = MaterialClassificationService()
        result = svc._classify_case_by_filename_and_path(
            filename="",
            source_path="",
            context={},
        )
        assert result is None

    def test_auto_side_infer_with_context(self):
        svc = MaterialClassificationService()
        result = svc._classify_case_by_filename_and_path(
            filename="委托材料-原告.pdf",
            source_path="/data/案件/",
            context={"our_party_ids": [1, 2]},
        )
        assert result is not None
        assert result["category"] == "party"


class TestBuildCaseSuggestion:
    def test_non_party_normalizes_side(self):
        svc = MaterialClassificationService()
        result = svc._build_case_suggestion(
            category="non_party",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="test",
            context={},
        )
        assert result["side"] == "unknown"
        assert result["suggested_supervising_authority_id"] is None

    def test_party_extracts_ids(self):
        svc = MaterialClassificationService()
        result = svc._build_case_suggestion(
            category="party",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="test",
            context={"our_party_ids": [1, 2]},
        )
        assert result["suggested_party_ids"] == [1, 2]

    def test_unknown_category(self):
        svc = MaterialClassificationService()
        result = svc._build_case_suggestion(
            category="invalid",
            side="our",
            type_name_hint="test",
            confidence=0.5,
            reason="test",
            context={},
        )
        assert result["category"] == "unknown"
        assert result["side"] == "unknown"


class TestParseWorkLogFromFolderName:
    def test_valid_format(self):
        svc = MaterialClassificationService()
        result = svc.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result is not None
        assert result["date"] == "2025-01-23"
        assert result["content"] == "审核知识产权合同"

    def test_dash_format(self):
        svc = MaterialClassificationService()
        result = svc.parse_work_log_from_folder_name("2025-06-15 劳动纠纷")
        assert result is not None
        assert result["date"] == "2025-06-15"

    def test_no_match(self):
        svc = MaterialClassificationService()
        assert svc.parse_work_log_from_folder_name("普通文件夹") is None
        assert svc.parse_work_log_from_folder_name("") is None


class TestClassifyArchiveMaterial:
    def test_invalid_category_fallback(self):
        svc = MaterialClassificationService()
        result = svc.classify_archive_material(
            filename="test.pdf",
            source_path="/data/test.pdf",
            archive_category="invalid",
        )
        assert result["confidence"] == 0.0

    def test_folder_match(self):
        svc = MaterialClassificationService()
        result = svc.classify_archive_material(
            filename="test.pdf",
            source_path="/data/案件/起诉状/test.pdf",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"
        assert result["confidence"] == 0.95

    def test_filename_match(self):
        svc = MaterialClassificationService()
        result = svc.classify_archive_material(
            filename="授权委托书.pdf",
            source_path="/data/案件/test.pdf",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_20"
        assert result["confidence"] == 0.90

    def test_criminal_category(self):
        svc = MaterialClassificationService()
        result = svc.classify_archive_material(
            filename="会见笔录.pdf",
            source_path="/data/刑事/test.pdf",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_7"

    def test_no_match(self):
        svc = MaterialClassificationService()
        result = svc.classify_archive_material(
            filename="random.pdf",
            source_path="/data/random.pdf",
            archive_category="non_litigation",
        )
        assert result["archive_item_code"] == ""


class TestExtractPathParts:
    def test_simple_path(self):
        svc = MaterialClassificationService()
        parts = svc._extract_path_parts("/data/案件/起诉状/test.pdf")
        assert "案件" in parts
        assert "起诉状" in parts

    def test_numbered_parts(self):
        svc = MaterialClassificationService()
        parts = svc._extract_path_parts("/data/1-立案材料/test.pdf")
        assert "立案材料" in parts
