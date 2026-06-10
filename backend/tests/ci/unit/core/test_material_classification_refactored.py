"""Tests for refactored pure functions from core/services/material_classification_service.py."""

from __future__ import annotations

import pytest

from apps.core.services.material_classification_service import MaterialClassificationService


class TestNormalizeForMatch:
    """Tests for _normalize_for_match static method."""

    def test_empty_string(self):
        assert MaterialClassificationService._normalize_for_match("") == ""

    def test_none(self):
        assert MaterialClassificationService._normalize_for_match(None) == ""

    def test_whitespace_only(self):
        assert MaterialClassificationService._normalize_for_match("   ") == ""

    def test_lowercase(self):
        assert MaterialClassificationService._normalize_for_match("ABC") == "abc"

    def test_backslash_normalized(self):
        assert MaterialClassificationService._normalize_for_match("a\\b") == "a/b"

    def test_spaces_removed(self):
        assert MaterialClassificationService._normalize_for_match("a b c") == "abc"

    def test_chinese_text(self):
        result = MaterialClassificationService._normalize_for_match("合同纠纷")
        assert result == "合同纠纷"

    def test_mixed_text(self):
        result = MaterialClassificationService._normalize_for_match("合同 纠纷")
        assert result == "合同纠纷"


class TestExtractSubfolderHint:
    """Tests for _extract_subfolder_hint static method."""

    def test_empty_string(self):
        assert MaterialClassificationService._extract_subfolder_hint("") == ""

    def test_none(self):
        assert MaterialClassificationService._extract_subfolder_hint(None) == ""

    def test_simple_name(self):
        assert MaterialClassificationService._extract_subfolder_hint("立案材料") == "立案材料"

    def test_number_prefix_removed(self):
        assert MaterialClassificationService._extract_subfolder_hint("2-立案材料") == "立案材料"

    def test_underscore_prefix_removed(self):
        assert MaterialClassificationService._extract_subfolder_hint("3_执行依据") == "执行依据"

    def test_dot_prefix_removed(self):
        assert MaterialClassificationService._extract_subfolder_hint("1.证据材料") == "证据材料"

    def test_multi_level_path(self):
        result = MaterialClassificationService._extract_subfolder_hint("子目录A/子目录B")
        assert result == "子目录B"

    def test_only_number(self):
        result = MaterialClassificationService._extract_subfolder_hint("1")
        assert result == "1"


class TestExtractJson:
    """Tests for _extract_json static method."""

    def test_empty_string(self):
        assert MaterialClassificationService._extract_json("") is None

    def test_none(self):
        assert MaterialClassificationService._extract_json(None) is None

    def test_valid_json(self):
        result = MaterialClassificationService._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        result = MaterialClassificationService._extract_json('Some text {"key": "value"} more text')
        assert result == {"key": "value"}

    def test_fenced_json(self):
        content = '```json\n{"key": "value"}\n```'
        result = MaterialClassificationService._extract_json(content)
        assert result == {"key": "value"}

    def test_fenced_without_json_tag(self):
        content = '```\n{"key": "value"}\n```'
        result = MaterialClassificationService._extract_json(content)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        assert MaterialClassificationService._extract_json("not json") is None

    def test_non_dict_json(self):
        assert MaterialClassificationService._extract_json("[1, 2, 3]") is None


class TestToConfidence:
    """Tests for _to_confidence method."""

    def setup_method(self):
        self.service = MaterialClassificationService()

    def test_valid_float(self):
        assert self.service._to_confidence(0.5) == 0.5

    def test_zero(self):
        assert self.service._to_confidence(0) == 0.0

    def test_one(self):
        assert self.service._to_confidence(1) == 1.0

    def test_negative_clamped(self):
        assert self.service._to_confidence(-0.5) == 0.0

    def test_above_one_clamped(self):
        assert self.service._to_confidence(1.5) == 1.0

    def test_none(self):
        assert self.service._to_confidence(None) == 0.0

    def test_string_number(self):
        assert self.service._to_confidence("0.8") == 0.8

    def test_invalid_string(self):
        assert self.service._to_confidence("abc") == 0.0

    def test_integer(self):
        assert self.service._to_confidence(1) == 1.0


