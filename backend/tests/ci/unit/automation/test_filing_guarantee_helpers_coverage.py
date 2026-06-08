"""Coverage tests for automation court_filing_helpers and court_guarantee_helpers."""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# --- court_filing_helpers ---

class TestCourtFilingHelpers:
    def test_normalize_filing_type_valid(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type

        result = _normalize_filing_type(requested_filing_type="civil", case=None, parties=[])
        assert result == "civil"

    def test_normalize_filing_type_invalid(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type

        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="civil"):
            result = _normalize_filing_type(requested_filing_type="unknown", case=MagicMock(), parties=[])
            assert result == "civil"

    def test_normalize_filing_engine_valid(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine

        assert _normalize_filing_engine("api") == "api"

    def test_normalize_filing_engine_invalid(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine

        result = _normalize_filing_engine("unknown")
        assert result == "api"

    def test_normalize_filing_engine_none(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine

        result = _normalize_filing_engine(None)
        assert result == "api"

    def test_to_valid_mobile(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile

        assert _to_valid_mobile("12000000000") == "12000000000"
        assert _to_valid_mobile("abc") == ""
        assert _to_valid_mobile("") == ""
        assert _to_valid_mobile("123") == ""

    def test_normalize_text(self):
        from apps.automation.api.court_filing_helpers import _normalize_text

        result = _normalize_text("Hello World")
        assert isinstance(result, str)

    def test_resolve_court_name_with_people_court(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    def test_resolve_court_name_short(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = None
            result = _resolve_court_name("天河区")
            assert "人民法院" in result

    def test_resolve_original_case_number_no_case_numbers(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_build_execution_reason_text(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="借款纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="2025粤01民初1号")
        assert "被执行人" in result

    def test_build_execution_reason_text_no_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_score_slot_for_signal_empty(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal

        assert _score_slot_for_signal(signal="", strong=(), weak=(), exclude=()) == 0

    def test_apply_execution_party_fallbacks(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks

        plaintiffs = [{"client_type": "natural", "phone": "", "address": "北京市"}]
        agents = [{"phone": "12000000000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "12000000000"

    def test_build_session_status_pending(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload

        task = MagicMock()
        task.status = "pending"
        task.id = 1
        task.result = {"message": "running"}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            mock_status.SUCCESS = "success"
            result = _build_session_status_payload(task=task)
            assert result["status"] == "in_progress"


# --- court_guarantee_helpers ---

class TestCourtGuaranteeHelpers:
    def test_normalize_insurance_company_valid(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_insurance_company

        with patch("apps.automation.api.court_guarantee_helpers._GUARANTEE_INSURANCE_COMPANY_OPTIONS", ["阳光财险"]):
            result = _normalize_insurance_company("阳光财险")
            assert result == "阳光财险"

    def test_normalize_insurance_company_empty(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_insurance_company

        with patch("apps.automation.api.court_guarantee_helpers._DEFAULT_INSURANCE_COMPANY", "默认公司"):
            result = _normalize_insurance_company("")
            assert result == "默认公司"

    def test_parse_preserve_amount_none(self):
        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount

        assert _parse_preserve_amount(None) is None

    def test_parse_preserve_amount_decimal(self):
        from decimal import Decimal

        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount

        assert _parse_preserve_amount(Decimal("10000")) == Decimal("10000")

    def test_parse_preserve_amount_string(self):
        from decimal import Decimal

        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount

        assert _parse_preserve_amount("50000") == Decimal("50000")

    def test_parse_preserve_amount_invalid(self):
        from apps.automation.api.court_guarantee_helpers import _parse_preserve_amount

        assert _parse_preserve_amount("abc") is None

    def test_normalize_property_clue_content(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_clue_content

        assert _normalize_property_clue_content("线索1\n线索2") == "线索1；线索2"
        assert _normalize_property_clue_content("") == ""

    def test_normalize_property_value(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_property_value

        assert _normalize_property_value(None) == ""
        assert _normalize_property_value("10000.50") == "10000.5"
        assert _normalize_property_value("10,000") == "10000"

    def test_build_property_clue_info(self):
        from apps.automation.api.court_guarantee_helpers import _build_property_clue_info

        result = _build_property_clue_info(clue_type="bank_account", raw_content="某某银行账户")
        assert "银行" in result or "某某" in result

    def test_build_cause_candidates(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates

        result = _build_cause_candidates("买卖合同纠纷、借款合同纠纷")
        assert len(result) > 0
        assert any("合同纠纷" in c for c in result)

    def test_build_cause_candidates_empty(self):
        from apps.automation.api.court_guarantee_helpers import _build_cause_candidates

        assert _build_cause_candidates("") == []

    def test_normalize_party_type(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_party_type

        assert _normalize_party_type("natural") == "natural"
        assert _normalize_party_type("legal") == "legal"
        assert _normalize_party_type("corp") == "legal"
        assert _normalize_party_type("unknown") == "natural"
        assert _normalize_party_type(None) == "natural"

    def test_normalize_selected_party_ids(self):
        from apps.automation.api.court_guarantee_helpers import _normalize_selected_party_ids

        assert _normalize_selected_party_ids(None) is None
        assert _normalize_selected_party_ids([1, 2, 0]) == {1, 2}

    def test_extract_quote_company_options(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options

        quote_context = {
            "items": [
                {"company_name": "阳光财险", "status": "success"},
                {"company_name": "平安财险", "status": "failed"},
            ]
        }
        result = _extract_quote_company_options(quote_context=quote_context)
        assert "阳光财险" in result

    def test_extract_quote_company_options_empty(self):
        from apps.automation.api.court_guarantee_helpers import _extract_quote_company_options

        assert _extract_quote_company_options(quote_context=None) == []

    def test_resolve_insurance_company_defaults(self):
        from apps.automation.api.court_guarantee_helpers import _resolve_insurance_company_defaults

        result = _resolve_insurance_company_defaults(quote_context=None)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_build_session_status_guarantee_success(self):
        from apps.automation.api.court_guarantee_helpers import _build_session_status_payload

        task = MagicMock()
        task.status = "success"
        task.id = 1
        task.result = {"message": "done"}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            mock_status.SUCCESS = "success"
            result = _build_session_status_payload(task=task)
            assert result["status"] == "completed"
