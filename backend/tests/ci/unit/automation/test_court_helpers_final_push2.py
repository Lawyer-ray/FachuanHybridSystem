"""Tests for court_filing_helpers and court_guarantee_helpers - pure functions only."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ==================== court_filing_helpers.py ====================


class TestToValidMobile:
    """Test _to_valid_mobile."""

    def test_valid_mobile(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("13812345678") == "13812345678"

    def test_mobile_with_spaces(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("138 1234 5678") == "13812345678"

    def test_invalid_mobile_returns_empty(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("12345") == ""
        assert _to_valid_mobile("23812345678") == ""
        assert _to_valid_mobile("abcdefghijk") == ""

    def test_empty_string(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("") == ""
        assert _to_valid_mobile(None) == ""  # type: ignore[arg-type]


class TestNormalizeFilingEngine:
    """Test _normalize_filing_engine."""

    def test_valid_engine(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        assert _normalize_filing_engine("api") == "api"

    def test_invalid_returns_default(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine, _FILING_ENGINE_API
        assert _normalize_filing_engine("unknown") == _FILING_ENGINE_API

    def test_none_returns_default(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine, _FILING_ENGINE_API
        assert _normalize_filing_engine(None) == _FILING_ENGINE_API


class TestBuildExecutionReasonText:
    """Test _build_execution_reason_text."""

    def test_with_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="借款合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="(2025)粤01执1号")
        assert "借款合同纠纷" in result
        assert "(2025)粤01执1号" in result

    def test_without_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="(2025)粤01执1号")
        assert "生效法律文书确定的义务" in result

    def test_without_case_number(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result


class TestNormalizeText:
    """Test _normalize_text."""

    def test_normalizes(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        result = _normalize_text("  Hello World  ")
        assert result == result.lower().strip()


class TestScoreSlotForSignal:
    """Test _score_slot_for_signal."""

    def test_empty_signal(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        assert _score_slot_for_signal(signal="", strong=("a",), weak=(), exclude=()) == 0

    def test_strong_match(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        assert _score_slot_for_signal(signal="起诉状文书", strong=("起诉状",), weak=(), exclude=()) >= 5

    def test_weak_match(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        assert _score_slot_for_signal(signal="身份证明材料", strong=(), weak=("身份证明",), exclude=()) >= 2

    def test_exclude_penalty(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        assert _score_slot_for_signal(signal="限制高消费申请书", strong=(), weak=(), exclude=("限制高消费",)) < 0


class TestApplyExecutionPartyFallbacks:
    """Test _apply_execution_party_fallbacks."""

    def test_fills_missing_phone(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "广州市"}]
        agents = [{"phone": "13812345678"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13812345678"

    def test_no_override_existing_phone(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "13900000000", "address": "广州市"}]
        agents = [{"phone": "13812345678"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900000000"

    def test_skips_legal_type(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "legal", "phone": "", "address": ""}]
        agents = [{"phone": "13812345678"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""


class TestBuildPartyPayloads:
    """Test _build_party_payloads."""

    def test_legal_defendant(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        client = SimpleNamespace(
            client_type="legal", name="测试公司", address="深圳市南山区",
            phone="075512345678", id_number="91440300MA5F123456",
            legal_representative="李四", legal_representative_id_number="440106199001011234",
        )
        party = SimpleNamespace(client=client, legal_status="defendant")
        plaintiffs, defendants, third_parties = _build_party_payloads([party])
        assert len(defendants) == 1
        assert defendants[0]["uscc"] == "91440300MA5F123456"
        assert defendants[0]["legal_rep"] == "李四"


# ==================== court_guarantee_helpers.py ====================


class TestParsePreserveAmount:
    """Test _parse_preserve_amount."""

    def test_none_returns_none(self):
        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount
        assert _parse_preserve_amount(None) is None

    def test_decimal_passthrough(self):
        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount
        assert _parse_preserve_amount(Decimal("100000")) == Decimal("100000")

    def test_string_to_decimal(self):
        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount
        assert _parse_preserve_amount("50000.50") == Decimal("50000.50")

    def test_invalid_returns_none(self):
        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount
        assert _parse_preserve_amount("abc") is None
        assert _parse_preserve_amount("") is None


class TestNormalizeInsuranceCompany:
    """Test _normalize_insurance_company."""

    def test_empty_returns_first_allowed(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_insurance_company
        assert _normalize_insurance_company("", allowed_options=["A", "B"]) == "A"

    def test_empty_no_allowed_returns_default(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_insurance_company, _DEFAULT_INSURANCE_COMPANY
        assert _normalize_insurance_company("") == _DEFAULT_INSURANCE_COMPANY

    def test_valid_in_allowed(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_insurance_company
        assert _normalize_insurance_company("B", allowed_options=["A", "B"]) == "B"

    def test_not_in_allowed_returns_first(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_insurance_company
        assert _normalize_insurance_company("C", allowed_options=["A", "B"]) == "A"

    def test_not_in_global_returns_default(self):
        from apps.automation.api.court_guarantee_helpers import _DEFAULT_INSURANCE_COMPANY, _normalize_insurance_company
        assert _normalize_insurance_company("UnknownCompanyXYZ") == _DEFAULT_INSURANCE_COMPANY


class TestNormalizeConsultantCode:
    """Test _normalize_consultant_code."""

    def test_non_sunshine_returns_code(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_consultant_code
        result = _normalize_consultant_code(insurance_company_name="平安保险", consultant_code="ABCD")
        assert result == "ABCD"


class TestNormalizePropertyClueContent:
    """Test _normalize_property_clue_content."""

    def test_empty(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_clue_content
        assert _normalize_property_clue_content("") == ""
        assert _normalize_property_clue_content(None) == ""  # type: ignore[arg-type]

    def test_single_line(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_clue_content
        assert _normalize_property_clue_content("银行存款") == "银行存款"

    def test_multiple_lines(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_clue_content
        result = _normalize_property_clue_content("银行存款\n房产\n车辆")
        assert "；" in result


class TestNormalizePropertyValue:
    """Test _normalize_property_value."""

    def test_none(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_value
        assert _normalize_property_value(None) == ""

    def test_with_commas(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_value
        assert _normalize_property_value("1,000,000") == "1000000"

    def test_removes_trailing_zeros(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_value
        assert _normalize_property_value("100.50") == "100.5"


class TestBuildPropertyClueInfo:
    """Test _build_property_clue_info."""

    def test_with_content(self):
        from apps.automation.api.court_guarantee_helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="银行存款", raw_content="招商银行账户")
        assert "银行存款" in result
        assert "招商银行账户" in result

    def test_empty_content(self):
        from apps.automation.api.court_guarantee_helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="房产", raw_content="")
        assert "房产" in result


class TestNormalizePartyType:
    """Test _normalize_party_type."""

    def test_natural(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("natural") == "natural"
        assert _normalize_party_type("person") == "natural"
        assert _normalize_party_type("individual") == "natural"

    def test_legal(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("legal") == "legal"
        assert _normalize_party_type("corp") == "legal"
        assert _normalize_party_type("company") == "legal"
        assert _normalize_party_type("enterprise") == "legal"

    def test_non_legal_org(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("non_legal_org") == "non_legal_org"
        assert _normalize_party_type("nonlegal") == "non_legal_org"

    def test_unknown_defaults_to_natural(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type
        assert _normalize_party_type("unknown") == "natural"
        assert _normalize_party_type("") == "natural"
        assert _normalize_party_type(None) == "natural"  # type: ignore[arg-type]


class TestBuildCauseCandidates:
    """Test _build_cause_candidates."""

    def test_empty(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        assert _build_cause_candidates("") == []
        assert _build_cause_candidates(None) == []  # type: ignore[arg-type]

    def test_single_cause(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        result = _build_cause_candidates("借款合同纠纷")
        assert "借款合同纠纷" in result
        assert "借款合同" in result

    def test_multiple_causes(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates
        result = _build_cause_candidates("借款合同纠纷，买卖合同纠纷")
        assert len(result) > 2


class TestNormalizeSelectedPartyIds:
    """Test _normalize_selected_party_ids."""

    def test_none(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids(None) is None

    def test_valid_ids(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids([1, 2, 3]) == {1, 2, 3}

    def test_filters_invalid(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids([1, 0, -1, 2]) == {1, 2}


class TestExtractQuoteCompanyOptions:
    """Test _extract_quote_company_options."""

    def test_none_context(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context=None) == []

    def test_empty_context(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context={}) == []

    def test_no_items(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context={"items": "not_list"}) == []

    def test_with_items(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options
        context = {
            "items": [
                {"company_name": "平安", "status": "success"},
                {"company_name": "人保", "status": "failed"},
                {"company_name": "平安", "status": "success"},
            ]
        }
        result = _extract_quote_company_options(quote_context=context)
        assert result.count("平安") == 1
        assert result[0] == "平安"  # preferred first

    def test_non_dict_item_skipped(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options
        context = {"items": ["not_a_dict", {"company_name": "Test", "status": "success"}]}
        result = _extract_quote_company_options(quote_context=context)
        assert result == ["Test"]


class TestBuildPartyPayloadFromCaseParty:
    """Test _build_party_payload_from_case_party."""

    def test_natural_party(self):
        from apps.automation.api.court_guarantee_helpers import _build_party_payload_from_case_party
        client = SimpleNamespace(
            client_type="natural", name="张三", id_number="440106199001011234",
            phone="13812345678", address="广州市天河区",
            legal_representative="", legal_representative_id_number="",
        )
        party = SimpleNamespace(id=1, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "natural"
        assert result["name"] == "张三"
        assert result["party_id"] == 1

    def test_none_party(self):
        from apps.automation.api.court_guarantee_helpers import _build_party_payload_from_case_party
        result = _build_party_payload_from_case_party(party=None)
        assert result["name"] == "张三"


class TestListOpponentCaseParties:
    """Test _list_opponent_case_parties."""

    def test_filters_opponents(self):
        from apps.automation.api.court_guarantee_helpers import _list_opponent_case_parties
        our_client = SimpleNamespace(is_our_client=True)
        their_client = SimpleNamespace(is_our_client=False)
        our_party = SimpleNamespace(client=our_client, legal_status="plaintiff")
        their_party = SimpleNamespace(client=their_client, legal_status="defendant")
        result = _list_opponent_case_parties(case_parties=[our_party, their_party])
        assert len(result) == 1
        assert result[0] is their_party

    def test_empty_list(self):
        from apps.automation.api.court_guarantee_helpers import _list_opponent_case_parties
        assert _list_opponent_case_parties(case_parties=[]) == []


class TestResolveInsuranceCompanyDefaults:
    """Test _resolve_insurance_company_defaults."""

    def test_no_quote_options_uses_global(self):
        from apps.automation.api.court_guarantee_helpers import (
            _DEFAULT_INSURANCE_COMPANY, _GUARANTEE_INSURANCE_COMPANY_OPTIONS,
            _resolve_insurance_company_defaults,
        )
        default, options = _resolve_insurance_company_defaults(quote_context=None)
        assert default == _DEFAULT_INSURANCE_COMPANY
        assert options == _GUARANTEE_INSURANCE_COMPANY_OPTIONS
