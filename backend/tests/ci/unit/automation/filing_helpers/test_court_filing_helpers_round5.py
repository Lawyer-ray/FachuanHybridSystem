"""court_filing_helpers.py — round5 tests for uncovered branches.

Covers:
- _infer_filing_type: execution hint from party statuses, from case name/cause, from CaseMaterial, civil default
- _resolve_original_case_number: fallback when no active, no numbers at all
- _build_party_payloads: third party status
- _apply_execution_party_fallbacks: no fallback phone, address trimming
- _build_agent_payloads: requester_id branch, lawyer with no name, fallback phone overflow
- _build_execution_request_text: generated text with newline cleanup
- _score_slot_deduplicated: primary exclude, secondary weak + exclude
- _match_slot: execution apply hits fallback, delivery address, guarantee fallback
- _build_material_slot_signals: with material_type and attachment
- _resolve_court_name (filing version): already has 人民法院, not found
- _build_session_status_payload: timing with no timing key in result
- _update_session_task: with set_started, set_finished, asyncio path
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── _infer_filing_type ────────────────────────────────────────────────────────


class TestInferFilingType:
    """_infer_filing_type — auto-detect execution vs civil."""

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_from_party_statuses(self, mock_cm):
        from apps.automation.api.court_filing_helpers import _infer_filing_type, _FILING_TYPE_EXECUTION

        party = SimpleNamespace(legal_status="applicant")
        case = SimpleNamespace(name="", cause_of_action="")
        result = _infer_filing_type(case=case, parties=[party])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_from_case_name(self, mock_cm):
        from apps.automation.api.court_filing_helpers import _infer_filing_type, _FILING_TYPE_EXECUTION

        case = SimpleNamespace(name="申请执行案", cause_of_action="")
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_from_cause(self, mock_cm):
        from apps.automation.api.court_filing_helpers import _infer_filing_type, _FILING_TYPE_EXECUTION

        case = SimpleNamespace(name="", cause_of_action="强制执行")
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_execution_from_material_type_name(self, mock_cm):
        from apps.automation.api.court_filing_helpers import _infer_filing_type, _FILING_TYPE_EXECUTION

        mock_qs = MagicMock()
        # The function iterates over `type_names` (a queryset), so we need to make it iterable
        mock_type_name = "执行申请书"
        mock_qs.__iter__ = MagicMock(return_value=iter([mock_type_name]))
        mock_cm.objects.filter.return_value.values_list.return_value = mock_qs
        case = SimpleNamespace(name="", cause_of_action="")
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION

    @patch("apps.cases.models.CaseMaterial")
    def test_civil_default(self, mock_cm):
        from apps.automation.api.court_filing_helpers import _infer_filing_type, _FILING_TYPE_CIVIL

        # patch the queryset to return no material type names
        mock_cm.objects.filter.return_value.values_list.return_value.__iter__ = MagicMock(return_value=iter([]))
        case = SimpleNamespace(name="合同纠纷", cause_of_action="合同纠纷")
        result = _infer_filing_type(case=case, parties=[])
        assert result == _FILING_TYPE_CIVIL


# ── _resolve_original_case_number fallback ────────────────────────────────────


class TestResolveOriginalCaseNumberFallback:
    def test_fallback_when_no_active(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        qs = MagicMock()
        # active returns None
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        # fallback returns a number
        qs.order_by.return_value.values_list.return_value.first.return_value = "(2023)粤01民初99号"
        case = SimpleNamespace(case_numbers=qs)
        result = _resolve_original_case_number(case)
        assert result == "(2023)粤01民初99号"

    def test_empty_when_no_numbers_at_all(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        qs.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=qs)
        result = _resolve_original_case_number(case)
        assert result == ""


# ── _build_party_payloads — third party ───────────────────────────────────────


class TestBuildPartyPayloadsThirdParty:
    @patch("apps.core.utils.id_card_utils.IdCardUtils.extract_gender", return_value="女")
    def test_third_party(self, _mock_gender):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        client = SimpleNamespace(
            client_type="natural", name="王五", address="", phone="",
            id_number="000000000000000000"
        )
        party = SimpleNamespace(client=client, legal_status="third")
        plaintiffs, defendants, thirds = _build_party_payloads([party])
        assert len(thirds) == 1
        assert thirds[0]["name"] == "王五"

    @patch("apps.core.utils.id_card_utils.IdCardUtils.extract_gender", return_value="男")
    def test_empty_status_goes_to_nothing(self, _mock_gender):
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        client = SimpleNamespace(
            client_type="natural", name="赵六", address="", phone="",
            id_number=""
        )
        party = SimpleNamespace(client=client, legal_status="")
        plaintiffs, defendants, thirds = _build_party_payloads([party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 0
        assert len(thirds) == 0


# ── _apply_execution_party_fallbacks — edge cases ─────────────────────────────


class TestApplyExecutionPartyFallbacksEdge:
    def test_no_fallback_phone(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks

        plaintiffs = [{"client_type": "natural", "phone": "", "address": ""}]
        agents = [{"phone": ""}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_address_trimmed(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks

        plaintiffs = [{"client_type": "natural", "phone": "12000000001", "address": "  广州天河  "}]
        agents = []
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["address"] == "广州天河"


# ── _build_agent_payloads — requester and edge cases ──────────────────────────


class TestBuildAgentPayloadsEdge:
    def test_requester_id_added(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        assignment_lawyer = SimpleNamespace(
            id=1, real_name="", username="lawyer1", phone="12000000000",
            id_card="", license_no="", law_firm=SimpleNamespace(name="", address="")
        )
        assignment = SimpleNamespace(lawyer=assignment_lawyer)
        qs_mock = MagicMock()
        qs_mock.select_related.return_value.order_by.return_value = [assignment]

        requester_lawyer = SimpleNamespace(
            id=99, real_name="请求律师", username="", phone="12000000001",
            id_card="", license_no="", law_firm=SimpleNamespace(name="请求所", address="")
        )

        case = SimpleNamespace(assignments=qs_mock)

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = requester_lawyer
            result = _build_agent_payloads(case=case, requester_id=99, parties=[])
        names = [a["name"] for a in result]
        assert "请求律师" in names

    def test_lawyer_with_no_name_skipped(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = SimpleNamespace(
            id=1, real_name="", username="", phone="",
            id_card="", license_no="", law_firm=None
        )
        assignment = SimpleNamespace(lawyer=lawyer)
        qs_mock = MagicMock()
        qs_mock.select_related.return_value.order_by.return_value = [assignment]
        case = SimpleNamespace(assignments=qs_mock)
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert result == []


# ── _score_slot_deduplicated — primary exclude and secondary scoring ──────────


class TestScoreSlotDeduplicatedEdge:
    def test_primary_exclude_penalty(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        score = _score_slot_deduplicated(
            primary_signals=["证据目录"],
            secondary_signals=[],
            strong=("证据",),
            weak=(),
            exclude=("证据目录",),
        )
        assert score < 0

    def test_secondary_weak_and_exclude(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["送达地址确认书", "申请书"],
            strong=("送达地址确认书",),
            weak=("申请书",),
            exclude=("执行申请",),
        )
        # strong(5) + weak(2) = 7
        assert score == 7


# ── _match_slot — fallback branches ───────────────────────────────────────────


class TestMatchSlotEdge:
    def test_execution_apply_hits_returns_slot_0(self):
        from apps.automation.api.court_filing_helpers import _match_slot, _FILING_TYPE_EXECUTION

        material = SimpleNamespace(type_name="执行申请书", type=None, source_attachment=None)
        result = _match_slot(material=material, file_path=Path("/tmp/执行申请书.pdf"), filing_type=_FILING_TYPE_EXECUTION)
        assert result == "0"

    def test_delivery_address_returns_slot_4(self):
        from apps.automation.api.court_filing_helpers import _match_slot, _FILING_TYPE_CIVIL

        material = SimpleNamespace(type_name="送达地址确认书", type=None, source_attachment=None)
        result = _match_slot(material=material, file_path=Path("/tmp/送达地址.pdf"), filing_type=_FILING_TYPE_CIVIL)
        assert result == "4"

    def test_guarantee_returns_slot_5(self):
        from apps.automation.api.court_filing_helpers import _match_slot, _FILING_TYPE_CIVIL

        material = SimpleNamespace(type_name="保全申请", type=None, source_attachment=None)
        result = _match_slot(material=material, file_path=Path("/tmp/保全申请.pdf"), filing_type=_FILING_TYPE_CIVIL)
        assert result == "5"


# ── _build_material_slot_signals — with type and attachment ───────────────────


class TestBuildMaterialSlotSignalsWithAttachments:
    def test_with_material_type(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals

        mat_type = SimpleNamespace(name="起诉状类型")
        attachment_log = SimpleNamespace(content="some log")
        attachment = SimpleNamespace(file=SimpleNamespace(name="test.pdf"), log=attachment_log)
        material = SimpleNamespace(type_name="起诉状", type=mat_type, source_attachment=attachment)
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/tmp/起诉状.pdf")
        )
        assert any("起诉状" in s for s in primary)
        assert any("起诉状类型" in s for s in primary)


# ── _resolve_court_name — filing version ──────────────────────────────────────


class TestResolveCourtNameFiling:
    def test_already_has_renmin(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_not_found_appends_renmin(self, MockCourt):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        MockCourt.objects.filter.return_value.first.return_value = None
        assert _resolve_court_name("天河区") == "天河区人民法院"

    @patch("apps.core.models.Court")
    def test_court_found_returns_name(self, MockCourt):
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        MockCourt.objects.filter.return_value.first.return_value = SimpleNamespace(name="广州市天河区人民法院")
        assert _resolve_court_name("天河") == "广州市天河区人民法院"


# ── _build_session_status_payload — no timing in result ──────────────────────


class TestBuildSessionStatusPayloadNoTiming:
    def test_failed_no_timing(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(id=1, status=ScraperTaskStatus.FAILED, result={}, error_message="err")
        payload = _build_session_status_payload(task=task)
        assert "timing" not in payload

    def test_success_with_timing(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=2, status=ScraperTaskStatus.SUCCESS,
            result={"timing": {"overall_start": 1.0}}, error_message=""
        )
        payload = _build_session_status_payload(task=task)
        assert payload["timing"]["overall_start"] == 1.0


# ── _update_session_task — set_started and set_finished ───────────────────────


class TestUpdateSessionTaskFlags:
    def test_none_session_id_noop(self):
        from apps.automation.api.court_filing_helpers import _update_session_task
        # session_id=None is a noop, no DB access
        _update_session_task(session_id=None, status="running", set_started=True, set_finished=True)

    @pytest.mark.django_db
    def test_set_started_and_finished(self):
        from apps.automation.api.court_filing_helpers import _update_session_task

        with patch("apps.automation.api.court_filing_helpers.timezone") as mock_tz:
            mock_tz.now.return_value = "now"
            with patch("apps.automation.api.court_filing_helpers.asyncio") as mock_asyncio:
                mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
                _update_session_task(
                    session_id=1,
                    status="running",
                    error_message="",
                    result={"key": "val"},
                    set_started=True,
                    set_finished=True,
                )


# ── _build_execution_request_text — newline cleanup ───────────────────────────


class TestBuildExecutionRequestTextNewlineCleanup:
    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_newlines_cleaned(self, mock_svc_cls):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        mock_svc = MagicMock()
        mock_svc.generate.return_value = {"申请执行事项": "line1\aline2\r\nline3\rline4"}
        mock_svc_cls.return_value = mock_svc
        case = SimpleNamespace(id=1)
        result = _build_execution_request_text(case=case)
        assert "\a" not in result
        assert "\r\n" not in result
        assert "\r" not in result

    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_service_raises_type_error_uses_fallback(self, mock_svc_cls):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        mock_svc = MagicMock()
        mock_svc.generate.side_effect = TypeError("bad")
        mock_svc_cls.return_value = mock_svc
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初100号"
        case = SimpleNamespace(id=1, case_numbers=qs)
        result = _build_execution_request_text(case=case)
        assert "执行" in result
