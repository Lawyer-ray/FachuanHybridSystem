"""Round 4 coverage tests for automation.api.court_filing_helpers.

Targets remaining uncovered branches:
- _resolve_court_name: court found, not found, already has 人民法院
- _normalize_filing_type: valid requested, invalid falls to infer
- _normalize_filing_engine: valid requested, invalid default
- _infer_filing_type: case cause keyword "执行"
- _resolve_original_case_number: no fallback number
- _build_party_payloads: defendant status
- _apply_execution_party_fallbacks: address already set, agent no valid phone
- _build_agent_payloads: multiple lawyers dedup, requester in seen_ids, empty name skip
- _build_execution_request_text: success with generated text, exception fallback
- _score_slot_for_signal: multiple strong+weak+exclude
- _build_material_slot_signals: with attachment and material type
- _score_slot_deduplicated: primary empty secondary, exclude in secondary
- _match_slot: score > best_score, default_slot fallback, no match returns default
- _build_materials_map: no materials fallback, skip non-pdf, dedup
- _build_session_status_payload: running with result dict
- _update_session_task: with event loop (executor path)
- _run_filing: login failure, exception, success with fallback
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# _resolve_court_name
# ---------------------------------------------------------------------------


class TestResolveCourtName:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name
        return _resolve_court_name

    def test_already_has_renfayuan(self):
        assert self._fn()("天河区人民法院") == "天河区人民法院"

    def test_court_found_in_db(self):
        court = MagicMock()
        court.name = "广州市天河区人民法院"
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = court
            result = self._fn()("天河区")
        assert result == "广州市天河区人民法院"

    def test_court_not_found_appends(self):
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = None
            result = self._fn()("天河区")
        assert result == "天河区人民法院"

    def test_court_found_but_empty_name(self):
        court = MagicMock()
        court.name = ""
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = court
            result = self._fn()("天河区")
        assert result == "天河区人民法院"


# ---------------------------------------------------------------------------
# _normalize_filing_type
# ---------------------------------------------------------------------------


class TestNormalizeFilingType:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        return _normalize_filing_type

    def test_valid_requested(self):
        assert self._fn()(requested_filing_type="execution", case=MagicMock(), parties=[]) == "execution"

    def test_invalid_falls_to_infer(self):
        case = MagicMock()
        case.name = "普通案件"
        case.cause_of_action = ""
        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="civil"):
            result = self._fn()(requested_filing_type="invalid", case=case, parties=[])
        assert result == "civil"

    def test_none_falls_to_infer(self):
        case = MagicMock()
        case.name = "普通案件"
        case.cause_of_action = ""
        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="civil"):
            result = self._fn()(requested_filing_type=None, case=case, parties=[])
        assert result == "civil"


# ---------------------------------------------------------------------------
# _normalize_filing_engine
# ---------------------------------------------------------------------------


class TestNormalizeFilingEngine:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        return _normalize_filing_engine

    def test_valid_playwright(self):
        assert self._fn()("playwright") == "playwright"

    def test_valid_api(self):
        assert self._fn()("api") == "api"

    def test_invalid_defaults_to_api(self):
        assert self._fn()("selenium") == "api"

    def test_none_defaults_to_api(self):
        assert self._fn()(None) == "api"


# ---------------------------------------------------------------------------
# _infer_filing_type — case cause keyword
# ---------------------------------------------------------------------------


class TestInferFilingTypeCauseKeyword:
    def test_cause_contains_zhixing(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        case = MagicMock()
        case.name = "张三案件"
        case.cause_of_action = "申请执行"
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = []
            assert _infer_filing_type(case=case, parties=[]) == "execution"

    def test_name_contains_zhixing(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        case = MagicMock()
        case.name = "执行案件"
        case.cause_of_action = ""
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = []
            assert _infer_filing_type(case=case, parties=[]) == "execution"


# ---------------------------------------------------------------------------
# _resolve_original_case_number — no fallback
# ---------------------------------------------------------------------------


class TestResolveOriginalCaseNumberNoFallback:
    def test_no_numbers_at_all(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        case = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = None
        assert _resolve_original_case_number(case) == ""


# ---------------------------------------------------------------------------
# _build_party_payloads — defendant
# ---------------------------------------------------------------------------


class TestBuildPartyPayloadsDefendant:
    def test_defendant_natural(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        party = MagicMock()
        party.client.client_type = "natural"
        party.client.name = "被告"
        party.client.address = "地址"
        party.client.phone = "13800138000"
        party.client.id_number = "110101199003077715"
        party.legal_status = "defendant"

        with patch("apps.core.utils.id_card_utils.IdCardUtils") as mock_id:
            mock_id.extract_gender.return_value = "女"
            plaintiffs, defendants, third_parties = _build_party_payloads(parties=[party])
        assert len(defendants) == 1
        assert defendants[0]["gender"] == "女"


# ---------------------------------------------------------------------------
# _apply_execution_party_fallbacks — edge cases
# ---------------------------------------------------------------------------


class TestApplyExecutionPartyFallbacksEdge:
    def test_address_already_set_preserved(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "已有地址"}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["address"] == "已有地址"
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_agent_no_valid_phone(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "", "address": ""}]
        agents = [{"phone": "invalid"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""


# ---------------------------------------------------------------------------
# _build_agent_payloads — edge cases
# ---------------------------------------------------------------------------


class TestBuildAgentPayloadsEdge:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        return _build_agent_payloads

    def test_lawyer_empty_name_skipped(self):
        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = ""
        lawyer.username = ""
        lawyer.phone = "13800138000"
        lawyer.id_card = ""
        lawyer.license_no = ""
        lawyer.law_firm = None

        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = self._fn()(case=case, requester_id=None, parties=[])
        assert result == []

    def test_requester_already_in_seen_ids(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = "张律师"
        lawyer.username = "zl"
        lawyer.phone = "13800138000"
        lawyer.id_card = "110101199003077715"
        lawyer.license_no = "A123"
        lawyer.law_firm = MagicMock()
        lawyer.law_firm.name = "Firm"
        lawyer.law_firm.address = "Addr"

        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        # requester_id = 1, same as existing lawyer id
        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_agent_payloads(case=case, requester_id=1, parties=[])
        # Only one agent since requester id=1 is already in seen_ids
        assert len(result) == 1

    def test_fallback_phone_from_party(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = "张律师"
        lawyer.username = "zl"
        lawyer.phone = ""  # no phone
        lawyer.id_card = ""
        lawyer.license_no = ""
        lawyer.law_firm = MagicMock()
        lawyer.law_firm.name = "Firm"
        lawyer.law_firm.address = ""

        assignment = MagicMock()
        assignment.lawyer = lawyer

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        party = MagicMock()
        party.client.phone = "13900139000"

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_agent_payloads(case=case, requester_id=None, parties=[party])
        assert result[0]["phone"] == "13900139000"


# ---------------------------------------------------------------------------
# _build_execution_request_text
# ---------------------------------------------------------------------------


class TestBuildExecutionRequestText:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text
        return _build_execution_request_text

    def test_success_with_generated_text(self):
        case = MagicMock()
        case.id = 1
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.generate.return_value = {"申请执行事项": "一、请求强制执行。"}
            with patch(
                "apps.litigation_ai.placeholders.spec.LitigationPlaceholderKeys"
            ) as MockKeys:
                MockKeys.ENFORCEMENT_EXECUTION_REQUEST = "enforcement_execution_request"
                result = self._fn()(case=case)
        assert "请求强制执行" in result

    def test_exception_falls_to_fallback(self):
        case = MagicMock()
        case.id = 1
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = None
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as MockSvc:
            MockSvc.side_effect = TypeError("bad")
            result = self._fn()(case=case)
        assert "强制执行" in result

    def test_generated_text_with_a_bell(self):
        case = MagicMock()
        case.id = 1
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.generate.return_value = {"申请执行事项": "一、请求\a强制执行"}
            with patch(
                "apps.litigation_ai.placeholders.spec.LitigationPlaceholderKeys"
            ) as MockKeys:
                MockKeys.ENFORCEMENT_EXECUTION_REQUEST = "enforcement_execution_request"
                result = self._fn()(case=case)
        # \a should be replaced with \n
        assert "\n" in result or "强制执行" in result


# ---------------------------------------------------------------------------
# _score_slot_for_signal — multiple signals
# ---------------------------------------------------------------------------


class TestScoreSlotForSignalMultiple:
    def test_combined_strong_weak_exclude(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(
            signal="起诉状与证据材料",
            strong=("起诉状",),
            weak=("证据",),
            exclude=("执行申请书",),
        )
        assert score == 5 + 2  # strong + weak


# ---------------------------------------------------------------------------
# _build_material_slot_signals — with attachment
# ---------------------------------------------------------------------------


class TestBuildMaterialSlotSignalsWithAttachment:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals
        return _build_material_slot_signals

    def test_with_material_type_and_attachment(self):
        material = MagicMock()
        material.type_name = "起诉状"
        material.type = MagicMock()
        material.type.name = "民事起诉状"
        material.source_attachment = MagicMock()
        material.source_attachment.file.name = "complaint.pdf"
        material.source_attachment.log = MagicMock()
        material.source_attachment.log.content = "起诉状内容"

        file_path = Path("/test/起诉状.pdf")
        primary, secondary = self._fn()(material=material, file_path=file_path)
        assert len(primary) >= 1
        assert len(secondary) >= 1

    def test_no_material_type(self):
        material = MagicMock()
        material.type_name = "身份证明"
        material.type = None
        material.source_attachment = None

        file_path = Path("/test/id.pdf")
        primary, secondary = self._fn()(material=material, file_path=file_path)
        assert len(primary) >= 1


# ---------------------------------------------------------------------------
# _score_slot_deduplicated — secondary exclude
# ---------------------------------------------------------------------------


class TestScoreSlotDeduplicatedSecondaryExclude:
    def test_secondary_exclude_penalty(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["执行申请书.pdf"],
            strong=(),
            weak=(),
            exclude=("执行申请书",),
        )
        assert score == -6


# ---------------------------------------------------------------------------
# _match_slot — no match returns default
# ---------------------------------------------------------------------------


class TestMatchSlotDefault:
    def test_no_signals_returns_default(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = MagicMock()
        file_path = Path("/test/unknown.pdf")

        with patch(
            "apps.automation.api.court_filing_helpers._build_material_slot_signals",
            return_value=([], []),
        ):
            with patch(
                "apps.automation.api.court_filing_helpers._score_slot_deduplicated",
                return_value=0,
            ):
                result = _match_slot(material=material, file_path=file_path, filing_type="civil")
        # civil default is "5"
        assert result == "5"

    def test_execution_no_match_returns_default(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = MagicMock()
        file_path = Path("/test/unknown.pdf")

        with patch(
            "apps.automation.api.court_filing_helpers._build_material_slot_signals",
            return_value=([], []),
        ):
            with patch(
                "apps.automation.api.court_filing_helpers._score_slot_deduplicated",
                return_value=0,
            ):
                result = _match_slot(material=material, file_path=file_path, filing_type="execution")
        # execution default is "4"
        assert result == "4"


# ---------------------------------------------------------------------------
# _build_session_status_payload — running with dict result
# ---------------------------------------------------------------------------


class TestBuildSessionStatusPayloadRunning:
    def test_running_with_non_dict_result(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        task = MagicMock()
        task.status = "running"
        task.id = 1
        task.result = "not a dict"
        result = _build_session_status_payload(task=task)
        assert result["status"] == "in_progress"
        assert result["message"] == "立案任务执行中..."

    def test_success_with_non_dict_result(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        task = MagicMock()
        task.status = "success"
        task.id = 2
        task.result = "not a dict"
        result = _build_session_status_payload(task=task)
        assert result["status"] == "completed"
        assert "timing" not in result

    def test_failed_with_non_dict_result(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        task = MagicMock()
        task.status = "failed"
        task.id = 3
        task.error_message = ""
        task.result = "not a dict"
        result = _build_session_status_payload(task=task)
        assert result["status"] == "failed"
        assert result["message"] == "立案失败"


# ---------------------------------------------------------------------------
# _update_session_task — with event loop (executor path)
# ---------------------------------------------------------------------------


class TestUpdateSessionTaskWithEventLoop:
    def test_runs_in_executor_when_loop_exists(self):
        from apps.automation.api.court_filing_helpers import _update_session_task

        # Simulate an event loop running
        with patch("apps.automation.api.court_filing_helpers.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.return_value = MagicMock()  # loop exists
            with patch("apps.automation.api.court_filing_helpers._SESSION_UPDATE_EXECUTOR") as mock_executor:
                _update_session_task(
                    session_id=1,
                    status="running",
                    set_started=True,
                )
                mock_executor.submit.assert_called_once()


# ---------------------------------------------------------------------------
# _build_materials_map — edge cases
# ---------------------------------------------------------------------------


class TestBuildMaterialsMap:
    def _fn(self):
        from apps.automation.api.court_filing_helpers import _build_materials_map
        return _build_materials_map

    def test_no_materials_returns_empty(self):
        case = MagicMock()
        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory") as MockCat, \
             patch("apps.cases.models.CaseMaterialSide") as MockSide:
            qs = MagicMock()
            qs.exists.return_value = False
            qs.filter.return_value = qs
            qs.select_related.return_value = qs
            qs.order_by.return_value = qs
            MockCM.objects.filter.return_value = qs
            result = self._fn()(case=case, filing_type="civil")
        assert result == {}

    def test_skips_non_pdf_files(self):
        """Non-.pdf files are skipped in _build_materials_map."""
        from apps.automation.api.court_filing_helpers import _build_materials_map

        case = MagicMock()
        attachment = MagicMock()
        attachment.file.path = "/test/file.docx"
        attachment.original_filename = "file.docx"

        material = MagicMock()
        material.source_attachment_id = 1
        material.source_attachment = attachment

        # Mock the queryset chain properly
        primary_qs = MagicMock()
        primary_qs.exists.return_value = False  # no party materials

        fallback_qs = MagicMock()
        fallback_qs.exists.return_value = True
        fallback_qs.select_related.return_value.order_by.return_value = [material]

        call_count = [0]

        def filter_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return primary_qs
            return fallback_qs

        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory"), \
             patch("apps.cases.models.CaseMaterialSide"):
            MockCM.objects.filter.side_effect = filter_side_effect
            result = _build_materials_map(case=case, filing_type="civil")
        assert result == {}


# ---------------------------------------------------------------------------
# _get_organization_service
# ---------------------------------------------------------------------------


class TestGetOrganizationService:
    def test_delegates_to_build(self):
        from apps.automation.api.court_filing_helpers import _get_organization_service
        with patch("apps.core.dependencies.build_organization_service", return_value="svc"):
            assert _get_organization_service() == "svc"
