"""Tests for MaterialClassificationService — pure logic methods."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


@pytest.fixture()
def svc() -> MaterialClassificationService:
    return MaterialClassificationService()


# ---------------------------------------------------------------------------
# _normalize_for_match
# ---------------------------------------------------------------------------


class TestNormalizeForMatch:
    def test_basic(self, svc: MaterialClassificationService):
        assert svc._normalize_for_match("  Hello World  ") == "helloworld"

    def test_empty(self, svc: MaterialClassificationService):
        assert svc._normalize_for_match("") == ""

    def test_none(self, svc: MaterialClassificationService):
        assert svc._normalize_for_match("") == ""

    def test_backslash_to_slash(self, svc: MaterialClassificationService):
        assert svc._normalize_for_match("a\\b\\c") == "a/b/c"

    def test_whitespace_collapsed(self, svc: MaterialClassificationService):
        assert svc._normalize_for_match("a b  c\td") == "abcd"


# ---------------------------------------------------------------------------
# _to_confidence
# ---------------------------------------------------------------------------


class TestToConfidence:
    def test_normal(self, svc: MaterialClassificationService):
        assert svc._to_confidence(0.7) == 0.7

    def test_below_zero(self, svc: MaterialClassificationService):
        assert svc._to_confidence(-1) == 0.0

    def test_above_one(self, svc: MaterialClassificationService):
        assert svc._to_confidence(2.0) == 1.0

    def test_string(self, svc: MaterialClassificationService):
        assert svc._to_confidence("0.5") == 0.5

    def test_none(self, svc: MaterialClassificationService):
        assert svc._to_confidence(None) == 0.0

    def test_invalid_string(self, svc: MaterialClassificationService):
        assert svc._to_confidence("abc") == 0.0


# ---------------------------------------------------------------------------
# _extract_subfolder_hint
# ---------------------------------------------------------------------------


class TestExtractSubfolderHint:
    def test_numbered_prefix(self, svc: MaterialClassificationService):
        assert svc._extract_subfolder_hint("2-立案材料") == "立案材料"

    def test_underscore_prefix(self, svc: MaterialClassificationService):
        assert svc._extract_subfolder_hint("3_执行依据") == "执行依据"

    def test_no_prefix(self, svc: MaterialClassificationService):
        assert svc._extract_subfolder_hint("立案材料") == "立案材料"

    def test_empty(self, svc: MaterialClassificationService):
        assert svc._extract_subfolder_hint("") == ""

    def test_multi_level(self, svc: MaterialClassificationService):
        assert svc._extract_subfolder_hint("parent/2-子目录") == "子目录"


# ---------------------------------------------------------------------------
# classify_contract_material
# ---------------------------------------------------------------------------


class TestClassifyContractMaterial:
    def test_in_contract_invoice_folder_with_supervision_card(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="服务质量监督卡.pdf",
            text_excerpt="",
            source_path="/合同发票/服务质量监督卡.pdf",
        )
        assert result["category"] == "supervision_card"
        assert result["confidence"] >= 0.9

    def test_in_contract_invoice_folder_with_supplementary(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="补充协议.pdf",
            text_excerpt="",
            source_path="/合同发票/补充协议.pdf",
        )
        assert result["category"] == "supplementary_agreement"

    def test_in_contract_invoice_folder_with_invoice(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="发票.pdf",
            text_excerpt="",
            source_path="/合同及发票/发票.pdf",
        )
        assert result["category"] == "invoice"

    def test_in_contract_invoice_folder_with_contract(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="采购合同.pdf",
            text_excerpt="",
            source_path="/合同发票/采购合同.pdf",
        )
        assert result["category"] == "contract_original"
        assert result["confidence"] >= 0.9

    def test_in_contract_invoice_folder_no_match_defaults(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="random.pdf",
            text_excerpt="",
            source_path="/合同发票/random.pdf",
        )
        assert result["category"] == "contract_original"
        assert result["confidence"] == 0.5

    def test_in_contract_folder_with_false_positive(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="合同纠纷说明.pdf",
            text_excerpt="",
            source_path="/合同发票/合同纠纷说明.pdf",
        )
        # "合同纠纷" is a false positive, so it falls through to default contract_original
        assert result["category"] == "contract_original"

    def test_not_in_contract_invoice_folder(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="判决书.pdf",
            text_excerpt="",
            source_path="/案件材料/判决书.pdf",
        )
        assert result["category"] == "case_material"
        assert result["confidence"] >= 0.9

    def test_empty_filename_in_contract_folder(self, svc: MaterialClassificationService):
        result = svc.classify_contract_material(
            filename="",
            text_excerpt="",
            source_path="/合同发票/",
        )
        # Empty filename -> _classify_contract_by_filename returns None -> default
        assert result["category"] == "contract_original"


# ---------------------------------------------------------------------------
# _classify_contract_by_filename
# ---------------------------------------------------------------------------


class TestClassifyContractByFilename:
    def test_supervision_card(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("质量监督卡.pdf")
        assert result is not None
        assert result["category"] == "supervision_card"

    def test_supplementary_agreement(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("补充合同.pdf")
        assert result is not None
        assert result["category"] == "supplementary_agreement"

    def test_invoice(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("开票.pdf")
        assert result is not None
        assert result["category"] == "invoice"

    def test_contract_original(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("采购合同.pdf")
        assert result is not None
        assert result["category"] == "contract_original"

    def test_false_positive(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("合同纠纷判决.pdf")
        assert result is None

    def test_empty(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("")
        assert result is None

    def test_no_match(self, svc: MaterialClassificationService):
        result = svc._classify_contract_by_filename("random_doc.pdf")
        assert result is None


# ---------------------------------------------------------------------------
# classify_case_material
# ---------------------------------------------------------------------------


class TestClassifyCaseMaterial:
    def test_keyword_rule_match(self, svc: MaterialClassificationService):
        result = svc.classify_case_material(
            filename="执行申请书.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert result["confidence"] >= 0.9

    def test_identity_doc_rule(self, svc: MaterialClassificationService):
        result = svc.classify_case_material(
            filename="身份证复印件.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["type_name_hint"] == "当事人身份证明"

    def test_no_match_ai_disabled(self, svc: MaterialClassificationService):
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "unknown"
        assert result["confidence"] == 0.0

    def test_filing_material_folder(self, svc: MaterialClassificationService):
        result = svc.classify_case_material(
            filename="something.pdf",
            text_excerpt="",
            source_path="/立案材料/something.pdf",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_no_match_ai_disabled_with_folder_hint(self, svc: MaterialClassificationService):
        result = svc.classify_case_material(
            filename="unknown.pdf",
            text_excerpt="",
            scan_subfolder="2-我的材料",
            enable_ai=False,
        )
        assert result["type_name_hint"] == "我的材料"


# ---------------------------------------------------------------------------
# _build_case_suggestion
# ---------------------------------------------------------------------------


class TestBuildCaseSuggestion:
    def test_party_our(self, svc: MaterialClassificationService):
        result = svc._build_case_suggestion(
            category="party",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="reason",
            context={"our_party_ids": [1, 2]},
        )
        assert result["category"] == "party"
        assert result["side"] == "our"
        assert 1 in result["suggested_party_ids"]

    def test_party_opponent(self, svc: MaterialClassificationService):
        result = svc._build_case_suggestion(
            category="party",
            side="opponent",
            type_name_hint="test",
            confidence=0.9,
            reason="reason",
            context={"opponent_party_ids": [5]},
        )
        assert result["side"] == "opponent"
        assert 5 in result["suggested_party_ids"]

    def test_non_party(self, svc: MaterialClassificationService):
        result = svc._build_case_suggestion(
            category="non_party",
            side="unknown",
            type_name_hint="test",
            confidence=0.9,
            reason="reason",
            context={"primary_supervising_authority_id": 10},
        )
        assert result["category"] == "non_party"
        assert result["side"] == "unknown"
        assert result["suggested_supervising_authority_id"] == 10

    def test_invalid_category(self, svc: MaterialClassificationService):
        result = svc._build_case_suggestion(
            category="invalid",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="reason",
            context={},
        )
        assert result["category"] == "unknown"
        assert result["side"] == "unknown"


# ---------------------------------------------------------------------------
# _extract_party_ids_by_side
# ---------------------------------------------------------------------------


class TestExtractPartyIdsBySide:
    def test_normal(self, svc: MaterialClassificationService):
        result = svc._extract_party_ids_by_side(side="our", context={"our_party_ids": [1, 2]})
        assert result == [1, 2]

    def test_non_list(self, svc: MaterialClassificationService):
        result = svc._extract_party_ids_by_side(side="our", context={"our_party_ids": "bad"})
        assert result == []

    def test_with_invalid_items(self, svc: MaterialClassificationService):
        result = svc._extract_party_ids_by_side(side="our", context={"our_party_ids": [1, "bad", 2]})
        assert result == [1, 2]

    def test_with_duplicates(self, svc: MaterialClassificationService):
        result = svc._extract_party_ids_by_side(side="our", context={"our_party_ids": [1, 1, 2]})
        assert result == [1, 2]

    def test_with_zero(self, svc: MaterialClassificationService):
        result = svc._extract_party_ids_by_side(side="our", context={"our_party_ids": [0, -1]})
        assert result == []

    def test_empty(self, svc: MaterialClassificationService):
        result = svc._extract_party_ids_by_side(side="our", context={})
        assert result == []


# ---------------------------------------------------------------------------
# _extract_primary_supervising_authority_id
# ---------------------------------------------------------------------------


class TestExtractPrimarySupervisingAuthorityId:
    def test_normal(self, svc: MaterialClassificationService):
        result = svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": 5})
        assert result == 5

    def test_none(self, svc: MaterialClassificationService):
        result = svc._extract_primary_supervising_authority_id({})
        assert result is None

    def test_zero(self, svc: MaterialClassificationService):
        result = svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": 0})
        assert result is None

    def test_invalid_string(self, svc: MaterialClassificationService):
        result = svc._extract_primary_supervising_authority_id({"primary_supervising_authority_id": "abc"})
        assert result is None


# ---------------------------------------------------------------------------
# _infer_case_side
# ---------------------------------------------------------------------------


class TestInferCaseSide:
    def test_our_hint(self, svc: MaterialClassificationService):
        assert svc._infer_case_side(match_text="申请人张三", context={}) == "our"

    def test_opponent_hint(self, svc: MaterialClassificationService):
        assert svc._infer_case_side(match_text="被执行人李四", context={}) == "opponent"

    def test_both_hints(self, svc: MaterialClassificationService):
        assert svc._infer_case_side(match_text="原告和被告", context={}) == "unknown"

    def test_no_hint_with_our_party_ids(self, svc: MaterialClassificationService):
        assert svc._infer_case_side(match_text="随机文本", context={"our_party_ids": [1]}) == "our"

    def test_no_hint_with_opponent_party_ids(self, svc: MaterialClassificationService):
        assert svc._infer_case_side(match_text="随机文本", context={"opponent_party_ids": [1]}) == "opponent"

    def test_empty_text(self, svc: MaterialClassificationService):
        assert svc._infer_case_side(match_text="", context={}) == "unknown"


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_valid_json(self, svc: MaterialClassificationService):
        result = svc._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_text(self, svc: MaterialClassificationService):
        result = svc._extract_json('Some text {"key": "value"} more text')
        assert result == {"key": "value"}

    def test_fenced_json(self, svc: MaterialClassificationService):
        result = svc._extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_empty(self, svc: MaterialClassificationService):
        assert svc._extract_json("") is None

    def test_no_json(self, svc: MaterialClassificationService):
        assert svc._extract_json("just plain text") is None

    def test_invalid_json_in_fence(self, svc: MaterialClassificationService):
        result = svc._extract_json("```\nnot json\n```")
        assert result is None


# ---------------------------------------------------------------------------
# parse_work_log_from_folder_name
# ---------------------------------------------------------------------------


class TestParseWorkLogFromFolderName:
    def test_valid(self, svc: MaterialClassificationService):
        result = svc.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result is not None
        assert result["date"] == "2025-01-23"
        assert result["content"] == "审核知识产权合同"

    def test_dash_separator(self, svc: MaterialClassificationService):
        result = svc.parse_work_log_from_folder_name("2025.12.31-合同审查")
        assert result is not None
        assert result["date"] == "2025-12-31"

    def test_invalid(self, svc: MaterialClassificationService):
        result = svc.parse_work_log_from_folder_name("not a date")
        assert result is None

    def test_empty(self, svc: MaterialClassificationService):
        result = svc.parse_work_log_from_folder_name("")
        assert result is None


# ---------------------------------------------------------------------------
# classify_archive_material
# ---------------------------------------------------------------------------


class TestClassifyArchiveMaterial:
    def test_folder_match_litigation(self, svc: MaterialClassificationService):
        result = svc.classify_archive_material(
            filename="test.pdf",
            source_path="/案件/起诉状/test.pdf",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"
        assert result["confidence"] >= 0.9

    def test_filename_match_criminal(self, svc: MaterialClassificationService):
        result = svc.classify_archive_material(
            filename="辩护词.pdf",
            source_path="/案件/其他/辩护词.pdf",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_12"

    def test_invalid_category_defaults_to_litigation(self, svc: MaterialClassificationService):
        result = svc.classify_archive_material(
            filename="起诉状.pdf",
            source_path="/案件/起诉状.pdf",
            archive_category="invalid",
        )
        assert result["archive_item_code"] == "lt_7"

    def test_no_match(self, svc: MaterialClassificationService):
        result = svc.classify_archive_material(
            filename="random.pdf",
            source_path="/random/",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == ""
        assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# _match_archive_by_filename
# ---------------------------------------------------------------------------


class TestMatchArchiveByFilename:
    def test_match(self, svc: MaterialClassificationService):
        result = svc._match_archive_by_filename(
            filename="执行申请书.pdf",
            archive_category="litigation",
        )
        assert result is not None
        assert result["archive_item_code"] == "lt_7"

    def test_no_match(self, svc: MaterialClassificationService):
        result = svc._match_archive_by_filename(
            filename="random.pdf",
            archive_category="litigation",
        )
        assert result is None

    def test_empty_rules(self, svc: MaterialClassificationService):
        result = svc._match_archive_by_filename(
            filename="test.pdf",
            archive_category="nonexistent",
        )
        assert result is None


# ---------------------------------------------------------------------------
# _extract_path_parts
# ---------------------------------------------------------------------------


class TestExtractPathParts:
    def test_numbered_prefix(self, svc: MaterialClassificationService):
        parts = svc._extract_path_parts("/1-起诉状/2-证据/test.pdf")
        assert "起诉状" in parts
        assert "证据" in parts

    def test_simple(self, svc: MaterialClassificationService):
        parts = svc._extract_path_parts("/foo/bar/test.pdf")
        assert "foo" in parts
        assert "bar" in parts