class TestExtractPartyIdsBySide:
    """Tests for _extract_party_ids_by_side static method."""

    def test_empty_context(self):
        assert MaterialClassificationService._extract_party_ids_by_side(side="our", context={}) == []

    def test_our_side(self):
        context = {"our_party_ids": [1, 2, 3]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2, 3]

    def test_opponent_side(self):
        context = {"opponent_party_ids": [4, 5]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="opponent", context=context)
        assert result == [4, 5]

    def test_invalid_ids_filtered(self):
        context = {"our_party_ids": [1, "abc", -1, 0, 2]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_duplicates_removed(self):
        context = {"our_party_ids": [1, 2, 1, 2]}
        result = MaterialClassificationService._extract_party_ids_by_side(side="our", context=context)
        assert result == [1, 2]

    def test_non_list_returns_empty(self):
        context = {"our_party_ids": "not a list"}
        assert MaterialClassificationService._extract_party_ids_by_side(side="our", context=context) == []


class TestExtractPrimarySupervisingAuthorityId:
    """Tests for _extract_primary_supervising_authority_id static method."""

    def test_valid_id(self):
        context = {"primary_supervising_authority_id": 42}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) == 42

    def test_none(self):
        assert MaterialClassificationService._extract_primary_supervising_authority_id({}) is None

    def test_invalid_value(self):
        context = {"primary_supervising_authority_id": "abc"}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) is None

    def test_negative_value(self):
        context = {"primary_supervising_authority_id": -1}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) is None

    def test_zero(self):
        context = {"primary_supervising_authority_id": 0}
        assert MaterialClassificationService._extract_primary_supervising_authority_id(context) is None


class TestParseWorkLogFromFolderName:
    """Tests for parse_work_log_from_folder_name method."""

    def setup_method(self):
        self.service = MaterialClassificationService()

    def test_valid_format(self):
        result = self.service.parse_work_log_from_folder_name("2025.01.23-知识产权合同")
        assert result == {"date": "2025-01-23", "content": "审核知识产权合同"}

    def test_dash_separator(self):
        result = self.service.parse_work_log_from_folder_name("2025-01-23 合同审核")
        assert result == {"date": "2025-01-23", "content": "审核合同审核"}

    def test_invalid_format(self):
        assert self.service.parse_work_log_from_folder_name("普通文件夹") is None

    def test_empty_string(self):
        assert self.service.parse_work_log_from_folder_name("") is None

    def test_invalid_format_with_numbers(self):
        assert self.service.parse_work_log_from_folder_name("20250123") is None


class TestClassifyContractByFilename:
    """Tests for _classify_contract_by_filename method."""

    def setup_method(self):
        self.service = MaterialClassificationService()

    def test_empty_filename(self):
        assert self.service._classify_contract_by_filename("") is None

    def test_none_filename(self):
        assert self.service._classify_contract_by_filename(None) is None

    def test_supervision_card(self):
        result = self.service._classify_contract_by_filename("律师办案服务质量监督卡.pdf")
        assert result["category"] == "supervision_card"

    def test_supplementary_agreement(self):
        result = self.service._classify_contract_by_filename("补充协议.pdf")
        assert result["category"] == "supplementary_agreement"

    def test_invoice(self):
        result = self.service._classify_contract_by_filename("发票.pdf")
        assert result["category"] == "invoice"

    def test_contract_original(self):
        result = self.service._classify_contract_by_filename("合同.pdf")
        assert result["category"] == "contract_original"

    def test_contract_dispute_excluded(self):
        result = self.service._classify_contract_by_filename("合同纠纷.pdf")
        assert result is None
