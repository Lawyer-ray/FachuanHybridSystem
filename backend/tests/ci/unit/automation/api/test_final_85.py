"""Coverage tests for automation/api pure helper functions.

Targets uncovered lines in:
- court_filing_helpers.py (156 uncovered)
- court_guarantee_helpers.py (126 uncovered)
- court_filing_schemas.py / court_guarantee_schemas.py
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest


# ---------------------------------------------------------------------------
# court_filing_helpers pure functions
# ---------------------------------------------------------------------------
from apps.automation.api.court_filing_helpers import (
    _FILING_TYPE_CIVIL,
    _FILING_TYPE_EXECUTION,
    _build_execution_reason_text,
    _build_execution_request_text,
    _build_material_slot_signals,
    _build_party_payloads,
    _build_session_status_payload,
    _infer_filing_type,
    _match_slot,
    _normalize_filing_engine,
    _normalize_filing_type,
    _normalize_text,
    _resolve_court_name,
    _resolve_original_case_number,
    _score_slot_deduplicated,
    _score_slot_for_signal,
    _to_valid_mobile,
    _update_session_task,
)

from apps.automation.api.court_guarantee_helpers import (
    _build_cause_candidates,
    _build_party_payload_from_case_party,
    _build_plaintiff_agent_payload,
    _build_primary_respondent_property_clue,
    _build_property_clue_info,
    _build_reusable_quote_options,
    _build_respondent_options,
    _build_selected_respondent_property_clues,
    _extract_quote_company_options,
    _list_opponent_case_parties,
    _list_opponent_party_payloads,
    _list_party_payloads,
    _normalize_consultant_code,
    _normalize_insurance_company,
    _normalize_party_type,
    _normalize_property_clue_content,
    _normalize_property_value,
    _normalize_selected_party_ids,
    _parse_preserve_amount,
    _pick_party_payload,
    _resolve_insurance_company_defaults,
)


# ===================================================================
# court_filing_helpers: _to_valid_mobile
# ===================================================================
class TestToValidMobile:
    def test_valid_mobile(self):
        assert _to_valid_mobile("13812345678") == "13812345678"

    def test_valid_mobile_with_spaces(self):
        assert _to_valid_mobile("138 1234 5678") == "13812345678"

    def test_valid_mobile_with_dashes(self):
        assert _to_valid_mobile("138-1234-5678") == "13812345678"

    def test_invalid_mobile_short(self):
        assert _to_valid_mobile("1381234567") == ""

    def test_invalid_mobile_long(self):
        assert _to_valid_mobile("138123456789") == ""

    def test_invalid_mobile_wrong_prefix(self):
        assert _to_valid_mobile("23812345678") == ""

    def test_empty_string(self):
        assert _to_valid_mobile("") == ""

    def test_none_input(self):
        assert _to_valid_mobile(None) == ""

    def test_non_digit_characters(self):
        assert _to_valid_mobile("abc") == ""

    def test_digits_extraction(self):
        assert _to_valid_mobile("phone: 138-1234-5678 ext.") == "13812345678"


# ===================================================================
# court_filing_helpers: _normalize_text
# ===================================================================
class TestNormalizeText:
    def test_strips_whitespace(self):
        result = _normalize_text("  hello  ")
        assert result == "hello"

    def test_strips_special_chars(self):
        result = _normalize_text("hello-world/test")
        assert result == "helloworldtest"

    def test_strips_punctuation(self):
        result = _normalize_text("hello（）:：test")
        assert result == "hellotest"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_none_input(self):
        assert _normalize_text(None) == ""

    def test_all_special(self):
        assert _normalize_text("-_/\\()") == ""


# ===================================================================
# court_filing_helpers: _score_slot_for_signal
# ===================================================================
class TestScoreSlotForSignal:
    def test_empty_signal(self):
        assert _score_slot_for_signal(signal="", strong=("a",), weak=(), exclude=()) == 0

    def test_strong_match(self):
        signal = _normalize_text("民事起诉状")
        score = _score_slot_for_signal(
            signal=signal, strong=("民事起诉状",), weak=(), exclude=()
        )
        assert score >= 5

    def test_weak_match(self):
        signal = _normalize_text("诉讼请求")
        score = _score_slot_for_signal(
            signal=signal, strong=(), weak=("诉讼请求",), exclude=()
        )
        assert score >= 2

    def test_exclude_penalty(self):
        signal = _normalize_text("执行申请书")
        score = _score_slot_for_signal(
            signal=signal, strong=(), weak=(), exclude=("执行申请书",)
        )
        assert score <= -6

    def test_combined_scoring(self):
        signal = _normalize_text("民事起诉状诉讼请求")
        score = _score_slot_for_signal(
            signal=signal,
            strong=("民事起诉状",),
            weak=("诉讼请求",),
            exclude=("执行申请书",),
        )
        assert score >= 7  # 5 + 2


# ===================================================================
# court_filing_helpers: _normalize_filing_type
# ===================================================================
class TestNormalizeFilingType:
    def test_valid_civil(self):
        assert _normalize_filing_type(requested_filing_type="civil", case=None, parties=[]) == "civil"

    def test_valid_execution(self):
        assert _normalize_filing_type(requested_filing_type="execution", case=None, parties=[]) == "execution"

    def test_case_insensitive(self):
        assert _normalize_filing_type(requested_filing_type="CIVIL", case=None, parties=[]) == "civil"

    def test_none_falls_back_to_infer(self):
        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="civil"):
            result = _normalize_filing_type(requested_filing_type=None, case=MagicMock(), parties=[])
            assert result == "civil"

    def test_empty_string_falls_back(self):
        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="execution"):
            result = _normalize_filing_type(requested_filing_type="", case=MagicMock(), parties=[])
            assert result == "execution"


# ===================================================================
# court_filing_helpers: _normalize_filing_engine
# ===================================================================
class TestNormalizeFilingEngine:
    def test_valid_api(self):
        assert _normalize_filing_engine("api") == "api"

    def test_valid_playwright(self):
        assert _normalize_filing_engine("playwright") == "playwright"

    def test_invalid_defaults_to_api(self):
        assert _normalize_filing_engine("unknown") == "api"

    def test_none_defaults_to_api(self):
        assert _normalize_filing_engine(None) == "api"


# ===================================================================
# court_filing_helpers: _build_execution_reason_text
# ===================================================================
class TestBuildExecutionReasonText:
    def test_with_cause_and_number(self):
        case = SimpleNamespace(cause_of_action="借款合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)粤01民初1号")
        assert "借款合同纠纷" in result
        assert "(2024)粤01民初1号" in result

    def test_without_cause(self):
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)粤01民初1号")
        assert "被执行人未履行" in result
        assert "(2024)粤01民初1号" in result

    def test_without_case_number(self):
        case = SimpleNamespace(cause_of_action="借贷纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result

    def test_none_cause(self):
        case = SimpleNamespace(cause_of_action=None)
        result = _build_execution_reason_text(case=case, original_case_number="test")
        assert "被执行人未履行" in result


# ===================================================================
# court_filing_helpers: _resolve_original_case_number
# ===================================================================
class TestResolveOriginalCaseNumber:
    def test_no_case_numbers_attr(self):
        case = SimpleNamespace()
        assert _resolve_original_case_number(case) == ""

    def test_none_case_numbers(self):
        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_active_number_found(self):
        qs_mock = MagicMock()
        qs_mock.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初1号"
        case = SimpleNamespace(case_numbers=qs_mock)
        result = _resolve_original_case_number(case)
        assert result == "(2024)粤01民初1号"

    def test_fallback_number(self):
        qs_mock = MagicMock()
        qs_mock.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        qs_mock.order_by.return_value.values_list.return_value.first.return_value = "(2023)粤01民初2号"
        case = SimpleNamespace(case_numbers=qs_mock)
        result = _resolve_original_case_number(case)
        assert result == "(2023)粤01民初2号"

    def test_no_numbers_at_all(self):
        qs_mock = MagicMock()
        qs_mock.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        qs_mock.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=qs_mock)
        assert _resolve_original_case_number(case) == ""


# ===================================================================
# court_filing_helpers: _build_session_status_payload
# ===================================================================
class TestBuildSessionStatusPayload:
    def test_pending_status(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=1,
            status=ScraperTaskStatus.PENDING,
            result={"message": "pending msg"},
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert payload["session_id"] == 1

    def test_running_status(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=2,
            status=ScraperTaskStatus.RUNNING,
            result=None,
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"

    def test_success_status(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=3,
            status=ScraperTaskStatus.SUCCESS,
            result={"message": "done", "timing": {"t": 1.0}},
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "completed"
        assert payload["timing"] == {"t": 1.0}

    def test_failed_status_with_error(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=4,
            status=ScraperTaskStatus.FAILED,
            result=None,
            error_message="some error",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "failed"
        assert payload["success"] is False
        assert "some error" in payload["message"]

    def test_failed_no_error_message_fallback(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=5,
            status=ScraperTaskStatus.FAILED,
            result={"message": "result msg"},
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert "result msg" in payload["message"]

    def test_failed_empty_fallback(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=6,
            status=ScraperTaskStatus.FAILED,
            result=None,
            error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert "立案失败" in payload["message"]


# ===================================================================
# court_filing_helpers: _update_session_task
# ===================================================================
class TestUpdateSessionTask:
    def test_none_session_id_does_nothing(self):
        _update_session_task(session_id=None, status="running")

    def test_update_with_all_params(self):
        with patch("apps.automation.api.court_filing_helpers.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.return_value = MagicMock()  # has running loop => executor.submit
            with patch("apps.automation.api.court_filing_helpers._SESSION_UPDATE_EXECUTOR") as mock_exec:
                with patch("apps.automation.api.court_filing_helpers.timezone") as mock_tz:
                    mock_tz.now.return_value = "now"
                    _update_session_task(
                        session_id=1,
                        status="running",
                        error_message="err",
                        result={"key": "value"},
                        set_started=True,
                        set_finished=True,
                    )
                    mock_exec.submit.assert_called_once()


# ===================================================================
# court_filing_helpers: _build_party_payloads
# ===================================================================
class TestBuildPartyPayloads:
    def _make_party(self, client_type="natural", legal_status="plaintiff", **kwargs):
        client_defaults = {
            "client_type": client_type,
            "name": "Test",
            "address": "addr",
            "phone": "13812345678",
            "id_number": "110101199003077715",
            "legal_representative": "",
            "legal_representative_id_number": "",
        }
        client_defaults.update(kwargs)
        client = SimpleNamespace(**client_defaults)
        return SimpleNamespace(client=client, legal_status=legal_status)

    def test_natural_plaintiff(self):
        # Use valid 18-digit id_number so IdCardUtils.extract_gender works
        party = self._make_party(
            client_type="natural",
            legal_status="plaintiff",
            id_number="110101199003077715",
        )
        plaintiffs, defendants, third_parties = _build_party_payloads([party])
        assert len(plaintiffs) == 1
        assert len(defendants) == 0
        assert plaintiffs[0]["gender"] in ("男", "女")

    def test_legal_defendant(self):
        party = self._make_party(
            client_type="legal",
            legal_status="defendant",
            id_number="91440101MA59TEST8X",
            legal_representative="张三",
            legal_representative_id_number="110101199003077715",
        )
        plaintiffs, defendants, third_parties = _build_party_payloads([party])
        assert len(defendants) == 1
        assert defendants[0]["uscc"] == "91440101MA59TEST8X"
        assert defendants[0]["legal_rep"] == "张三"

    def test_third_party(self):
        party = self._make_party(legal_status="third")
        _, _, third_parties = _build_party_payloads([party])
        assert len(third_parties) == 1

    def test_unknown_status_not_included(self):
        party = self._make_party(legal_status="unknown_status")
        plaintiffs, defendants, third_parties = _build_party_payloads([party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 0
        assert len(third_parties) == 0


# ===================================================================
# court_filing_helpers: _score_slot_deduplicated
# ===================================================================
class TestScoreSlotDeduplicated:
    def test_empty_signals(self):
        assert _score_slot_deduplicated(
            primary_signals=[], secondary_signals=[], strong=(), weak=(), exclude=()
        ) == 0

    def test_primary_strong_match(self):
        score = _score_slot_deduplicated(
            primary_signals=["民事起诉状"],
            secondary_signals=[],
            strong=("民事起诉状",),
            weak=(),
            exclude=(),
        )
        assert score >= 10

    def test_secondary_strong_match(self):
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["起诉状.pdf"],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score >= 5

    def test_dedup_secondary_signals(self):
        """Same keyword in multiple secondary signals should count once."""
        score1 = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["起诉状.pdf", "起诉状_backup.pdf"],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        score2 = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["起诉状.pdf"],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score1 == score2  # dedup should prevent double counting

    def test_exclude_penalty_primary(self):
        score = _score_slot_deduplicated(
            primary_signals=["执行申请书"],
            secondary_signals=[],
            strong=(),
            weak=(),
            exclude=("执行申请书",),
        )
        assert score <= -12


# ===================================================================
# court_filing_helpers: _build_material_slot_signals
# ===================================================================
class TestBuildMaterialSlotSignals:
    def test_basic_material(self):
        material = SimpleNamespace(
            type_name="起诉状",
            type=SimpleNamespace(name="民事起诉状"),
            source_attachment=None,
        )
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/tmp/complaint.pdf")
        )
        assert len(primary) > 0
        assert len(secondary) > 0

    def test_no_material_type(self):
        material = SimpleNamespace(
            type_name="证据",
            type=None,
            source_attachment=None,
        )
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/tmp/evidence.pdf")
        )
        assert any("证据" in s for s in primary)


# ===================================================================
# court_filing_helpers: _match_slot
# ===================================================================
class TestMatchSlot:
    def test_civil_complaint(self):
        material = SimpleNamespace(
            type_name="民事起诉状",
            type=SimpleNamespace(name="起诉状"),
            source_attachment=None,
        )
        slot = _match_slot(
            material=material,
            file_path=Path("/tmp/complaint.pdf"),
            filing_type=_FILING_TYPE_CIVIL,
        )
        assert slot == "0"

    def test_civil_id_proof(self):
        material = SimpleNamespace(
            type_name="当事人身份证明",
            type=SimpleNamespace(name="身份证"),
            source_attachment=None,
        )
        slot = _match_slot(
            material=material,
            file_path=Path("/tmp/id.pdf"),
            filing_type=_FILING_TYPE_CIVIL,
        )
        assert slot == "1"

    def test_delivery_confirmation(self):
        material = SimpleNamespace(
            type_name="其他",
            type=None,
            source_attachment=None,
        )
        slot = _match_slot(
            material=material,
            file_path=Path("/tmp/送达地址确认书.pdf"),
            filing_type=_FILING_TYPE_CIVIL,
        )
        assert slot == "4"

    def test_preservation_match(self):
        material = SimpleNamespace(
            type_name="其他",
            type=None,
            source_attachment=None,
        )
        slot = _match_slot(
            material=material,
            file_path=Path("/tmp/保全申请.pdf"),
            filing_type=_FILING_TYPE_CIVIL,
        )
        assert slot == "5"

    def test_execution_type_default(self):
        material = SimpleNamespace(
            type_name="unrelated",
            type=None,
            source_attachment=None,
        )
        slot = _match_slot(
            material=material,
            file_path=Path("/tmp/unrelated.pdf"),
            filing_type=_FILING_TYPE_EXECUTION,
        )
        assert slot in {"0", "1", "2", "3", "4", "5"}


# ===================================================================
# court_guarantee_helpers: _parse_preserve_amount
# ===================================================================
class TestParsePreserveAmount:
    def test_none_returns_none(self):
        assert _parse_preserve_amount(None) is None

    def test_decimal_passthrough(self):
        assert _parse_preserve_amount(Decimal("100000")) == Decimal("100000")

    def test_string_number(self):
        assert _parse_preserve_amount("50000") == Decimal("50000")

    def test_int_value(self):
        assert _parse_preserve_amount(100000) == Decimal("100000")

    def test_float_value(self):
        result = _parse_preserve_amount(50000.5)
        assert result == Decimal("50000.5")

    def test_invalid_string(self):
        assert _parse_preserve_amount("not_a_number") is None

    def test_empty_string(self):
        assert _parse_preserve_amount("") is None


# ===================================================================
# court_guarantee_helpers: _normalize_insurance_company
# ===================================================================
class TestNormalizeInsuranceCompany:
    def test_valid_company(self):
        result = _normalize_insurance_company("中国平安财产保险股份有限公司")
        assert result == "中国平安财产保险股份有限公司"

    def test_empty_name_returns_default(self):
        result = _normalize_insurance_company("")
        assert result == "中国平安财产保险股份有限公司"

    def test_unknown_company_returns_default(self):
        result = _normalize_insurance_company("未知保险公司")
        assert result == "中国平安财产保险股份有限公司"

    def test_custom_allowed_options(self):
        result = _normalize_insurance_company("OptionB", allowed_options=["OptionA", "OptionB"])
        assert result == "OptionB"

    def test_custom_allowed_options_not_found(self):
        result = _normalize_insurance_company("Unknown", allowed_options=["OptionA", "OptionB"])
        assert result == "OptionA"

    def test_empty_with_custom_options(self):
        result = _normalize_insurance_company("  ", allowed_options=["First", "Second"])
        assert result == "First"


# ===================================================================
# court_guarantee_helpers: _normalize_consultant_code
# ===================================================================
class TestNormalizeConsultantCode:
    def test_sunshine_company_default_code(self):
        result = _normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code=None
        )
        assert result == "08740007"

    def test_sunshine_company_custom_code(self):
        result = _normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code="12345"
        )
        assert result == "12345"

    def test_other_company_no_code(self):
        result = _normalize_consultant_code(
            insurance_company_name="中国平安", consultant_code=None
        )
        assert result == ""


# ===================================================================
# court_guarantee_helpers: _normalize_property_clue_content
# ===================================================================
class TestNormalizePropertyClueContent:
    def test_empty(self):
        assert _normalize_property_clue_content("") == ""

    def test_none(self):
        assert _normalize_property_clue_content(None) == ""

    def test_single_line(self):
        assert _normalize_property_clue_content("建设银行尾号1234") == "建设银行尾号1234"

    def test_multiple_lines(self):
        result = _normalize_property_clue_content("建设银行\n工商银行\n农业银行")
        assert result == "建设银行；工商银行；农业银行"

    def test_strips_empty_lines(self):
        result = _normalize_property_clue_content("建设银行\n\n\n工商银行\n")
        assert result == "建设银行；工商银行"


# ===================================================================
# court_guarantee_helpers: _normalize_property_value
# ===================================================================
class TestNormalizePropertyValue:
    def test_none(self):
        assert _normalize_property_value(None) == ""

    def test_integer_string(self):
        assert _normalize_property_value("100000") == "100000"

    def test_decimal_with_zeros(self):
        assert _normalize_property_value("100000.00") == "100000"

    def test_decimal_without_trailing(self):
        assert _normalize_property_value("100000.50") == "100000.5"

    def test_with_commas(self):
        assert _normalize_property_value("100,000.00") == "100000"

    def test_whitespace(self):
        assert _normalize_property_value("  50000  ") == "50000"


# ===================================================================
# court_guarantee_helpers: _build_property_clue_info
# ===================================================================
class TestBuildPropertyClueInfo:
    def test_bank_type(self):
        result = _build_property_clue_info(clue_type="bank", raw_content="建行尾号1234")
        assert "银行账户" in result
        assert "建行尾号1234" in result

    def test_alipay_type(self):
        result = _build_property_clue_info(clue_type="alipay", raw_content="138@example.com")
        assert "支付宝账户" in result

    def test_unknown_type(self):
        result = _build_property_clue_info(clue_type="unknown", raw_content="content")
        assert "unknown" in result or "财产线索" in result

    def test_empty_content(self):
        result = _build_property_clue_info(clue_type="bank", raw_content="")
        assert "银行账户" in result


# ===================================================================
# court_guarantee_helpers: _normalize_party_type
# ===================================================================
class TestNormalizePartyType:
    def test_natural(self):
        assert _normalize_party_type("natural") == "natural"

    def test_person(self):
        assert _normalize_party_type("person") == "natural"

    def test_individual(self):
        assert _normalize_party_type("individual") == "natural"

    def test_legal(self):
        assert _normalize_party_type("legal") == "legal"

    def test_corp(self):
        assert _normalize_party_type("corp") == "legal"

    def test_company(self):
        assert _normalize_party_type("company") == "legal"

    def test_enterprise(self):
        assert _normalize_party_type("enterprise") == "legal"

    def test_organization(self):
        assert _normalize_party_type("organization") == "legal"

    def test_non_legal_org(self):
        assert _normalize_party_type("non_legal_org") == "non_legal_org"

    def test_none_defaults_natural(self):
        assert _normalize_party_type(None) == "natural"

    def test_empty_defaults_natural(self):
        assert _normalize_party_type("") == "natural"

    def test_unknown_defaults_natural(self):
        assert _normalize_party_type("something_else") == "natural"


# ===================================================================
# court_guarantee_helpers: _build_cause_candidates
# ===================================================================
class TestBuildCauseCandidates:
    def test_empty(self):
        assert _build_cause_candidates("") == []

    def test_none(self):
        assert _build_cause_candidates(None) == []

    def test_single_cause(self):
        result = _build_cause_candidates("借款合同纠纷")
        assert "借款合同纠纷" in result
        assert "借款合同" in result  # strips "纠纷"

    def test_multiple_causes_separator(self):
        result = _build_cause_candidates("借款合同纠纷、买卖合同纠纷")
        assert len(result) >= 3

    def test_fullwidth_space(self):
        result = _build_cause_candidates("借款合同　纠纷")
        assert len(result) >= 1

    def test_deduplication(self):
        result = _build_cause_candidates("借款合同纠纷、借款合同纠纷")
        assert result.count("借款合同纠纷") == 1

    def test_max_eight(self):
        result = _build_cause_candidates("A、B、C、D、E、F、G、H、I、J")
        assert len(result) <= 8


# ===================================================================
# court_guarantee_helpers: _normalize_selected_party_ids
# ===================================================================
class TestNormalizeSelectedPartyIds:
    def test_none_returns_none(self):
        assert _normalize_selected_party_ids(None) is None

    def test_valid_ids(self):
        assert _normalize_selected_party_ids([1, 2, 3]) == {1, 2, 3}

    def test_filters_zero_and_negative(self):
        assert _normalize_selected_party_ids([0, -1, 2]) == {2}

    def test_filters_non_numeric(self):
        assert _normalize_selected_party_ids(["abc", 1, None]) == {1}

    def test_empty_list(self):
        assert _normalize_selected_party_ids([]) == set()


# ===================================================================
# court_guarantee_helpers: _list_opponent_case_parties
# ===================================================================
class TestListOpponentCaseParties:
    def test_filters_non_our_client(self):
        p1 = SimpleNamespace(
            client=SimpleNamespace(is_our_client=False), legal_status="defendant"
        )
        p2 = SimpleNamespace(
            client=SimpleNamespace(is_our_client=True), legal_status="plaintiff"
        )
        result = _list_opponent_case_parties(case_parties=[p1, p2])
        assert p1 in result
        assert p2 not in result

    def test_fallback_to_respondent_status(self):
        p1 = SimpleNamespace(
            client=SimpleNamespace(is_our_client=True), legal_status="respondent"
        )
        result = _list_opponent_case_parties(case_parties=[p1])
        assert p1 in result

    def test_fallback_to_all(self):
        p1 = SimpleNamespace(
            client=SimpleNamespace(is_our_client=True), legal_status="plaintiff"
        )
        result = _list_opponent_case_parties(case_parties=[p1])
        assert p1 in result

    def test_empty_list(self):
        assert _list_opponent_case_parties(case_parties=[]) == []


# ===================================================================
# court_guarantee_helpers: _build_party_payload_from_case_party
# ===================================================================
class TestBuildPartyPayloadFromCaseParty:
    def test_natural_party(self):
        client = SimpleNamespace(
            client_type="natural",
            name="张三",
            id_number="110101199003077715",
            phone="13812345678",
            address="北京市朝阳区",
            legal_representative="",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(id=1, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["name"] == "张三"
        assert result["party_type"] == "natural"
        assert result["id_number"] == "110101199003077715"

    def test_legal_party(self):
        client = SimpleNamespace(
            client_type="legal",
            name="某公司",
            id_number="",
            phone="",
            address="",
            legal_representative="李四",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(id=2, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "legal"
        assert result["legal_representative"] == "李四"

    def test_none_party(self):
        result = _build_party_payload_from_case_party(party=None)
        assert result["name"] == "张三"

    def test_missing_id_number_defaults(self):
        client = SimpleNamespace(
            client_type="natural",
            name="王五",
            id_number="",
            phone="",
            address="",
            legal_representative="",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(id=3, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert "110101" in result["id_number"]

    def test_empty_name_defaults(self):
        client = SimpleNamespace(
            client_type="natural",
            name="",
            id_number="",
            phone="",
            address="",
            legal_representative="",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(id=4, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["name"] == "张三"


# ===================================================================
# court_guarantee_helpers: _list_party_payloads
# ===================================================================
class TestListPartyPayloads:
    def _make_party(self, id, status, is_our_client=False, name="Test"):
        client = SimpleNamespace(
            client_type="natural",
            name=name,
            id_number="",
            phone="",
            address="addr",
            legal_representative="",
            legal_representative_id_number="",
            is_our_client=is_our_client,
        )
        return SimpleNamespace(id=id, client=client, legal_status=status)

    def test_prefer_our_plaintiff(self):
        p1 = self._make_party(1, "plaintiff", is_our_client=True)
        p2 = self._make_party(2, "defendant", is_our_client=False)
        result = _list_party_payloads(
            case_parties=[p1, p2],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) >= 1
        assert result[0]["party_id"] == 1

    def test_fallback_to_any_status_match(self):
        p1 = self._make_party(1, "plaintiff", is_our_client=False)
        result = _list_party_payloads(
            case_parties=[p1],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1

    def test_fallback_to_any_our_client(self):
        p1 = self._make_party(1, "defendant", is_our_client=True)
        result = _list_party_payloads(
            case_parties=[p1],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1

    def test_fallback_to_first(self):
        p1 = self._make_party(1, "unknown", is_our_client=False)
        result = _list_party_payloads(
            case_parties=[p1],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1


# ===================================================================
# court_guarantee_helpers: _pick_party_payload
# ===================================================================
class TestPickPartyPayload:
    def test_returns_first_match(self):
        client = SimpleNamespace(
            client_type="natural",
            name="Test",
            id_number="",
            phone="",
            address="addr",
            legal_representative="",
            legal_representative_id_number="",
            is_our_client=True,
        )
        party = SimpleNamespace(id=1, client=client, legal_status="plaintiff")
        result = _pick_party_payload(
            case_parties=[party],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert result["party_id"] == 1

    def test_empty_returns_default(self):
        result = _pick_party_payload(
            case_parties=[],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert result["name"] == "张三"


# ===================================================================
# court_guarantee_helpers: _list_opponent_party_payloads
# ===================================================================
class TestListOpponentPartyPayloads:
    def test_returns_opponent_payloads(self):
        client = SimpleNamespace(
            client_type="natural",
            name="被告",
            id_number="",
            phone="",
            address="addr",
            legal_representative="",
            legal_representative_id_number="",
            is_our_client=False,
        )
        party = SimpleNamespace(id=1, client=client, legal_status="defendant")
        result = _list_opponent_party_payloads(case_parties=[party])
        assert len(result) == 1
        assert result[0]["name"] == "被告"


# ===================================================================
# court_guarantee_helpers: _build_respondent_options
# ===================================================================
class TestBuildRespondentOptions:
    def test_builds_options(self):
        client = SimpleNamespace(
            name="被告A",
            is_our_client=False,
        )
        party = SimpleNamespace(
            id=1,
            client=client,
            legal_status="defendant",
            get_legal_status_display=lambda: "被告",
        )
        result = _build_respondent_options(case_parties=[party])
        assert len(result) == 1
        assert result[0]["party_id"] == 1
        assert result[0]["name"] == "被告A"


# ===================================================================
# court_guarantee_helpers: _extract_quote_company_options
# ===================================================================
class TestExtractQuoteCompanyOptions:
    def test_empty_context(self):
        assert _extract_quote_company_options(quote_context=None) == []

    def test_non_dict_context(self):
        assert _extract_quote_company_options(quote_context="invalid") == []

    def test_no_items(self):
        assert _extract_quote_company_options(quote_context={}) == []

    def test_successful_items_first(self):
        context = {
            "items": [
                {"company_name": "A公司", "status": "failed"},
                {"company_name": "B公司", "status": "success"},
                {"company_name": "C公司", "status": "success"},
            ]
        }
        result = _extract_quote_company_options(quote_context=context)
        assert result[0] == "B公司"
        assert result[1] == "C公司"

    def test_deduplication(self):
        context = {
            "items": [
                {"company_name": "A公司", "status": "success"},
                {"company_name": "A公司", "status": "failed"},
            ]
        }
        result = _extract_quote_company_options(quote_context=context)
        assert result.count("A公司") == 1

    def test_skips_empty_names(self):
        context = {
            "items": [
                {"company_name": "", "status": "success"},
                {"company_name": "B公司", "status": "success"},
            ]
        }
        result = _extract_quote_company_options(quote_context=context)
        assert "" not in result


# ===================================================================
# court_guarantee_helpers: _resolve_insurance_company_defaults
# ===================================================================
class TestResolveInsuranceCompanyDefaults:
    def test_with_recommended(self):
        context = {
            "recommended_company": "A公司",
            "items": [
                {"company_name": "A公司", "status": "success"},
                {"company_name": "B公司", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=context)
        assert default == "A公司"

    def test_without_recommended(self):
        context = {
            "items": [
                {"company_name": "A公司", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=context)
        assert default == "A公司"

    def test_empty_context(self):
        default, options = _resolve_insurance_company_defaults(quote_context=None)
        assert default == "中国平安财产保险股份有限公司"
        assert len(options) > 0


# ===================================================================
# court_guarantee_helpers: _build_plaintiff_agent_payload
# ===================================================================
class TestBuildPlaintiffAgentPayload:
    def test_no_lawyer_uses_fallback(self):
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None
        fallback = {"name": "原告名", "phone": "13812345678"}
        with patch("apps.organization.models.Lawyer") as mock_lawyer:
            mock_lawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=None, fallback_party=fallback
            )
        assert result["party_type"] == "agent"
        assert result["name"] == "原告名"

    def test_with_lawyer(self):
        mock_law_firm = SimpleNamespace(name="测试律所")
        mock_lawyer = SimpleNamespace(
            id=1,
            real_name="律师A",
            username="lawyer_a",
            id_card="110101199003077715",
            phone="13900001111",
            law_firm=mock_law_firm,
            license_no="12345",
        )
        case = SimpleNamespace(assignments=MagicMock())
        with patch("apps.organization.models.Lawyer") as mock_lawyer_cls:
            mock_lawyer_cls.objects.select_related.return_value.filter.return_value.first.return_value = mock_lawyer
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=1, fallback_party={}
            )
        assert result["name"] == "律师A"
        assert result["law_firm"] == "测试律所"


# ===================================================================
# court_guarantee_helpers: _build_primary_respondent_property_clue
# ===================================================================
class TestBuildPrimaryRespondentPropertyClue:
    def test_returns_default_when_no_parties(self):
        with patch(
            "apps.automation.api.court_guarantee_helpers._build_selected_respondent_property_clues",
            return_value=[],
        ):
            result = _build_primary_respondent_property_clue(
                case_parties=[], selected_respondents=[]
            )
        assert result["owner_name"] == "被申请人"

    def test_returns_first_clue(self):
        with patch(
            "apps.automation.api.court_guarantee_helpers._build_selected_respondent_property_clues",
            return_value=[{"owner_name": "张三", "property_type": "其他"}],
        ):
            result = _build_primary_respondent_property_clue(
                case_parties=[], selected_respondents=[]
            )
        assert result["owner_name"] == "张三"


# ===================================================================
# court_guarantee_schemas: _read_int_env
# ===================================================================
class TestReadIntEnv:
    def test_default_value(self):
        from apps.automation.api.court_guarantee_schemas import _read_int_env

        assert _read_int_env("NONEXISTENT_VAR_12345", 42) == 42

    def test_valid_int(self):
        with patch.dict(os.environ, {"TEST_INT_VAR": "100"}):
            from apps.automation.api.court_guarantee_schemas import _read_int_env

            assert _read_int_env("TEST_INT_VAR", 42) == 100

    def test_invalid_int_returns_default(self):
        with patch.dict(os.environ, {"TEST_INT_VAR": "not_a_number"}):
            from apps.automation.api.court_guarantee_schemas import _read_int_env

            assert _read_int_env("TEST_INT_VAR", 42) == 42

    def test_negative_returns_default(self):
        with patch.dict(os.environ, {"TEST_INT_VAR": "-5"}):
            from apps.automation.api.court_guarantee_schemas import _read_int_env

            assert _read_int_env("TEST_INT_VAR", 42) == 42


# ===================================================================
# court_filing_helpers: _build_agent_payloads
# ===================================================================
class TestBuildAgentPayloads:
    def test_no_lawyers(self):
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = []
        parties = []
        with patch("apps.organization.models.Lawyer") as mock_lawyer:
            mock_lawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            from apps.automation.api.court_filing_helpers import _build_agent_payloads

            result = _build_agent_payloads(case=case, requester_id=None, parties=parties)
        assert result == []

    def test_with_lawyer(self):
        mock_law_firm = SimpleNamespace(name="律所", address="地址")
        mock_lawyer = SimpleNamespace(
            id=1,
            real_name="律师A",
            username="lawyer_a",
            id_card="110101199003077715",
            license_no="12345",
            phone="13800001111",
            law_firm=mock_law_firm,
        )
        mock_assignment = SimpleNamespace(lawyer=mock_lawyer)
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = [mock_assignment]
        with patch("apps.organization.models.Lawyer") as mock_lawyer_cls:
            mock_lawyer_cls.objects.select_related.return_value.filter.return_value.first.return_value = None
            from apps.automation.api.court_filing_helpers import _build_agent_payloads

            result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1
        assert result[0]["name"] == "律师A"
        assert result[0]["law_firm"] == "律所"
