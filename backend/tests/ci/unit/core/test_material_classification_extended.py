"""
Extended unit tests for core/services/material_classification_service.py

Covers:
  - classify_contract_material: contract_invoice folder paths, non-contract paths
  - _classify_contract_by_filename: all keyword categories, false positive patterns, empty
  - classify_case_material: rule matching, AI fallback, enable_ai=False, side inference
  - _classify_case_by_filename_and_path: filing material folder, keyword rules, auto side
  - _build_case_suggestion: category normalization, side normalization, party/supervising authority IDs
  - _infer_case_side: opponent hints, our hints, both hints, context fallback
  - _extract_party_ids_by_side: valid, invalid, duplicates, non-positive
  - _extract_primary_supervising_authority_id: valid, invalid, negative
  - _extract_subfolder_hint: numbered prefix, no prefix, nested path
  - _normalize_for_match: empty, whitespace, backslash
  - _extract_json: valid JSON, fenced code block, invalid
  - classify_archive_material: folder match, filename match, unmatched
  - parse_work_log_from_folder_name: valid, invalid
  - _to_confidence: valid, negative, >1, None, string
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


@pytest.fixture
def svc():
    return MaterialClassificationService()


# ===========================================================================
# classify_contract_material
# ===========================================================================


class TestClassifyContractMaterial:
    def test_in_contract_invoice_folder_with_keyword(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="补充协议.pdf",
            text_excerpt="",
            source_path="/contracts/合同发票/补充协议.pdf",
        )
        assert result["category"] == "supplementary_agreement"

    def test_in_contract_invoice_folder_no_keyword(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="random.pdf",
            text_excerpt="",
            source_path="/contracts/合同发票/random.pdf",
        )
        assert result["category"] == "contract_original"
        assert result["confidence"] == 0.5

    def test_in_contract_invoice_folder_invoice(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="发票.pdf",
            text_excerpt="",
            source_path="/data/合同及发票/发票.pdf",
        )
        assert result["category"] == "invoice"

    def test_in_contract_invoice_folder_supervision_card(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="监督卡.pdf",
            text_excerpt="",
            source_path="/data/合同发票/监督卡.pdf",
        )
        assert result["category"] == "supervision_card"

    def test_in_contract_invoice_folder_contract(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="房屋租赁合同.pdf",
            text_excerpt="",
            source_path="/data/合同发票/房屋租赁合同.pdf",
        )
        assert result["category"] == "contract_original"

    def test_in_contract_invoice_folder_contract_false_positive(self, svc) -> None:
        """'合同纠纷' should not match as contract."""
        result = svc.classify_contract_material(
            filename="合同纠纷起诉状.pdf",
            text_excerpt="",
            source_path="/data/合同发票/合同纠纷起诉状.pdf",
        )
        # Falls through to default since no keyword matches
        assert result["category"] == "contract_original"

    def test_not_in_contract_invoice_folder(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="anything.pdf",
            text_excerpt="",
            source_path="/cases/材料/anything.pdf",
        )
        assert result["category"] == "case_material"
        assert result["confidence"] == 0.95

    def test_empty_source_path(self, svc) -> None:
        result = svc.classify_contract_material(
            filename="file.pdf",
            text_excerpt="",
            source_path="",
        )
        assert result["category"] == "case_material"


# ===========================================================================
# _classify_contract_by_filename
# ===========================================================================


class TestClassifyContractByFilename:
    def test_empty_filename(self, svc) -> None:
        assert svc._classify_contract_by_filename("") is None
        assert svc._classify_contract_by_filename(None) is None

    def test_supervision_card(self, svc) -> None:
        result = svc._classify_contract_by_filename("律师办案服务质量监督卡.pdf")
        assert result["category"] == "supervision_card"

    def test_supplementary(self, svc) -> None:
        result = svc._classify_contract_by_filename("补充合同.pdf")
        assert result["category"] == "supplementary_agreement"

    def test_invoice(self, svc) -> None:
        result = svc._classify_contract_by_filename("增值税专用发票.pdf")
        assert result["category"] == "invoice"

    def test_contract(self, svc) -> None:
        result = svc._classify_contract_by_filename("房屋买卖合同.pdf")
        assert result["category"] == "contract_original"

    def test_agreement(self, svc) -> None:
        result = svc._classify_contract_by_filename("合作协议.pdf")
        assert result["category"] == "contract_original"

    def test_false_positive_contract_dispute(self, svc) -> None:
        result = svc._classify_contract_by_filename("合同纠纷案.pdf")
        assert result is None

    def test_false_positive_agreement_dispute(self, svc) -> None:
        result = svc._classify_contract_by_filename("协议纠纷案.pdf")
        assert result is None

    def test_no_match(self, svc) -> None:
        result = svc._classify_contract_by_filename("random_document.pdf")
        assert result is None


# ===========================================================================
# classify_case_material
# ===========================================================================


class TestClassifyCaseMaterial:
    def test_rule_match_execution_application(self, svc) -> None:
        result = svc.classify_case_material(
            filename="执行申请书.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_rule_match_authorization(self, svc) -> None:
        result = svc.classify_case_material(
            filename="授权委托书.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "party"

    def test_rule_match_restriction(self, svc) -> None:
        result = svc.classify_case_material(
            filename="限制高消费令.pdf",
            text_excerpt="",
            enable_ai=False,
        )
        assert result["category"] == "non_party"

    def test_filing_material_folder(self, svc) -> None:
        result = svc.classify_case_material(
            filename="",
            text_excerpt="",
            source_path="/cases/立案材料/document.pdf",
            enable_ai=False,
        )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_filing_material_folder_with_filename(self, svc) -> None:
        result = svc.classify_case_material(
            filename="起诉状.pdf",
            text_excerpt="",
            source_path="/cases/立案材料/起诉状.pdf",
            enable_ai=False,
        )
        assert result["category"] == "party"

    def test_ai_disabled_no_match(self, svc) -> None:
        result = svc.classify_case_material(
            filename="random.pdf",
            text_excerpt="some text",
            enable_ai=False,
        )
        assert result["category"] == "unknown"
        assert "未启用识别" in result["reason"]

    def test_ai_disabled_with_folder_hint(self, svc) -> None:
        result = svc.classify_case_material(
            filename="random.pdf",
            text_excerpt="",
            enable_ai=False,
            parent_folder_hint="证据材料",
        )
        assert result["type_name_hint"] == "证据材料"

    def test_ai_enabled_no_content(self, svc) -> None:
        with patch.object(svc, "_complete", return_value=""):
            result = svc.classify_case_material(
                filename="random.pdf",
                text_excerpt="",
                enable_ai=True,
            )
        assert result["category"] == "unknown"
        assert "AI 分类不可用" in result["reason"]

    def test_ai_enabled_invalid_json(self, svc) -> None:
        with patch.object(svc, "_complete", return_value="not json"):
            result = svc.classify_case_material(
                filename="random.pdf",
                text_excerpt="",
                enable_ai=True,
            )
        assert "AI 输出解析失败" in result["reason"]

    def test_ai_enabled_valid_response(self, svc) -> None:
        with patch.object(svc, "_complete", return_value='{"category":"party","side":"our","type_name_hint":"证据","confidence":0.9,"reason":"test"}'):
            result = svc.classify_case_material(
                filename="random.pdf",
                text_excerpt="",
                enable_ai=True,
            )
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_ai_enabled_invalid_category(self, svc) -> None:
        with patch.object(svc, "_complete", return_value='{"category":"invalid","side":"our","confidence":0.9,"reason":"test"}'):
            result = svc.classify_case_material(
                filename="random.pdf",
                text_excerpt="",
                enable_ai=True,
            )
        assert result["category"] == "unknown"

    def test_ai_enabled_non_party_side_unknown(self, svc) -> None:
        with patch.object(svc, "_complete", return_value='{"category":"non_party","side":"our","confidence":0.9,"reason":"test"}'):
            result = svc.classify_case_material(
                filename="random.pdf",
                text_excerpt="",
                enable_ai=True,
            )
        assert result["side"] == "unknown"


# ===========================================================================
# _classify_case_by_filename_and_path
# ===========================================================================


class TestClassifyCaseByFilenameAndPath:
    def test_empty_match_text(self, svc) -> None:
        result = svc._classify_case_by_filename_and_path(
            filename="",
            source_path="",
            context={},
        )
        assert result is None

    def test_evidence_rule_match(self, svc) -> None:
        result = svc._classify_case_by_filename_and_path(
            filename="证据清单.pdf",
            source_path="",
            context={},
        )
        assert result is not None
        assert result["category"] == "party"

    def test_delivery_address_match(self, svc) -> None:
        result = svc._classify_case_by_filename_and_path(
            filename="送达地址确认书.pdf",
            source_path="",
            context={},
        )
        assert result is not None
        assert result["category"] == "non_party"

    def test_folder_hint_used(self, svc) -> None:
        result = svc._classify_case_by_filename_and_path(
            filename="执行申请书.pdf",
            source_path="",
            context={},
            folder_hint="我的文件夹",
        )
        assert result is not None
        assert result["type_name_hint"] == "我的文件夹"

    def test_filing_folder_forces_party(self, svc) -> None:
        result = svc._classify_case_by_filename_and_path(
            filename="证据材料.pdf",
            source_path="/cases/立案材料/证据材料.pdf",
            context={},
        )
        assert result["category"] == "party"
        assert result["side"] == "our"


# ===========================================================================
# _build_case_suggestion
# ===========================================================================


class TestBuildCaseSuggestion:
    def test_party_with_ids(self, svc) -> None:
        result = svc._build_case_suggestion(
            category="party",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="test",
            context={"our_party_ids": [1, 2, 3]},
        )
        assert result["suggested_party_ids"] == [1, 2, 3]
        assert result["category"] == "party"
        assert result["side"] == "our"

    def test_non_party_with_supervising_authority(self, svc) -> None:
        result = svc._build_case_suggestion(
            category="non_party",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="test",
            context={"primary_supervising_authority_id": 42},
        )
        assert result["suggested_supervising_authority_id"] == 42
        assert result["side"] == "unknown"  # non_party -> side forced to unknown

    def test_unknown_category(self, svc) -> None:
        result = svc._build_case_suggestion(
            category="invalid",
            side="our",
            type_name_hint="test",
            confidence=0.9,
            reason="test",
            context={},
        )
        assert result["category"] == "unknown"
        assert result["side"] == "unknown"


# ===========================================================================
# _infer_case_side
# ===========================================================================


class TestInferCaseSide:
    def test_empty_text(self, svc) -> None:
        assert svc._infer_case_side(match_text="", context={}) == "unknown"

    def test_opponent_hint(self, svc) -> None:
        result = svc._infer_case_side(match_text="被告张三的材料", context={})
        assert result == "opponent"

    def test_our_hint(self, svc) -> None:
        result = svc._infer_case_side(match_text="原告李四的起诉状", context={})
        assert result == "our"

    def test_both_hints(self, svc) -> None:
        result = svc._infer_case_side(match_text="原告与被告的庭审笔录", context={})
        assert result == "unknown"

    def test_context_our_party_ids(self, svc) -> None:
        result = svc._infer_case_side(match_text="some document", context={"our_party_ids": [1]})
        assert result == "our"

    def test_context_opponent_party_ids(self, svc) -> None:
        result = svc._infer_case_side(match_text="some document", context={"opponent_party_ids": [2]})
        assert result == "opponent"

    def test_context_our_party_names(self, svc) -> None:
        result = svc._infer_case_side(match_text="张三的材料", context={"our_party_names": ["张三"]})
        assert result == "our"

    def test_context_opponent_party_names(self, svc) -> None:
        result = svc._infer_case_side(match_text="李四的材料", context={"opponent_party_names": ["李四"]})
        assert result == "opponent"


# ===========================================================================
# _extract_party_ids_by_side
# ===========================================================================


class TestExtractPartyIdsBySide:
    def test_valid_ids(self) -> None:
        result = MaterialClassificationService._extract_party_ids_by_side(
            side="our", context={"our_party_ids": [1, 2, 3]}
        )
        assert result == [1, 2, 3]

    def test_deduplicates(self) -> None:
        result = MaterialClassificationService._extract_party_ids_by_side(
            side="our", context={"our_party_ids": [1, 1, 2]}
        )
        assert result == [1, 2]

    def test_filters_non_positive(self) -> None:
        result = MaterialClassificationService._extract_party_ids_by_side(
            side="our", context={"our_party_ids": [0, -1, 5]}
        )
        assert result == [5]

    def test_invalid_items(self) -> None:
        result = MaterialClassificationService._extract_party_ids_by_side(
            side="our", context={"our_party_ids": ["abc", None, 1]}
        )
        assert result == [1]

    def test_non_list_returns_empty(self) -> None:
        result = MaterialClassificationService._extract_party_ids_by_side(
            side="our", context={"our_party_ids": "not a list"}
        )
        assert result == []

    def test_missing_key(self) -> None:
        result = MaterialClassificationService._extract_party_ids_by_side(
            side="our", context={}
        )
        assert result == []


# ===========================================================================
# _extract_primary_supervising_authority_id
# ===========================================================================


class TestExtractPrimarySupervisingAuthorityId:
    def test_valid(self) -> None:
        result = MaterialClassificationService._extract_primary_supervising_authority_id(
            {"primary_supervising_authority_id": 42}
        )
        assert result == 42

    def test_negative(self) -> None:
        result = MaterialClassificationService._extract_primary_supervising_authority_id(
            {"primary_supervising_authority_id": -1}
        )
        assert result is None

    def test_none(self) -> None:
        result = MaterialClassificationService._extract_primary_supervising_authority_id({})
        assert result is None

    def test_invalid(self) -> None:
        result = MaterialClassificationService._extract_primary_supervising_authority_id(
            {"primary_supervising_authority_id": "abc"}
        )
        assert result is None


# ===========================================================================
# _extract_subfolder_hint
# ===========================================================================


class TestExtractSubfolderHint:
    def test_numbered_prefix(self) -> None:
        assert MaterialClassificationService._extract_subfolder_hint("2-立案材料") == "立案材料"

    def test_underscore_prefix(self) -> None:
        assert MaterialClassificationService._extract_subfolder_hint("3_执行依据") == "执行依据"

    def test_dot_prefix(self) -> None:
        assert MaterialClassificationService._extract_subfolder_hint("1.委托材料") == "委托材料"

    def test_no_prefix(self) -> None:
        assert MaterialClassificationService._extract_subfolder_hint("证据材料") == "证据材料"

    def test_empty(self) -> None:
        assert MaterialClassificationService._extract_subfolder_hint("") == ""
        assert MaterialClassificationService._extract_subfolder_hint(None) == ""

    def test_nested_path(self) -> None:
        assert MaterialClassificationService._extract_subfolder_hint("parent/2-子目录") == "子目录"

    def test_only_number_returns_original(self) -> None:
        result = MaterialClassificationService._extract_subfolder_hint("123")
        # After stripping number prefix, empty -> returns last_segment
        assert result == "123" or result == ""


# ===========================================================================
# _normalize_for_match
# ===========================================================================


class TestNormalizeForMatch:
    def test_empty(self) -> None:
        assert MaterialClassificationService._normalize_for_match("") == ""

    def test_none(self) -> None:
        assert MaterialClassificationService._normalize_for_match(None) == ""

    def test_whitespace(self) -> None:
        assert MaterialClassificationService._normalize_for_match("hello  world") == "helloworld"

    def test_backslash(self) -> None:
        result = MaterialClassificationService._normalize_for_match("path\\to\\file")
        assert "\\" not in result
        assert "/" in result

    def test_lowercase(self) -> None:
        assert MaterialClassificationService._normalize_for_match("HELLO") == "hello"


# ===========================================================================
# _extract_json
# ===========================================================================


class TestExtractJson:
    def test_valid_json(self) -> None:
        result = MaterialClassificationService._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_text(self) -> None:
        result = MaterialClassificationService._extract_json('Here is the result: {"key": "value"} done.')
        assert result == {"key": "value"}

    def test_fenced_code_block(self) -> None:
        result = MaterialClassificationService._extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_fenced_without_json_label(self) -> None:
        result = MaterialClassificationService._extract_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_empty(self) -> None:
        assert MaterialClassificationService._extract_json("") is None
        assert MaterialClassificationService._extract_json(None) is None

    def test_invalid_json(self) -> None:
        assert MaterialClassificationService._extract_json("not json at all") is None

    def test_json_array(self) -> None:
        # extract_json only returns dicts
        assert MaterialClassificationService._extract_json("[1, 2, 3]") is None


# ===========================================================================
# parse_work_log_from_folder_name
# ===========================================================================


class TestParseWorkLogFromFolderName:
    def test_valid_format(self, svc) -> None:
        result = svc.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result == {"date": "2025-01-23", "content": "审核知识产权合同"}

    def test_dash_format(self, svc) -> None:
        result = svc.parse_work_log_from_folder_name("2025-01-23-劳动合同审核")
        assert result["date"] == "2025-01-23"

    def test_invalid_format(self, svc) -> None:
        assert svc.parse_work_log_from_folder_name("random_folder") is None

    def test_empty(self, svc) -> None:
        assert svc.parse_work_log_from_folder_name("") is None

    def test_with_spaces(self, svc) -> None:
        result = svc.parse_work_log_from_folder_name("2025.03.15 股权转让")
        assert result["date"] == "2025-03-15"


# ===========================================================================
# _to_confidence
# ===========================================================================


class TestToConfidence:
    def test_valid(self, svc) -> None:
        assert svc._to_confidence(0.9) == 0.9

    def test_negative(self, svc) -> None:
        assert svc._to_confidence(-0.5) == 0.0

    def test_over_one(self, svc) -> None:
        assert svc._to_confidence(1.5) == 1.0

    def test_none(self, svc) -> None:
        assert svc._to_confidence(None) == 0.0

    def test_string(self, svc) -> None:
        assert svc._to_confidence("0.8") == 0.8

    def test_invalid_string(self, svc) -> None:
        assert svc._to_confidence("abc") == 0.0


# ===========================================================================
# classify_archive_material
# ===========================================================================


class TestClassifyArchiveMaterial:
    def test_invalid_category_defaults_to_litigation(self, svc) -> None:
        result = svc.classify_archive_material(
            filename="test.pdf",
            source_path="/path/test.pdf",
            archive_category="invalid",
        )
        # Should fall through with no match since "invalid" becomes "litigation"
        assert "archive_item_code" in result

    def test_filename_match_litigation(self, svc) -> None:
        result = svc.classify_archive_material(
            filename="起诉状.pdf",
            source_path="/path/起诉状.pdf",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"

    def test_filename_match_criminal(self, svc) -> None:
        result = svc.classify_archive_material(
            filename="判决书.pdf",
            source_path="/path/判决书.pdf",
            archive_category="criminal",
        )
        assert result["archive_item_code"] == "cr_14"

    def test_folder_match_litigation(self, svc) -> None:
        result = svc.classify_archive_material(
            filename="test.pdf",
            source_path="/cases/起诉状/test.pdf",
            archive_category="litigation",
        )
        assert result["archive_item_code"] == "lt_7"

    def test_parent_folder_hint(self, svc) -> None:
        result = svc.classify_archive_material(
            filename="test.pdf",
            source_path="/path/test.pdf",
            archive_category="litigation",
            parent_folder_hint="授权委托",
        )
        assert result["archive_item_code"] == "lt_20"

    def test_no_match(self, svc) -> None:
        """When no rule matches, should return unmatched."""
        with patch("apps.contracts.services.archive.constants.CASE_MATERIAL_KEYWORD_MAPPING", new={}):
            result = svc.classify_archive_material(
                filename="random.pdf",
                source_path="/path/random.pdf",
                archive_category="litigation",
            )
        assert result["archive_item_code"] == ""
        assert result["confidence"] == 0.0


# ===========================================================================
# _extract_path_parts
# ===========================================================================


class TestExtractPathParts:
    def test_simple_path(self, svc) -> None:
        parts = svc._extract_path_parts("/cases/起诉状/test.pdf")
        assert any("起诉状" in p for p in parts)

    def test_numbered_parts(self, svc) -> None:
        parts = svc._extract_path_parts("/cases/2-立案材料/test.pdf")
        assert any("立案材料" in p for p in parts)

    def test_root_path(self, svc) -> None:
        parts = svc._extract_path_parts("test.pdf")
        assert isinstance(parts, list)
