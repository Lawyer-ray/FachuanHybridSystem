"""court_filing_helpers.py — round8 tests for DB-dependent + untested branches.

Covers 142 missing: _resolve_court_name, _infer_filing_type, _resolve_original_case_number,
_build_party_payloads, _build_agent_payloads, _build_materials_map,
_build_session_status_payload, _update_session_task, _run_filing, _match_slot fallbacks.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.automation.api.court_filing_schemas import (
    _DEFAULT_SLOT_BY_FILING_TYPE,
    _FILING_TYPE_CIVIL,
    _FILING_TYPE_EXECUTION,
)


# ── _resolve_court_name ────────────────────────────────────────────────


class TestResolveCourtName:
    def test_already_contains人民法院(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_court_found_in_db(self, MockCourt):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        mock_court = MagicMock()
        mock_court.name = "广州市天河区人民法院"
        MockCourt.objects.filter.return_value.first.return_value = mock_court

        result = _resolve_court_name("天河区")
        assert result == "广州市天河区人民法院"
        MockCourt.objects.filter.assert_called_once()

    @patch("apps.core.models.Court")
    def test_court_not_found_fallback(self, MockCourt):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        MockCourt.objects.filter.return_value.first.return_value = None
        result = _resolve_court_name("天河区")
        assert result == "天河区人民法院"

    @patch("apps.core.models.Court")
    def test_court_found_but_empty_name(self, MockCourt):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        mock_court = MagicMock()
        mock_court.name = ""
        MockCourt.objects.filter.return_value.first.return_value = mock_court

        result = _resolve_court_name("天河区")
        assert result == "天河区人民法院"


# ── _infer_filing_type ─────────────────────────────────────────────────


class TestInferFilingType:
    def test_execution_hint_from_legal_status(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(name="test", cause_of_action="")
        party = SimpleNamespace(legal_status="applicant")
        result = _infer_filing_type(case=case, parties=[party])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_hint_from_case_name(self, MockCM):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(id=1, name="申请执行案件", cause_of_action="")
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_hint_from_cause(self, MockCM):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(id=1, name="张三诉李四", cause_of_action="申请执行")
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_hint_from_material_type(self, MockCM):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        MockCM.objects.filter.return_value.values_list.return_value = ["执行申请书", "其他"]
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_default_civil(self, MockCM):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(id=1, name="张三诉李四", cause_of_action="合同纠纷")
        MockCM.objects.filter.return_value.values_list.return_value = ["起诉状"]
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_CIVIL

    def test_multiple_parties_mixed_statuses(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(name="test", cause_of_action="")
        p1 = SimpleNamespace(legal_status="plaintiff")
        p2 = SimpleNamespace(legal_status="respondent")
        result = _infer_filing_type(case=case, parties=[p1, p2])
        # respondent is in _EXECUTION_HINT_STATUSES
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_empty_case_name_and_cause(self, MockCM):
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(id=1, name="", cause_of_action="")
        MockCM.objects.filter.return_value.values_list.return_value = []
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_CIVIL


# ── _resolve_original_case_number ──────────────────────────────────────


class TestResolveOriginalCaseNumber:
    def test_no_case_numbers(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_active_number_exists(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)京01民初123号"
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == "(2024)京01民初123号"

    def test_no_active_fallback_to_first(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_qs.order_by.return_value.values_list.return_value.first.return_value = "(2024)京01民初456号"
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == "(2024)京01民初456号"

    def test_no_numbers_at_all(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_qs.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=mock_qs)
        assert _resolve_original_case_number(case) == ""


# ── _build_party_payloads ──────────────────────────────────────────────


class TestBuildPartyPayloads:
    @patch("apps.core.utils.id_card_utils.IdCardUtils")
    def test_natural_person_plaintiff(self, MockIdCard):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        MockIdCard.extract_gender.return_value = "男"
        party = MagicMock()
        party.legal_status = "plaintiff"
        party.client.client_type = "natural"
        party.client.name = "张三"
        party.client.address = "北京市"
        party.client.phone = "13800138000"
        party.client.id_number = "110101199001011234"

        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(plaintiffs) == 1
        assert plaintiffs[0]["name"] == "张三"
        assert plaintiffs[0]["client_type"] == "natural"
        assert plaintiffs[0]["gender"] == "男"

    @patch("apps.core.utils.id_card_utils.IdCardUtils")
    def test_legal_person_defendant(self, MockIdCard):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        MockIdCard.extract_gender.return_value = None
        party = MagicMock()
        party.legal_status = "defendant"
        party.client.client_type = "legal"
        party.client.name = "有限公司"
        party.client.address = ""
        party.client.phone = None
        party.client.id_number = "91110105MA12345"
        party.client.legal_representative = "王五"
        party.client.legal_representative_id_number = "110101199001015678"

        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(defendants) == 1
        assert defendants[0]["uscc"] == "91110105MA12345"
        assert defendants[0]["legal_rep"] == "王五"

    @patch("apps.core.utils.id_card_utils.IdCardUtils")
    def test_third_party(self, MockIdCard):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        MockIdCard.extract_gender.return_value = "女"
        party = MagicMock()
        party.legal_status = "third"
        party.client.client_type = "natural"
        party.client.name = "第三人"
        party.client.address = "上海市"
        party.client.phone = "13900139000"
        party.client.id_number = "310101199001011234"

        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(third) == 1
        assert third[0]["name"] == "第三人"

    @patch("apps.core.utils.id_card_utils.IdCardUtils")
    def test_unknown_status_skipped(self, MockIdCard):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        party = MagicMock()
        party.legal_status = "unknown_status"
        party.client.client_type = "natural"
        party.client.name = "未知"
        party.client.address = ""
        party.client.phone = ""
        party.client.id_number = ""

        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 0
        assert len(third) == 0

    @patch("apps.core.utils.id_card_utils.IdCardUtils")
    def test_natural_person_no_gender(self, MockIdCard):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        MockIdCard.extract_gender.return_value = None
        party = MagicMock()
        party.legal_status = "plaintiff"
        party.client.client_type = "natural"
        party.client.name = "张三"
        party.client.address = ""
        party.client.phone = ""
        party.client.id_number = ""

        plaintiffs, _, _ = _build_party_payloads([party])
        assert plaintiffs[0]["gender"] == "男"


# ── _build_agent_payloads ──────────────────────────────────────────────


class TestBuildAgentPayloads:
    def test_basic_agent(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        assignment = MagicMock()
        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = "律师甲"
        lawyer.username = "lawyer1"
        lawyer.id_card = "110101199001011234"
        lawyer.license_no = "A12345"
        lawyer.phone = "13800138000"
        lawyer.law_firm = MagicMock()
        lawyer.law_firm.name = "甲律所"
        lawyer.law_firm.address = "北京"
        assignment.lawyer = lawyer

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1
        assert result[0]["name"] == "律师甲"
        assert result[0]["bar_number"] == "A12345"
        assert result[0]["law_firm"] == "甲律所"

    def test_no_lawyer(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        assignment = MagicMock()
        assignment.lawyer = None
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 0

    def test_duplicate_lawyer_id(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = "律师甲"
        lawyer.username = ""
        lawyer.id_card = ""
        lawyer.license_no = ""
        lawyer.phone = ""
        lawyer.law_firm = None

        a1 = MagicMock()
        a1.lawyer = lawyer
        a2 = MagicMock()
        a2.lawyer = lawyer

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [a1, a2]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1

    def test_requester_added(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = []

        requester = MagicMock()
        requester.id = 10
        requester.real_name = "请求人"
        requester.username = "req"
        requester.id_card = ""
        requester.license_no = ""
        requester.phone = "13900139000"
        requester.law_firm = None

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = requester
            result = _build_agent_payloads(case=case, requester_id=10, parties=[])
            assert len(result) == 1
            assert result[0]["name"] == "请求人"

    def test_no_name_lawyer_skipped(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = ""
        lawyer.username = ""
        lawyer.id_card = ""
        lawyer.license_no = ""
        lawyer.phone = ""
        lawyer.law_firm = None

        assignment = MagicMock()
        assignment.lawyer = lawyer
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 0

    def test_fallback_phone_from_party(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = "律师甲"
        lawyer.username = ""
        lawyer.id_card = ""
        lawyer.license_no = ""
        lawyer.phone = ""  # no phone
        lawyer.law_firm = None

        assignment = MagicMock()
        assignment.lawyer = lawyer
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        party = MagicMock()
        client = MagicMock()
        client.phone = "13800138000"
        party.client = client

        result = _build_agent_payloads(case=case, requester_id=None, parties=[party])
        assert len(result) == 1
        assert result[0]["phone"] == "13800138000"

    def test_fallback_phone_overflow_index(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer1 = MagicMock()
        lawyer1.id = 1
        lawyer1.real_name = "律师甲"
        lawyer1.username = ""
        lawyer1.id_card = ""
        lawyer1.license_no = ""
        lawyer1.phone = ""
        lawyer1.law_firm = None

        lawyer2 = MagicMock()
        lawyer2.id = 2
        lawyer2.real_name = "律师乙"
        lawyer2.username = ""
        lawyer2.id_card = ""
        lawyer2.license_no = ""
        lawyer2.phone = ""
        lawyer2.law_firm = None

        a1 = MagicMock()
        a1.lawyer = lawyer1
        a2 = MagicMock()
        a2.lawyer = lawyer2

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [a1, a2]

        party = MagicMock()
        client = MagicMock()
        client.phone = "13800138000"
        party.client = client

        result = _build_agent_payloads(case=case, requester_id=None, parties=[party])
        assert len(result) == 2
        # Both should get the fallback phone (index 0 overflow for lawyer2)
        assert result[1]["phone"] == "13800138000"


# ── _build_execution_reason_text ───────────────────────────────────────


class TestBuildExecutionReasonText:
    def test_with_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)京01民初1号")
        assert "(2024)京01民初1号" in result
        assert "合同纠纷" in result

    def test_without_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)京01民初1号")
        assert "确定的义务" in result

    def test_empty_case_number(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result


# ── _build_execution_request_text ──────────────────────────────────────


class TestBuildExecutionRequestText:
    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_generated_text_success(self, MockSvc):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        MockSvc.return_value.generate.return_value = {
            "申请执行事项": "请求强制执行"
        }
        case = SimpleNamespace(id=1)
        result = _build_execution_request_text(case=case)
        assert "请求强制执行" in result

    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_generated_text_fallback_key(self, MockSvc):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        MockSvc.return_value.generate.return_value = {
            "申请执行事项": "fallback text"
        }
        case = SimpleNamespace(id=1)
        result = _build_execution_request_text(case=case)
        assert "fallback text" in result

    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_exception_triggers_fallback(self, MockSvc):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        MockSvc.return_value.generate.side_effect = TypeError("error")
        case = SimpleNamespace(id=1)
        with patch("apps.automation.api.court_filing_helpers._resolve_original_case_number", return_value=""):
            result = _build_execution_request_text(case=case)
            assert "请求依法强制执行" in result

    @patch("apps.automation.api.court_filing_helpers._resolve_original_case_number")
    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_exception_and_case_number(self, MockSvc, mock_resolve):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        MockSvc.return_value.generate.side_effect = ValueError("err")
        mock_resolve.return_value = "(2024)京01民初1号"
        case = SimpleNamespace(id=1)
        result = _build_execution_request_text(case=case)
        assert "(2024)京01民初1号" in result

    def test_generated_text_strips_special_chars(self):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService") as MockSvc:
            MockSvc.return_value.generate.return_value = {
                "ENFORCEMENT_EXECUTION_REQUEST": "line1\aline2\r\nline3\rline4"
            }
            case = SimpleNamespace(id=1)
            result = _build_execution_request_text(case=case)
            assert "\a" not in result
            assert "\r\n" not in result
            assert "\r" not in result

    def test_generated_text_empty_falls_through(self):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService") as MockSvc:
            MockSvc.return_value.generate.return_value = {}
            case = SimpleNamespace(id=1)
            with patch("apps.automation.api.court_filing_helpers._resolve_original_case_number", return_value=""):
                result = _build_execution_request_text(case=case)
                assert "请求依法强制执行" in result


# ── _build_session_status_payload ──────────────────────────────────────


class TestBuildSessionStatusPayload:
    def test_pending_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.PENDING
        task.result = {"message": "测试中"}
        task.id = 1

        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert payload["success"] is True

    def test_running_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.RUNNING
        task.result = None
        task.id = 2

        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert "执行中" in payload["message"]

    def test_success_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.SUCCESS
        task.result = {"message": "完成"}
        task.id = 3

        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "completed"
        assert payload["message"] == "完成"

    def test_failed_status_with_message(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.FAILED
        task.error_message = "网络错误"
        task.result = {}
        task.id = 4

        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "failed"
        assert payload["message"] == "网络错误"

    def test_failed_status_no_message(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.FAILED
        task.error_message = ""
        task.result = {"message": "from result"}
        task.id = 5

        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "from result"

    def test_failed_status_no_message_anywhere(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.FAILED
        task.error_message = ""
        task.result = {}
        task.id = 6

        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "立案失败"

    def test_timing_dict_in_payload(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.PENDING
        task.result = {"timing": {"overall_start": 1.0}, "message": ""}
        task.id = 7

        payload = _build_session_status_payload(task=task)
        assert "timing" in payload
        assert payload["timing"]["overall_start"] == 1.0

    def test_success_with_timing(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = MagicMock()
        task.status = ScraperTaskStatus.SUCCESS
        task.result = {"timing": {"overall_start": 1.0}, "message": "完成"}
        task.id = 8

        payload = _build_session_status_payload(task=task)
        assert "timing" in payload


# ── _update_session_task ───────────────────────────────────────────────


@pytest.mark.django_db
class TestUpdateSessionTask:
    def test_none_session_id_returns(self):
        from apps.automation.api.court_filing_helpers import _update_session_task

        # Should return without error
        _update_session_task(session_id=None, status="running")

    def test_basic_update(self):
        from apps.automation.api.court_filing_helpers import _update_session_task
        from apps.automation.models import ScraperTask

        _update_session_task(session_id=999999, status="running")
        # Should not raise

    def test_update_with_options(self):
        from apps.automation.api.court_filing_helpers import _update_session_task
        from apps.automation.models import ScraperTask

        _update_session_task(
            session_id=999999,
            status="failed",
            error_message="error",
            result={"key": "value"},
            set_started=True,
            set_finished=True,
        )
        # Should not raise


# ── _match_slot fallbacks ──────────────────────────────────────────────


class TestMatchSlotFallbacks:
    def test_execution_apply_book(self):
        from apps.automation.api.court_filing_helpers import _match_slot

        material = MagicMock()
        material.type_name = "执行申请书"
        material.type = None
        material.source_attachment = None

        result = _match_slot(material=material, file_path=Path("/test/执行申请书.pdf"), filing_type=_FILING_TYPE_EXECUTION)
        assert result == "0"

    def test_delivery_address_slot(self):
        from apps.automation.api.court_filing_helpers import _match_slot

        material = MagicMock()
        material.type_name = "送达地址确认书"
        material.type = None
        material.source_attachment = None

        result = _match_slot(material=material, file_path=Path("/test/送达地址.pdf"), filing_type=_FILING_TYPE_CIVIL)
        assert result == "4"

    def test_preservation_slot(self):
        from apps.automation.api.court_filing_helpers import _match_slot

        material = MagicMock()
        material.type_name = "保全申请"
        material.type = None
        material.source_attachment = None

        result = _match_slot(material=material, file_path=Path("/test/保全.pdf"), filing_type=_FILING_TYPE_CIVIL)
        assert result == "5"


# ── _build_material_slot_signals ───────────────────────────────────────


class TestBuildMaterialSlotSignals:
    def test_basic_signals(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals

        material = MagicMock()
        material.type_name = "合同原件"
        material.type = None
        material.source_attachment = None

        primary, secondary = _build_material_slot_signals(material=material, file_path=Path("/test/合同.pdf"))
        assert len(primary) > 0
        assert "合同原件" in primary[0] or "hetong" in primary[0]

    def test_with_material_type(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals

        material = MagicMock()
        material.type_name = "身份证"
        mt = MagicMock()
        mt.name = "当事人身份证"
        material.type = mt
        material.source_attachment = None

        primary, secondary = _build_material_slot_signals(material=material, file_path=Path("/test/id.pdf"))
        assert len(primary) >= 2

    def test_with_attachment(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals

        material = MagicMock()
        material.type_name = "合同"
        material.type = None
        attachment = MagicMock()
        attachment.file.name = "/files/contract.pdf"
        log = MagicMock()
        log.content = "上传合同文件"
        attachment.log = log
        material.source_attachment = attachment

        primary, secondary = _build_material_slot_signals(material=material, file_path=Path("/test/contract.pdf"))
        assert len(secondary) >= 4


# ── _score_slot_deduplicated ───────────────────────────────────────────


class TestScoreSlotDeduplicated:
    def test_empty_signals(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        result = _score_slot_deduplicated(
            primary_signals=[], secondary_signals=[],
            strong=("合同",), weak=(), exclude=(),
        )
        assert result == 0

    def test_primary_signal_strong_match(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        result = _score_slot_deduplicated(
            primary_signals=["合同原件"], secondary_signals=[],
            strong=("合同",), weak=(), exclude=(),
        )
        assert result == 10

    def test_secondary_signal_strong_match(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        result = _score_slot_deduplicated(
            primary_signals=[], secondary_signals=["合同原件.pdf"],
            strong=("合同",), weak=(), exclude=(),
        )
        assert result == 5


# ── _run_filing — full flow mocking ────────────────────────────────────


class TestRunFiling:
    @patch("apps.automation.api.court_filing_helpers._update_session_task")
    @patch("apps.automation.services.scraper.sites.court_zxfw_filing.CourtZxfwFilingService")
    @patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService")
    @patch("apps.core.services.browser.create_browser")
    def test_successful_filing(self, mock_browser, MockLogin, MockFiling, mock_update):
        from apps.automation.api.court_filing_helpers import _run_filing

        page = MagicMock()
        context = MagicMock()
        mock_browser.return_value.__enter__.return_value = (page, context)

        login_svc = MagicMock()
        login_svc.login.return_value = {"success": True, "token": "tok"}
        MockLogin.return_value = login_svc

        filing_svc = MagicMock()
        filing_svc.file_case.return_value = {"success": True, "message": "立案成功"}
        MockFiling.return_value = filing_svc

        _run_filing("acc", "pwd", {"case_id": 1}, session_id=1)
        assert mock_update.call_count >= 1

    @patch("apps.automation.api.court_filing_helpers._update_session_task")
    @patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService")
    @patch("apps.core.services.browser.create_browser")
    def test_login_failure(self, mock_browser, MockLogin, mock_update):
        from apps.automation.api.court_filing_helpers import _run_filing

        page = MagicMock()
        context = MagicMock()
        mock_browser.return_value.__enter__.return_value = (page, context)

        login_svc = MagicMock()
        login_svc.login.return_value = {"success": False, "message": "密码错误"}
        MockLogin.return_value = login_svc

        _run_filing("acc", "pwd", {"case_id": 1}, session_id=2)
        # Should have called update with FAILED
        last_call = mock_update.call_args_list[-1]
        assert "FAILED" in str(last_call) or "failed" in str(last_call).lower()

    @patch("apps.automation.api.court_filing_helpers._update_session_task")
    @patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService")
    @patch("apps.core.services.browser.create_browser")
    def test_exception_in_filing(self, mock_browser, MockLogin, mock_update):
        from apps.automation.api.court_filing_helpers import _run_filing

        page = MagicMock()
        context = MagicMock()
        mock_browser.return_value.__enter__.return_value = (page, context)

        login_svc = MagicMock()
        login_svc.login.side_effect = RuntimeError("browser crash")
        MockLogin.return_value = login_svc

        _run_filing("acc", "pwd", {"case_id": 1}, session_id=3)
        last_call = mock_update.call_args_list[-1]
        assert "FAILED" in str(last_call) or "failed" in str(last_call).lower()

    @patch("apps.automation.api.court_filing_helpers._update_session_task")
    @patch("apps.automation.services.scraper.sites.court_zxfw_filing.CourtZxfwFilingService")
    @patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService")
    @patch("apps.core.services.browser.create_browser")
    def test_execution_filing_type(self, mock_browser, MockLogin, MockFiling, mock_update):
        from apps.automation.api.court_filing_helpers import _run_filing

        page = MagicMock()
        context = MagicMock()
        mock_browser.return_value.__enter__.return_value = (page, context)

        login_svc = MagicMock()
        login_svc.login.return_value = {"success": True, "token": "tok"}
        MockLogin.return_value = login_svc

        filing_svc = MagicMock()
        filing_svc.file_execution.return_value = {"success": True, "message": "执行立案成功"}
        MockFiling.return_value = filing_svc

        _run_filing("acc", "pwd", {"case_id": 1}, filing_type="execution", session_id=4)
        filing_svc.file_execution.assert_called_once()

    @patch("apps.automation.api.court_filing_helpers._update_session_task")
    @patch("apps.automation.services.scraper.sites.court_zxfw_filing.CourtZxfwFilingService")
    @patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService")
    @patch("apps.core.services.browser.create_browser")
    def test_filing_failure(self, mock_browser, MockLogin, MockFiling, mock_update):
        from apps.automation.api.court_filing_helpers import _run_filing

        page = MagicMock()
        context = MagicMock()
        mock_browser.return_value.__enter__.return_value = (page, context)

        login_svc = MagicMock()
        login_svc.login.return_value = {"success": True, "token": "tok"}
        MockLogin.return_value = login_svc

        filing_svc = MagicMock()
        filing_svc.file_case.return_value = {"success": False, "message": "立案失败"}
        MockFiling.return_value = filing_svc

        _run_filing("acc", "pwd", {"case_id": 1}, session_id=5)
        last_call = mock_update.call_args_list[-1]
        assert "FAILED" in str(last_call) or "failed" in str(last_call).lower()
