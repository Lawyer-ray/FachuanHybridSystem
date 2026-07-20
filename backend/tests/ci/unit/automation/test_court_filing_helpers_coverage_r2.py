"""Tests for court_filing_helpers — targeted coverage for uncovered branches."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)

from plugins.court_automation.filing.helpers import (
    _apply_execution_party_fallbacks,
    _build_execution_reason_text,
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
from plugins.court_automation.filing.schemas import _FILING_TYPE_CIVIL, _FILING_TYPE_EXECUTION


class TestResolveCourtName:
    def test_already_contains人民法院(self) -> None:
        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_court_found(self, mock_court_model: Any) -> None:
        mock_qs = MagicMock()
        mock_qs.first.return_value = SimpleNamespace(name="广州市天河区人民法院")
        mock_court_model.objects.filter.return_value = mock_qs
        assert _resolve_court_name("天河区") == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_court_not_found_fallback(self, mock_court_model: Any) -> None:
        mock_qs = MagicMock()
        mock_qs.first.return_value = None
        mock_court_model.objects.filter.return_value = mock_qs
        assert _resolve_court_name("番禺区") == "番禺区人民法院"

    @patch("apps.core.models.Court")
    def test_court_found_no_name(self, mock_court_model: Any) -> None:
        mock_qs = MagicMock()
        mock_qs.first.return_value = SimpleNamespace(name=None)
        mock_court_model.objects.filter.return_value = mock_qs
        assert _resolve_court_name("海珠区") == "海珠区人民法院"


class TestNormalizeFilingType:
    def test_valid_requested(self) -> None:
        case = MagicMock()
        assert _normalize_filing_type(requested_filing_type="civil", case=case, parties=[]) == "civil"
        assert _normalize_filing_type(requested_filing_type="execution", case=case, parties=[]) == "execution"

    def test_invalid_requested_infers(self) -> None:
        case = MagicMock()
        case.name = ""
        case.cause_of_action = ""
        with patch("apps.cases.models.CaseMaterial") as mock_mat:
            mock_mat.objects.filter.return_value.values_list.return_value = []
            assert _normalize_filing_type(requested_filing_type="bad", case=case, parties=[]) == _FILING_TYPE_CIVIL

    def test_none_requested(self) -> None:
        case = MagicMock()
        case.name = ""
        with patch("apps.cases.models.CaseMaterial") as mock_mat:
            mock_mat.objects.filter.return_value.values_list.return_value = []
            assert _normalize_filing_type(requested_filing_type=None, case=case, parties=[]) == _FILING_TYPE_CIVIL

    def test_whitespace_requested(self) -> None:
        case = MagicMock()
        case.name = ""
        case.cause_of_action = ""
        with patch("apps.cases.models.CaseMaterial") as mock_mat:
            mock_mat.objects.filter.return_value.values_list.return_value = []
            assert _normalize_filing_type(requested_filing_type="  civil  ", case=case, parties=[]) == "civil"


class TestNormalizeFilingEngine:
    def test_valid_api(self) -> None:
        assert _normalize_filing_engine("api") == "api"

    def test_valid_playwright(self) -> None:
        assert _normalize_filing_engine("playwright") == "playwright"

    def test_invalid_defaults_to_api(self) -> None:
        assert _normalize_filing_engine("unknown") == "api"

    def test_none_defaults_to_api(self) -> None:
        assert _normalize_filing_engine(None) == "api"


class TestInferFilingType:
    def test_execution_hint_statuses(self) -> None:
        case = MagicMock()
        party1 = SimpleNamespace(legal_status="applicant")
        assert _infer_filing_type(case=case, parties=[party1]) == _FILING_TYPE_EXECUTION

    def test_execution_keyword_in_name(self) -> None:
        case = SimpleNamespace(name="申请执行张三案", cause_of_action="")
        assert _infer_filing_type(case=case, parties=[]) == _FILING_TYPE_EXECUTION

    def test_execution_keyword_in_cause(self) -> None:
        case = SimpleNamespace(name="", cause_of_action="执行异议")
        assert _infer_filing_type(case=case, parties=[]) == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_keyword_in_material_type(self, mock_material: Any) -> None:
        case = SimpleNamespace(name="", cause_of_action="")
        mock_qs = MagicMock()
        mock_qs.values_list.return_value = ["执行申请书"]
        mock_material.objects.filter.return_value = mock_qs
        assert _infer_filing_type(case=case, parties=[]) == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_no_execution_hints_defaults_to_civil(self, mock_material: Any) -> None:
        case = SimpleNamespace(name="合同纠纷", cause_of_action="合同")
        mock_qs = MagicMock()
        mock_qs.values_list.return_value = ["起诉状"]
        mock_material.objects.filter.return_value = mock_qs
        assert _infer_filing_type(case=case, parties=[]) == _FILING_TYPE_CIVIL

    def test_no_execution_status_no_keywords(self) -> None:
        case = SimpleNamespace(name="合同纠纷", cause_of_action="合同")
        party = SimpleNamespace(legal_status="plaintiff")
        with patch("apps.cases.models.CaseMaterial") as mock_mat:
            mock_mat.objects.filter.return_value.values_list.return_value = []
            assert _infer_filing_type(case=case, parties=[party]) == _FILING_TYPE_CIVIL


class TestResolveOriginalCaseNumber:
    def test_case_numbers_none(self) -> None:
        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_active_number_exists(self) -> None:
        active_qs = MagicMock()
        active_qs.order_by.return_value.values_list.return_value.first.return_value = "2024-CA-123"
        case_numbers = MagicMock()
        case_numbers.filter.return_value = active_qs
        case_numbers.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=case_numbers)
        assert _resolve_original_case_number(case) == "2024-CA-123"

    def test_no_active_fallback(self) -> None:
        active_qs = MagicMock()
        active_qs.order_by.return_value.values_list.return_value.first.return_value = None
        fallback_qs = MagicMock()
        fallback_qs.values_list.return_value.first.return_value = "2023-CA-456"
        case_numbers = MagicMock()
        case_numbers.filter.return_value = active_qs
        case_numbers.order_by.return_value = fallback_qs
        case = SimpleNamespace(case_numbers=case_numbers)
        assert _resolve_original_case_number(case) == "2023-CA-456"

    def test_no_numbers_at_all(self) -> None:
        active_qs = MagicMock()
        active_qs.order_by.return_value.values_list.return_value.first.return_value = None
        fallback_qs = MagicMock()
        fallback_qs.values_list.return_value.first.return_value = None
        case_numbers = MagicMock()
        case_numbers.filter.return_value = active_qs
        case_numbers.order_by.return_value = fallback_qs
        case = SimpleNamespace(case_numbers=case_numbers)
        assert _resolve_original_case_number(case) == ""


class TestToValidMobile:
    def test_valid_mobile(self) -> None:
        assert _to_valid_mobile("13800138000") == "13800138000"

    def test_with_prefix(self) -> None:
        assert _to_valid_mobile("+86-13800138000") == ""

    def test_invalid_too_short(self) -> None:
        assert _to_valid_mobile("13800138") == ""

    def test_invalid_not_start_with_1(self) -> None:
        assert _to_valid_mobile("23800138000") == ""

    def test_empty(self) -> None:
        assert _to_valid_mobile("") == ""


class TestNormalizeText:
    def test_basic(self) -> None:
        result = _normalize_text("  Hello World  ")
        assert result == "helloworld"

    def test_special_chars(self) -> None:
        result = _normalize_text("Hello-World_Foo.Bar")
        assert result == "helloworldfoobar"

    def test_chinese(self) -> None:
        result = _normalize_text("民事 起诉状")
        assert result == "民事起诉状"


class TestScoreSlotForSignal:
    def test_empty_signal(self) -> None:
        assert _score_slot_for_signal(signal="", strong=("a",), weak=("b",), exclude=("c",)) == 0

    def test_strong_match(self) -> None:
        score = _score_slot_for_signal(signal="民事起诉状", strong=("起诉状",), weak=(), exclude=())
        assert score == 5

    def test_weak_match(self) -> None:
        score = _score_slot_for_signal(signal="事实与理由", strong=(), weak=("事实",), exclude=())
        assert score == 2

    def test_exclude_match(self) -> None:
        score = _score_slot_for_signal(signal="执行申请书", strong=("执行申请书",), weak=(), exclude=("限制高消费",))
        assert score >= 5


class TestBuildMaterialSlotSignals:
    def test_basic_signals(self) -> None:
        material = SimpleNamespace(type_name="起诉状", type=None, source_attachment=None)
        file_path = Path("/data/cases/test.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert "起诉状" in primary
        assert any("testpdf" in s for s in secondary)

    def test_with_material_type(self) -> None:
        mat_type = SimpleNamespace(name="身份证")
        material = SimpleNamespace(type_name="", type=mat_type, source_attachment=None)
        file_path = Path("/data/test.pdf")
        primary, _ = _build_material_slot_signals(material=material, file_path=file_path)
        assert "身份证" in primary

    def test_with_attachment(self) -> None:
        att_file = SimpleNamespace(name="uploads/test.pdf")
        att_log = SimpleNamespace(content="some log")
        attachment = SimpleNamespace(file=att_file, log=att_log)
        material = SimpleNamespace(type_name="合同", type=None, source_attachment=attachment)
        file_path = Path("/data/test.pdf")
        _, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert any("testpdf" in s for s in secondary)

    def test_deduplication(self) -> None:
        material = SimpleNamespace(type_name="合同", type=None, source_attachment=None)
        file_path = Path("/data/test.pdf")
        primary, _ = _build_material_slot_signals(material=material, file_path=file_path)
        assert len(primary) == len(set(primary))


class TestScoreSlotDeduplicated:
    def test_empty_signals(self) -> None:
        assert _score_slot_deduplicated(
            primary_signals=[], secondary_signals=[], strong=("a",), weak=("b",), exclude=("c",)
        ) == 0

    def test_primary_strong_match(self) -> None:
        score = _score_slot_deduplicated(
            primary_signals=["起诉状"], secondary_signals=[], strong=("起诉状",), weak=(), exclude=()
        )
        assert score == 10

    def test_primary_weak_match(self) -> None:
        score = _score_slot_deduplicated(
            primary_signals=["事实与理由"], secondary_signals=[], strong=(), weak=("事实",), exclude=()
        )
        assert score == 4

    def test_secondary_strong_match(self) -> None:
        score = _score_slot_deduplicated(
            primary_signals=[], secondary_signals=["起诉状.pdf"], strong=("起诉状",), weak=(), exclude=()
        )
        assert score == 5

    def test_secondary_dedup(self) -> None:
        score = _score_slot_deduplicated(
            primary_signals=[], secondary_signals=["起诉状.pdf", "起诉状_backup.pdf"],
            strong=("起诉状",), weak=(), exclude=(),
        )
        assert score == 5


class TestMatchSlot:
    def test_civil_default(self) -> None:
        material = SimpleNamespace(type_name="其他", type=None, source_attachment=None)
        file_path = Path("/data/other.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type=_FILING_TYPE_CIVIL)
        assert isinstance(slot, str)

    def test_execution_fallback_delivery_address(self) -> None:
        material = SimpleNamespace(type_name="送达地址确认书", type=None, source_attachment=None)
        file_path = Path("/data/addr.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type=_FILING_TYPE_EXECUTION)
        assert slot in ("4", "0", "5")


class TestBuildPartyPayloads:
    def test_natural_person(self) -> None:
        client = SimpleNamespace(
            client_type="natural", name="Zhang", address="GZ", phone="13800138000",
            id_number="440106199001011234", legal_representative="", legal_representative_id_number="",
        )
        party = SimpleNamespace(client=client, legal_status="plaintiff")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(plaintiffs) == 1
        assert plaintiffs[0]["client_type"] == "natural"

    def test_legal_person(self) -> None:
        client = SimpleNamespace(
            client_type="company", name="GZ Tech", address="TH", phone="020-1234",
            id_number="91440100MA5XXXXX", legal_representative="Li", legal_representative_id_number="440106199001011234",
        )
        party = SimpleNamespace(client=client, legal_status="defendant")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(defendants) == 1
        assert defendants[0]["client_type"] == "legal"
        assert defendants[0]["uscc"] == "91440100MA5XXXXX"

    def test_third_party(self) -> None:
        client = SimpleNamespace(
            client_type="natural", name="Wang", address="", phone="", id_number="",
            legal_representative="", legal_representative_id_number="",
        )
        party = SimpleNamespace(client=client, legal_status="third")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(third) == 1

    def test_unknown_status(self) -> None:
        client = SimpleNamespace(
            client_type="natural", name="X", address="", phone="", id_number="",
            legal_representative="", legal_representative_id_number="",
        )
        party = SimpleNamespace(client=client, legal_status="other")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 0
        assert len(third) == 0


class TestBuildSessionStatusPayload:
    def test_pending_status(self) -> None:
        task = SimpleNamespace(status="pending", id=1, result=None, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert payload["success"] is True

    def test_running_with_result_message(self) -> None:
        task = SimpleNamespace(status="running", id=2, result={"message": "Processing..."}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "Processing..."

    def test_running_with_timing(self) -> None:
        task = SimpleNamespace(status="running", id=3, result={"message": "ok", "timing": {"start": 1.0}}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload

    def test_success_status(self) -> None:
        task = SimpleNamespace(status="success", id=4, result={"message": "Done"}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "completed"
        assert payload["success"] is True

    def test_success_with_timing(self) -> None:
        task = SimpleNamespace(status="success", id=5, result={"timing": {"start": 1.0}}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload

    def test_failed_with_error_message(self) -> None:
        task = SimpleNamespace(status="failed", id=6, result=None, error_message="Login failed")
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is False

    def test_failed_no_message_fallback(self) -> None:
        task = SimpleNamespace(status="failed", id=7, result={"message": "Internal error"}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "Internal error"

    def test_failed_empty_result_message(self) -> None:
        task = SimpleNamespace(status="failed", id=8, result={"message": ""}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "立案失败"

    def test_failed_with_timing(self) -> None:
        task = SimpleNamespace(status="failed", id=9, result={"timing": {"start": 1.0}}, error_message="err")
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload


class TestBuildExecutionReasonText:
    def test_with_cause(self) -> None:
        case = SimpleNamespace(cause_of_action="contract dispute")
        result = _build_execution_reason_text(case=case, original_case_number="2024-CA-123")
        assert "contract dispute" in result
        assert "2024-CA-123" in result

    def test_without_cause(self) -> None:
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="2024-CA-123")
        assert "2024-CA-123" in result

    def test_empty_case_number(self) -> None:
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result


class TestApplyExecutionPartyFallbacks:
    def test_phone_fallback(self) -> None:
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "GZ"}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_no_fallback_needed(self) -> None:
        plaintiffs = [{"client_type": "natural", "phone": "13900139000", "address": "GZ"}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900139000"

    def test_legal_person_skipped(self) -> None:
        plaintiffs = [{"client_type": "legal", "phone": ""}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""


class TestUpdateSessionTask:
    def test_none_session_id(self) -> None:
        _update_session_task(session_id=None, status="running")

    @patch("apps.automation.models.ScraperTask")
    @patch("django.db.close_old_connections")
    def test_basic_update(self, mock_close: Any, mock_task_cls: Any) -> None:
        mock_qs = MagicMock()
        mock_task_cls.objects.filter.return_value = mock_qs
        _update_session_task(session_id=1, status="running", set_started=True)
        mock_task_cls.objects.filter.assert_called_once_with(id=1)
        mock_qs.update.assert_called_once()

    @patch("apps.automation.models.ScraperTask")
    @patch("django.db.close_old_connections")
    def test_update_with_finished(self, mock_close: Any, mock_task_cls: Any) -> None:
        mock_qs = MagicMock()
        mock_task_cls.objects.filter.return_value = mock_qs
        _update_session_task(session_id=2, status="success", error_message="", result={"key": "val"}, set_started=True, set_finished=True)
        mock_task_cls.objects.filter.assert_called_once_with(id=2)
        mock_qs.update.assert_called_once()
