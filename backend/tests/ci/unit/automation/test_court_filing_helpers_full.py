"""Full coverage tests for apps.automation.api.court_filing_helpers."""

from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helper to create fake party objects
# ---------------------------------------------------------------------------

def _make_party(
    *,
    party_id: int = 1,
    legal_status: str = "plaintiff",
    client_type: str = "natural",
    name: str = "张三",
    id_number: str = "110101199003077715",
    phone: str = "13800138000",
    address: str = "北京市",
    legal_rep: str = "",
    legal_rep_id: str = "",
    is_our_client: bool = True,
) -> SimpleNamespace:
    client = SimpleNamespace(
        id=party_id * 10,
        client_type=client_type,
        name=name,
        id_number=id_number,
        phone=phone,
        address=address,
        legal_representative=legal_rep,
        legal_representative_id_number=legal_rep_id,
        is_our_client=is_our_client,
    )
    return SimpleNamespace(id=party_id, legal_status=legal_status, client=client)


# ======================================================================
# _normalize_filing_type
# ======================================================================

class TestNormalizeFilingType:
    def test_valid_civil(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        result = _normalize_filing_type(requested_filing_type="civil", case=None, parties=[])
        assert result == "civil"

    def test_valid_execution(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        result = _normalize_filing_type(requested_filing_type="execution", case=None, parties=[])
        assert result == "execution"

    def test_invalid_falls_to_infer(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="civil"):
            result = _normalize_filing_type(requested_filing_type="bogus", case=MagicMock(), parties=[])
            assert result == "civil"

    def test_none_falls_to_infer(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="execution"):
            result = _normalize_filing_type(requested_filing_type=None, case=MagicMock(), parties=[])
            assert result == "execution"

    def test_case_insensitive(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        result = _normalize_filing_type(requested_filing_type="CIVIL", case=None, parties=[])
        assert result == "civil"


# ======================================================================
# _normalize_filing_engine
# ======================================================================

class TestNormalizeFilingEngine:
    def test_valid_api(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        assert _normalize_filing_engine("api") == "api"

    def test_valid_playwright(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        assert _normalize_filing_engine("playwright") == "playwright"

    def test_invalid_defaults_to_api(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        assert _normalize_filing_engine("unknown") == "api"

    def test_none_defaults_to_api(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        assert _normalize_filing_engine(None) == "api"


# ======================================================================
# _resolve_court_name
# ======================================================================

class TestResolveCourtName:
    def test_already_has_people_court(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name
        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    def test_found_in_db(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name
        mock_court = SimpleNamespace(name="北京市朝阳区人民法院")
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = mock_court
            result = _resolve_court_name("朝阳区")
            assert result == "北京市朝阳区人民法院"

    def test_not_in_db_appends_suffix(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = None
            result = _resolve_court_name("天河区")
            assert result == "天河区人民法院"


# ======================================================================
# _infer_filing_type
# ======================================================================

class TestInferFilingType:
    def test_execution_by_status(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        party = _make_party(legal_status="applicant")
        result = _infer_filing_type(case=SimpleNamespace(name="", cause_of_action=""), parties=[party])
        assert result == "execution"

    def test_execution_by_cause_keyword(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        case = SimpleNamespace(name="某案", cause_of_action="申请执行")
        result = _infer_filing_type(case=case, parties=[])
        assert result == "execution"

    def test_execution_by_material_type_name(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        case = SimpleNamespace(name="普通案", cause_of_action="借款纠纷")
        mock_material = SimpleNamespace(type_name="执行申请书")
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = ["执行申请书"]
            result = _infer_filing_type(case=case, parties=[])
            assert result == "execution"

    def test_civil_default(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        case = SimpleNamespace(name="普通案", cause_of_action="借款纠纷")
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[])
            assert result == "civil"


# ======================================================================
# _resolve_original_case_number
# ======================================================================

class TestResolveOriginalCaseNumber:
    def test_no_case_numbers(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_active_number(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "2025粤01民初1号"
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == "2025粤01民初1号"

    def test_fallback_number(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_qs.order_by.return_value.values_list.return_value.first.return_value = "2025粤02民初2号"
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == "2025粤02民初2号"

    def test_no_numbers_at_all(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_qs.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=mock_qs)
        assert _resolve_original_case_number(case) == ""


# ======================================================================
# _build_party_payloads
# ======================================================================

class TestBuildPartyPayloads:
    def test_natural_plaintiff(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        party = _make_party(legal_status="plaintiff", client_type="natural")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(plaintiffs) == 1
        assert plaintiffs[0]["client_type"] == "natural"
        assert plaintiffs[0]["name"] == "张三"
        assert len(defendants) == 0

    def test_legal_defendant(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        party = _make_party(
            legal_status="defendant",
            client_type="legal",
            name="某公司",
            id_number="91440101MA59TEST8X",
            legal_rep="李四",
            legal_rep_id="110101199003077715",
        )
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(defendants) == 1
        assert defendants[0]["uscc"] == "91440101MA59TEST8X"
        assert defendants[0]["legal_rep"] == "李四"

    def test_third_party(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        party = _make_party(legal_status="third")
        _, _, third = _build_party_payloads([party])
        assert len(third) == 1

    def test_unknown_status_excluded(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        party = _make_party(legal_status="unknown_role")
        p, d, t = _build_party_payloads([party])
        assert len(p) == 0 and len(d) == 0 and len(t) == 0


# ======================================================================
# _to_valid_mobile
# ======================================================================

class TestToValidMobile:
    def test_valid(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("13800138000") == "13800138000"

    def test_with_spaces(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("138 0013 8000") == "13800138000"

    def test_invalid_short(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("123") == ""

    def test_invalid_starts_with_wrong_digit(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("23800138000") == ""

    def test_empty(self):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile("") == ""


# ======================================================================
# _apply_execution_party_fallbacks
# ======================================================================

class TestApplyExecutionPartyFallbacks:
    def test_fills_phone_from_agent(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "北京"}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_skips_non_natural(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "legal", "phone": "", "address": ""}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_no_fallback_when_phone_exists(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "13900139000", "address": ""}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900139000"

    def test_preserves_address(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "  上海  "}]
        agents = []
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["address"] == "上海"


# ======================================================================
# _build_agent_payloads
# ======================================================================

class TestBuildAgentPayloads:
    def test_builds_from_assignment(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        law_firm = SimpleNamespace(name="测试律师事务所", address="广州天河")
        lawyer = SimpleNamespace(
            id=1, real_name="王律师", username="wang", id_card="110101199003077715",
            license_no="12345", phone="13800138000", law_firm=law_firm,
        )
        assignment = SimpleNamespace(lawyer=lawyer)
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1
        assert result[0]["name"] == "王律师"
        assert result[0]["law_firm"] == "测试律师事务所"

    def test_deduplicates_lawyers(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        lawyer = SimpleNamespace(
            id=1, real_name="王律师", username="wang", id_card="110101199003077715",
            license_no="12345", phone="13800138000", law_firm=SimpleNamespace(name="所", address=""),
        )
        assignment1 = SimpleNamespace(lawyer=lawyer)
        assignment2 = SimpleNamespace(lawyer=lawyer)
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = [assignment1, assignment2]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1

    def test_uses_fallback_phone_from_party(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        lawyer = SimpleNamespace(
            id=1, real_name="王律师", username="wang", id_card="",
            license_no="12345", phone="", law_firm=SimpleNamespace(name="所", address=""),
        )
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = [SimpleNamespace(lawyer=lawyer)]
        party = _make_party(phone="13900139000")

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_agent_payloads(case=case, requester_id=None, parties=[party])
            assert result[0]["phone"] == "13900139000"

    def test_skips_lawyer_without_name(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        lawyer = SimpleNamespace(
            id=1, real_name="", username="", id_card="",
            license_no="", phone="", law_firm=None,
        )
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = [SimpleNamespace(lawyer=lawyer)]

        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 0

    def test_requester_added_if_not_in_assignments(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value = []
        requester = SimpleNamespace(
            id=99, real_name="请求人", username="req", id_card="110101199003077715",
            license_no="54321", phone="13700137000", law_firm=SimpleNamespace(name="所", address=""),
        )
        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = requester
            result = _build_agent_payloads(case=case, requester_id=99, parties=[])
            assert len(result) == 1
            assert result[0]["name"] == "请求人"


# ======================================================================
# _build_execution_reason_text / _build_execution_request_text
# ======================================================================

class TestExecutionTexts:
    def test_reason_with_cause_and_case_number(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="借款纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="2025粤01民初1号")
        assert "被执行人" in result
        assert "2025粤01民初1号" in result
        assert "借款纠纷" in result

    def test_reason_without_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "被执行人" in result
        assert "相关" in result

    def test_request_uses_service_when_available(self):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text
        case = SimpleNamespace(id=1, case_numbers=None)
        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService") as MockSvc:
            mock_instance = MockSvc.return_value
            mock_instance.generate.return_value = {"申请执行事项": "一、请求执行\n二、承担费用"}
            result = _build_execution_request_text(case=case)
            assert "请求执行" in result

    def test_request_fallback(self):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text
        case = SimpleNamespace(id=1, case_numbers=None)
        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService", side_effect=TypeError("nope")):
            result = _build_execution_request_text(case=case)
            assert "强制执行" in result


# ======================================================================
# _normalize_text
# ======================================================================

class TestNormalizeText:
    def test_removes_punctuation(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        result = _normalize_text("Hello-World (test)")
        assert "-" not in result
        assert "(" not in result

    def test_lowercases(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        result = _normalize_text("ABC")
        assert result == "abc"

    def test_empty(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        assert _normalize_text("") == ""


# ======================================================================
# _score_slot_for_signal
# ======================================================================

class TestScoreSlotForSignal:
    def test_empty_signal(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        assert _score_slot_for_signal(signal="", strong=(), weak=(), exclude=()) == 0

    def test_strong_match(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(signal="民事起诉状", strong=("起诉状",), weak=(), exclude=())
        assert score >= 5

    def test_weak_match(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(signal="诉讼请求文件", strong=(), weak=("诉讼请求",), exclude=())
        assert score >= 2

    def test_exclude_penalty(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(signal="执行申请书", strong=("起诉状",), weak=(), exclude=("执行申请书",))
        assert score < 0


# ======================================================================
# _score_slot_deduplicated
# ======================================================================

class TestScoreSlotDeduplicated:
    def test_empty_signals(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        assert _score_slot_deduplicated(primary_signals=[], secondary_signals=[], strong=(), weak=(), exclude=()) == 0

    def test_primary_gets_double_weight(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        score = _score_slot_deduplicated(
            primary_signals=["民事起诉状"],
            secondary_signals=[],
            strong=("起诉状",), weak=(), exclude=(),
        )
        assert score == 10  # 5 * 2

    def test_secondary_deduplicated(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["起诉状文件1.pdf", "起诉状文件2.pdf"],
            strong=("起诉状",), weak=(), exclude=(),
        )
        assert score == 5  # counted only once


# ======================================================================
# _build_material_slot_signals
# ======================================================================

class TestBuildMaterialSlotSignals:
    def test_with_type_name(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals
        material = SimpleNamespace(type_name="起诉状", type=None, source_attachment=None)
        primary, secondary = _build_material_slot_signals(material=material, file_path=Path("/tmp/doc.pdf"))
        assert any("起诉状" in s for s in primary)

    def test_with_material_type(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals
        mat_type = SimpleNamespace(name="授权委托书")
        material = SimpleNamespace(type_name="", type=mat_type, source_attachment=None)
        primary, secondary = _build_material_slot_signals(material=material, file_path=Path("/tmp/doc.pdf"))
        assert any("授权委托书" in s for s in primary)

    def test_secondary_includes_filename(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals
        material = SimpleNamespace(type_name="", type=None, source_attachment=None)
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/tmp/证据材料.pdf")
        )
        assert any("证据材料" in s for s in secondary)


# ======================================================================
# _match_slot
# ======================================================================

class TestMatchSlot:
    def test_matches_civil_complaint_to_slot_0(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = SimpleNamespace(type_name="民事起诉状", type=None, source_attachment=None)
        slot = _match_slot(material=material, file_path=Path("/tmp/complaint.pdf"), filing_type="civil")
        assert slot == "0"

    def test_matches_identity_to_slot_1(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = SimpleNamespace(type_name="身份证明", type=None, source_attachment=None)
        slot = _match_slot(material=material, file_path=Path("/tmp/id.pdf"), filing_type="civil")
        assert slot == "1"

    def test_delivery_address_to_slot_4(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = SimpleNamespace(type_name="其他", type=None, source_attachment=None)
        slot = _match_slot(
            material=material, file_path=Path("/tmp/送达地址确认书.pdf"), filing_type="civil"
        )
        assert slot == "4"

    def test_default_slot_for_unknown(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = SimpleNamespace(type_name="", type=None, source_attachment=None)
        slot = _match_slot(
            material=material, file_path=Path("/tmp/unknown.pdf"), filing_type="civil"
        )
        assert slot == "5"  # default for civil

    def test_execution_application_slot_0(self):
        from apps.automation.api.court_filing_helpers import _match_slot
        material = SimpleNamespace(type_name="执行申请书", type=None, source_attachment=None)
        slot = _match_slot(material=material, file_path=Path("/tmp/apply.pdf"), filing_type="execution")
        assert slot == "0"


# ======================================================================
# _build_session_status_payload
# ======================================================================

class TestBuildSessionStatusPayload:
    def _make_task(self, *, status, task_id=1, result=None, error_message=""):
        task = SimpleNamespace(id=task_id, status=status, result=result or {}, error_message=error_message)
        return task

    def test_pending_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            task = self._make_task(status="pending", result={"message": "排队中"})
            result = _build_session_status_payload(task=task)
            assert result["status"] == "in_progress"
            assert result["message"] == "排队中"

    def test_running_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            task = self._make_task(status="running")
            result = _build_session_status_payload(task=task)
            assert result["status"] == "in_progress"

    def test_success_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            task = self._make_task(status="success", result={"message": "完成"})
            result = _build_session_status_payload(task=task)
            assert result["status"] == "completed"

    def test_failed_status_with_error(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            task = self._make_task(status="failed", error_message="连接超时")
            result = _build_session_status_payload(task=task)
            assert result["status"] == "failed"
            assert result["message"] == "连接超时"

    def test_failed_status_no_error_fallback(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            task = self._make_task(status="failed", error_message="", result={})
            result = _build_session_status_payload(task=task)
            assert result["message"] == "立案失败"

    def test_timing_included(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            timing = {"overall_start": 1.0, "overall_end": 5.0}
            task = self._make_task(status="success", result={"timing": timing})
            result = _build_session_status_payload(task=task)
            assert "timing" in result
            assert result["timing"]["overall_end"] == 5.0

    def test_failed_with_result_message(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        with patch("apps.automation.models.ScraperTaskStatus") as MockStatus:
            MockStatus.PENDING = "pending"
            MockStatus.RUNNING = "running"
            MockStatus.SUCCESS = "success"
            task = self._make_task(status="failed", error_message="", result={"message": "来自结果"})
            result = _build_session_status_payload(task=task)
            assert result["message"] == "来自结果"


# ======================================================================
# _update_session_task
# ======================================================================

class TestUpdateSessionTask:
    def test_noop_when_session_id_none(self):
        from apps.automation.api.court_filing_helpers import _update_session_task
        # Should not raise
        _update_session_task(session_id=None, status="running")

    @patch("apps.automation.api.court_filing_helpers.timezone")
    def test_update_without_async(self, mock_tz):
        from apps.automation.api.court_filing_helpers import _update_session_task
        mock_tz.now.return_value = "2026-01-01"
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.filter.return_value.update.return_value = 1
            with patch("django.db.close_old_connections"):
                with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
                    _update_session_task(session_id=10, status="success", set_started=True, set_finished=True)
                    MockTask.objects.filter.assert_called_once_with(id=10)

    @patch("apps.automation.api.court_filing_helpers.timezone")
    def test_update_in_async_context(self, mock_tz):
        from apps.automation.api.court_filing_helpers import _update_session_task, _SESSION_UPDATE_EXECUTOR
        mock_tz.now.return_value = "2026-01-01"
        mock_loop = MagicMock()
        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with patch.object(_SESSION_UPDATE_EXECUTOR, "submit") as mock_submit:
                _update_session_task(session_id=10, status="running", error_message="err", result={"k": "v"})
                mock_submit.assert_called_once()


# ======================================================================
# _build_materials_map (complex, needs mocking)
# ======================================================================

class TestBuildMaterialsMap:
    def test_returns_empty_when_no_materials(self):
        from apps.automation.api.court_filing_helpers import _build_materials_map
        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory") as MockCat, \
             patch("apps.cases.models.CaseMaterialSide") as MockSide:
            MockCat.PARTY = "party"
            MockSide.OUR = "our"
            mock_qs = MagicMock()
            # Chain: filter().filter().select_related().order_by()
            mock_qs.filter.return_value = mock_qs
            mock_qs.select_related.return_value = mock_qs
            mock_qs.order_by.return_value = mock_qs
            mock_qs.exists.return_value = False
            mock_qs.__iter__ = MagicMock(return_value=iter([]))
            MockCM.objects.filter.return_value = mock_qs
            result = _build_materials_map(case=MagicMock(), filing_type="civil")
            assert result == {}

    def test_maps_pdf_to_slot(self):
        from apps.automation.api.court_filing_helpers import _build_materials_map
        mock_file = MagicMock()
        mock_file.path = "/tmp/起诉状.pdf"
        mock_attachment = MagicMock()
        mock_attachment.file = mock_file
        mock_attachment.original_filename = "起诉状.pdf"
        mock_attachment.id = 1
        mock_material = MagicMock()
        mock_material.source_attachment_id = 1
        mock_material.source_attachment = mock_attachment
        mock_material.type_name = "民事起诉状"
        mock_material.type = None

        with patch("apps.cases.models.CaseMaterial") as MockCM, \
             patch("apps.cases.models.CaseMaterialCategory") as MockCat, \
             patch("apps.cases.models.CaseMaterialSide") as MockSide, \
             patch("apps.automation.api.court_filing_helpers.Path") as MockPath:
            MockCat.PARTY = "party"
            MockSide.OUR = "our"

            path_instance = MagicMock()
            path_instance.exists.return_value = True
            path_instance.suffix = ".pdf"
            path_instance.as_posix.return_value = "/tmp/起诉状.pdf"
            path_instance.name = "起诉状.pdf"
            path_instance.stem = "起诉状"
            path_instance.parent.as_posix.return_value = "/tmp"
            MockPath.return_value = path_instance

            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.exists.return_value = True
            mock_qs.select_related.return_value = mock_qs
            mock_qs.order_by.return_value = mock_qs
            mock_qs.__iter__ = MagicMock(return_value=iter([mock_material]))
            MockCM.objects.filter.return_value = mock_qs

            result = _build_materials_map(case=MagicMock(), filing_type="civil")
            assert "0" in result  # should be in slot 0 (起诉状)


# ======================================================================
# _get_organization_service
# ======================================================================

class TestGetOrganizationService:
    def test_returns_service(self):
        from apps.automation.api.court_filing_helpers import _get_organization_service
        with patch("apps.core.dependencies.build_organization_service", return_value="mock_svc"):
            assert _get_organization_service() == "mock_svc"
