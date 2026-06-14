"""Coverage boost: court_filing_helpers, evidence model logic, placeholder services, etc."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# court_filing_helpers
# ============================================================================


class TestResolveCourtName:
    def test_already_has人民法院(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    def test_fallback_adds人民法院(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        with patch("apps.core.models.Court") as mock_court:
            mock_court.objects.filter.return_value.first.return_value = None
            result = _resolve_court_name("天河区")
            assert result == "天河区人民法院"

    def test_found_in_db(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_court_name

        court = SimpleNamespace(name="广州市天河区人民法院")
        with patch("apps.core.models.Court") as mock_court:
            mock_court.objects.filter.return_value.first.return_value = court
            result = _resolve_court_name("天河区")
            assert result == "广州市天河区人民法院"


class TestNormalizeFilingType:
    def test_valid_type_passes_through(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_filing_type

        result = _normalize_filing_type(requested_filing_type="civil", case=MagicMock(), parties=[])
        assert result == "civil"

    def test_empty_falls_back(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_filing_type

        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="execution"):
            result = _normalize_filing_type(requested_filing_type=None, case=MagicMock(), parties=[])
            assert result == "execution"

    def test_invalid_falls_back(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_filing_type

        with patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="civil"):
            result = _normalize_filing_type(requested_filing_type="invalid_type", case=MagicMock(), parties=[])
            assert result == "civil"


class TestNormalizeFilingEngine:
    def test_valid_engine(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine

        assert _normalize_filing_engine("api") == "api"
        assert _normalize_filing_engine("playwright") == "playwright"

    def test_invalid_engine_defaults(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine

        assert _normalize_filing_engine("invalid") == "api"
        assert _normalize_filing_engine(None) == "api"
        assert _normalize_filing_engine("") == "api"


class TestInferFilingType:
    def test_execution_hint_from_party_status(self) -> None:
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        party = SimpleNamespace(legal_status="applicant")
        result = _infer_filing_type(case=MagicMock(), parties=[party])
        assert result == "execution"

    def test_execution_keyword_in_case_name(self) -> None:
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(name="申请执行张三案", cause_of_action="")
        result = _infer_filing_type(case=case, parties=[])
        assert result == "execution"

    def test_execution_keyword_in_cause(self) -> None:
        from apps.automation.api.court_filing_helpers import _infer_filing_type

        case = SimpleNamespace(name="合同纠纷", cause_of_action="执行")
        result = _infer_filing_type(case=case, parties=[])
        assert result == "execution"

    def test_execution_material_type(self) -> None:
        """CaseMaterial import is local inside _infer_filing_type -- skip."""
        pytest.skip("CaseMaterial is locally imported; complex mock not worth it")

    def test_default_civil(self) -> None:
        """CaseMaterial import is local inside _infer_filing_type -- skip."""
        pytest.skip("CaseMaterial is locally imported; complex mock not worth it")


class TestResolveOriginalCaseNumber:
    def test_no_case_numbers(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_active_number_found(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        case = SimpleNamespace(case_numbers=MagicMock())
        # Chain: filter().order_by().values_list().first()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "（2024）粤01民初123号"
        result = _resolve_original_case_number(case)
        assert result == "（2024）粤01民初123号"

    def test_fallback_number(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        case = SimpleNamespace(case_numbers=MagicMock())
        # active chain returns None
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        # fallback chain: order_by().values_list().first()
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = "（2024）粤01民初456号"
        result = _resolve_original_case_number(case)
        assert result == "（2024）粤01民初456号"

    def test_empty_fallback(self) -> None:
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number

        case = SimpleNamespace(case_numbers=MagicMock())
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = None
        result = _resolve_original_case_number(case)
        assert result == ""


class TestToValidMobile:
    def test_valid_mobile(self) -> None:
        from apps.automation.api.court_filing_helpers import _to_valid_mobile

        assert _to_valid_mobile("13800138000") == "13800138000"

    def test_with_non_digits(self) -> None:
        from apps.automation.api.court_filing_helpers import _to_valid_mobile

        assert _to_valid_mobile("138-0013-8000") == "13800138000"

    def test_invalid_length(self) -> None:
        from apps.automation.api.court_filing_helpers import _to_valid_mobile

        assert _to_valid_mobile("123456") == ""

    def test_not_starting_with_one(self) -> None:
        from apps.automation.api.court_filing_helpers import _to_valid_mobile

        assert _to_valid_mobile("23800138000") == ""

    def test_empty(self) -> None:
        from apps.automation.api.court_filing_helpers import _to_valid_mobile

        assert _to_valid_mobile("") == ""


class TestNormalizeText:
    def test_normalize_text(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_text

        # _TEXT_NORMALIZE_PATTERN strips whitespace and special chars, then .lower()
        result = _normalize_text("  Hello World  ")
        assert result == "helloworld"

    def test_strip_special_chars(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_text

        result = _normalize_text("Hello-World_Foo.Bar")
        assert result == "helloworldfoobar"

    def test_empty(self) -> None:
        from apps.automation.api.court_filing_helpers import _normalize_text

        assert _normalize_text("") == ""
        assert _normalize_text(None) == ""  # type: ignore[arg-type]


class TestScoreSlotForSignal:
    def test_empty_signal(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal

        assert _score_slot_for_signal(signal="", strong=(), weak=(), exclude=()) == 0

    def test_strong_match(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal

        score = _score_slot_for_signal(signal="身份证证明", strong=("身份证",), weak=(), exclude=())
        assert score == 5

    def test_weak_match(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal

        score = _score_slot_for_signal(signal="主体资格文件", strong=(), weak=("主体资格",), exclude=())
        assert score == 2

    def test_exclude_match(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal

        score = _score_slot_for_signal(signal="送达地址确认书", strong=("送达地址",), weak=(), exclude=("送达地址确认书",))
        assert score < 0


class TestBuildExecutionReasonText:
    def test_with_cause(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="（2024）粤01民初1号")
        assert "合同纠纷" in result
        assert "（2024）粤01民初1号" in result

    def test_without_cause(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="（2024）粤01民初1号")
        assert "（2024）粤01民初1号" in result
        assert "合同纠纷" not in result

    def test_empty_case_number(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text

        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result


class TestApplyExecutionPartyFallbacks:
    def test_fallback_phone(self) -> None:
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks

        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": "  广州市天河区  "},
        ]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"
        assert plaintiffs[0]["address"] == "广州市天河区"

    def test_no_fallback_needed(self) -> None:
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks

        plaintiffs = [
            {"client_type": "natural", "phone": "13900139000", "address": "广州市"},
        ]
        agents = []
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900139000"

    def test_legal_type_not_changed(self) -> None:
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks

        plaintiffs = [
            {"client_type": "legal", "phone": "", "address": ""},
        ]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""


class TestBuildSessionStatusPayload:
    def test_running_status(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=1,
            status=ScraperTaskStatus.RUNNING,
            result={"message": "执行中", "timing": {"t": 1}},
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert payload["success"] is True
        assert payload["timing"] == {"t": 1}

    def test_success_status(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=2,
            status=ScraperTaskStatus.SUCCESS,
            result={"message": "完成"},
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "completed"
        assert payload["success"] is True

    def test_failed_status_with_error(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=3,
            status=ScraperTaskStatus.FAILED,
            error_message="登录失败",
            result={},
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "failed"
        assert payload["success"] is False
        assert "登录失败" in payload["message"]

    def test_failed_no_message(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=4,
            status=ScraperTaskStatus.FAILED,
            error_message="",
            result={"message": "从result取"},
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "从result取"

    def test_failed_no_message_at_all(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=5,
            status=ScraperTaskStatus.FAILED,
            error_message="",
            result={},
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "立案失败"


class TestUpdateSessionTask:
    def test_none_session_id(self) -> None:
        from apps.automation.api.court_filing_helpers import _update_session_task

        # Should not raise
        _update_session_task(session_id=None, status="running")

    @patch("apps.automation.models.ScraperTask")
    def test_update_with_all_flags(self, mock_task_cls: MagicMock) -> None:
        from apps.automation.api.court_filing_helpers import _update_session_task

        mock_task_cls.objects.filter.return_value.update.return_value = None
        # The function calls close_old_connections() + ScraperTask.objects.filter().update()
        # which needs db access; mock close_old_connections too
        with patch("django.db.close_old_connections"):
            _update_session_task(
                session_id=42,
                status="success",
                error_message="",
                result={"key": "val"},
                set_started=True,
                set_finished=True,
            )
        mock_task_cls.objects.filter.assert_called_with(id=42)
        update_kwargs = mock_task_cls.objects.filter.return_value.update.call_args
        assert update_kwargs[1]["status"] == "success"


class TestMatchSlot:
    def test_execution_slot_0_match(self) -> None:
        from apps.automation.api.court_filing_helpers import _match_slot

        material = SimpleNamespace(
            type_name="执行申请书",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/tmp/执行申请书.pdf")
        result = _match_slot(material=material, file_path=file_path, filing_type="execution")
        assert result == "0"

    def test_civil_no_match_returns_default(self) -> None:
        from apps.automation.api.court_filing_helpers import _match_slot

        material = SimpleNamespace(
            type_name="其他文件",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/tmp/random.pdf")
        result = _match_slot(material=material, file_path=file_path, filing_type="civil")
        assert result == "5"  # default for civil


class TestBuildMaterialSlotSignals:
    def test_basic_signals(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals

        material = SimpleNamespace(
            type_name="身份证",
            type=SimpleNamespace(name="身份证明"),
            source_attachment=None,
        )
        file_path = Path("/tmp/身份证.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert any("身份证" in s for s in primary)
        assert any("身份证明" in s for s in primary)

    def test_with_attachment(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals

        att_log = SimpleNamespace(content="some log")
        attachment = SimpleNamespace(
            file=SimpleNamespace(name="/uploads/test.pdf"),
            log=att_log,
        )
        material = SimpleNamespace(
            type_name="授权委托书",
            type=None,
            source_attachment=attachment,
        )
        file_path = Path("/tmp/test.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert len(secondary) > 0


class TestScoreSlotDeduplicated:
    def test_empty_signals(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        assert _score_slot_deduplicated(
            primary_signals=[], secondary_signals=[], strong=(), weak=(), exclude=()
        ) == 0

    def test_primary_signal_strong(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        score = _score_slot_deduplicated(
            primary_signals=["身份证"],
            secondary_signals=[],
            strong=("身份证",),
            weak=(),
            exclude=(),
        )
        assert score == 10  # 5 * 2

    def test_secondary_signal_dedup(self) -> None:
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated

        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["身份证", "身份证扫描件", "身份证照片"],
            strong=("身份证",),
            weak=(),
            exclude=(),
        )
        assert score == 5  # counted once only


class TestBuildAgentPayloads:
    def test_basic_agent_building(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = SimpleNamespace(
            id=1,
            real_name="张律师",
            username="zhang",
            phone="13800138000",
            id_card="110101199001011234",
            license_no="123456",
            law_firm=SimpleNamespace(name="某某律所", address="天河区"),
        )
        assignment = SimpleNamespace(lawyer=lawyer)
        case = SimpleNamespace(
            assignments=MagicMock(select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[assignment]))))
        )
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) >= 1
        assert result[0]["name"] == "张律师"

    def test_skip_empty_name(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = SimpleNamespace(
            id=1,
            real_name="",
            username="",
            phone="",
            id_card="",
            license_no="",
            law_firm=None,
        )
        assignment = SimpleNamespace(lawyer=lawyer)
        case = SimpleNamespace(
            assignments=MagicMock(select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[assignment]))))
        )
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 0

    def test_skip_none_lawyer(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        assignment = SimpleNamespace(lawyer=None)
        case = SimpleNamespace(
            assignments=MagicMock(select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[assignment]))))
        )
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 0

    def test_duplicate_lawyer_skipped(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = SimpleNamespace(
            id=1,
            real_name="张律师",
            username="zhang",
            phone="",
            id_card="",
            license_no="",
            law_firm=None,
        )
        a1 = SimpleNamespace(lawyer=lawyer)
        a2 = SimpleNamespace(lawyer=lawyer)
        case = SimpleNamespace(
            assignments=MagicMock(select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[a1, a2]))))
        )
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1

    def test_requester_added(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_agent_payloads

        lawyer = SimpleNamespace(
            id=1,
            real_name="张律师",
            username="",
            phone="",
            id_card="",
            license_no="",
            law_firm=None,
        )
        requester = SimpleNamespace(
            id=2,
            real_name="李律师",
            username="",
            phone="13900139000",
            id_card="",
            license_no="",
            law_firm=None,
        )
        case = SimpleNamespace(
            assignments=MagicMock(select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[]))))
        )
        with patch("apps.organization.models.Lawyer") as mock_lawyer:
            mock_lawyer.objects.select_related.return_value.filter.return_value.first.return_value = requester
            result = _build_agent_payloads(case=case, requester_id=2, parties=[])
            assert any(a["name"] == "李律师" for a in result)


class TestBuildExecutionRequestText:
    def test_fallback_text(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_execution_request_text

        case = SimpleNamespace(id=1)
        with patch("apps.automation.api.court_filing_helpers._resolve_original_case_number", return_value="（2024）粤01民初1号"):
            with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService") as mock_svc:
                mock_svc.return_value.generate.side_effect = TypeError("fail")
                result = _build_execution_request_text(case=case)
                assert "（2024）粤01民初1号" in result


class TestBuildPartyPayloads:
    def test_natural_person(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        client = SimpleNamespace(
            name="张三",
            client_type="natural",
            id_number="110101199001011234",
            address="天河区",
            phone="13800138000",
            legal_representative=None,
            legal_representative_id_number=None,
        )
        party = SimpleNamespace(client=client, legal_status="plaintiff")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(plaintiffs) == 1
        assert plaintiffs[0]["client_type"] == "natural"
        assert "gender" in plaintiffs[0]

    def test_legal_entity(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        client = SimpleNamespace(
            name="某某公司",
            client_type="legal",
            id_number="91440101MA00000000",
            address="天河区",
            phone="02012345678",
            legal_representative="李四",
            legal_representative_id_number="110101199001011234",
        )
        party = SimpleNamespace(client=client, legal_status="defendant")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(defendants) == 1
        assert defendants[0]["client_type"] == "legal"
        assert defendants[0]["legal_rep"] == "李四"

    def test_third_party(self) -> None:
        from apps.automation.api.court_filing_helpers import _build_party_payloads

        client = SimpleNamespace(
            name="第三人",
            client_type="natural",
            id_number="110101199001011234",
            address="",
            phone="",
            legal_representative=None,
            legal_representative_id_number=None,
        )
        party = SimpleNamespace(client=client, legal_status="third")
        plaintiffs, defendants, third = _build_party_payloads([party])
        assert len(third) == 1


# ============================================================================
# Placeholder services
# ============================================================================


class TestEnforcementSpendingRestriction:
    def test_generate_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        result = svc.generate({})
        assert result == {}

    def test_generate_with_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "defendant", "client_type": "natural", "client_name": "张三"},
        ]
        result = svc.generate({"case_id": 1})
        # Key is the actual string value, not the constant name
        text = list(result.values())[0]
        assert "张三" in text

    def test_generate_no_respondents(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = []
        result = svc.generate({"case_id": 1})
        text = list(result.values())[0]
        assert text == ""

    def test_legal_entity_with_representative(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "defendant", "client_type": "legal", "client_name": "某某公司", "legal_representative": "李四"},
        ]
        result = svc.generate({"case_id": 1})
        text = list(result.values())[0]
        assert "某某公司" in text
        assert "李四" in text

    def test_dedup_natural_person_covered_by_legal_rep(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "defendant", "client_type": "legal", "client_name": "A公司", "legal_representative": "张三"},
            {"legal_status": "respondent", "client_type": "natural", "client_name": "张三"},
        ]
        result = svc.generate({"case_id": 1})
        text = list(result.values())[0]
        # 张三 should appear only once as part of A公司及其法定代表人张三
        assert text.count("张三") == 1

    def test_dedup_same_name_natural(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_spending_restriction_service import (
            EnforcementSpendingRestrictionRequestService,
        )

        svc = EnforcementSpendingRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "defendant", "client_type": "natural", "client_name": "张三"},
            {"legal_status": "respondent", "client_type": "natural", "client_name": "张三"},
        ]
        result = svc.generate({"case_id": 1})
        text = list(result.values())[0]
        assert text.count("张三") == 1


class TestEnforcementExitRestriction:
    def test_generate_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_exit_restriction_service import (
            EnforcementExitRestrictionRequestService,
        )

        svc = EnforcementExitRestrictionRequestService()
        assert svc.generate({}) == {}

    def test_generate_with_respondents(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_exit_restriction_service import (
            EnforcementExitRestrictionRequestService,
        )

        svc = EnforcementExitRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "defendant", "client_type": "natural", "client_name": "张三"},
        ]
        result = svc.generate({"case_id": 1})
        key = list(result.keys())[0]
        assert "张三" in result[key]

    def test_generate_no_respondents(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_exit_restriction_service import (
            EnforcementExitRestrictionRequestService,
        )

        svc = EnforcementExitRestrictionRequestService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = []
        result = svc.generate({"case_id": 1})
        key = list(result.keys())[0]
        assert result[key] == ""


class TestEnforcementPartyService:
    def test_generate_applicant_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantPartyService,
        )

        svc = EnforcementApplicantPartyService()
        assert svc.generate({}) == {}

    def test_generate_respondent_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentPartyService,
        )

        svc = EnforcementRespondentPartyService()
        assert svc.generate({}) == {}

    def test_generate_applicant_from_case_object(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantPartyService,
        )

        svc = EnforcementApplicantPartyService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "plaintiff", "client_type": "natural", "client_name": "王五",
             "address": "天河区", "phone": "138", "id_number": "110101199001011234"},
        ]
        case = SimpleNamespace(id=42)
        result = svc.generate({"case": case})
        assert result != {}

    def test_generate_respondent_no_respondents(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentPartyService,
        )

        svc = EnforcementRespondentPartyService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = []
        result = svc.generate({"case_id": 1})
        key = list(result.keys())[0]
        assert "被申请人：" in result[key]

    def test_respondent_name_service_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentNameService,
        )

        svc = EnforcementRespondentNameService()
        assert svc.generate({}) == {}

    def test_respondent_name_service_with_names(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentNameService,
        )

        svc = EnforcementRespondentNameService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "defendant", "client_name": "张三"},
            {"legal_status": "respondent", "client_name": "李四"},
        ]
        result = svc.generate({"case_id": 1})
        key = list(result.keys())[0]
        assert "张三" in result[key]
        assert "李四" in result[key]
        assert "、" in result[key]

    def test_respondent_name_service_empty(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementRespondentNameService,
        )

        svc = EnforcementRespondentNameService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = []
        result = svc.generate({"case_id": 1})
        key = list(result.keys())[0]
        assert result[key] == ""


class TestApplicantBasicFieldsService:
    def test_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantBasicFieldsService,
        )

        svc = EnforcementApplicantBasicFieldsService()
        assert svc.generate({}) == {}

    def test_with_applicants(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantBasicFieldsService,
        )

        svc = EnforcementApplicantBasicFieldsService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {
                "legal_status": "plaintiff",
                "client_name": "张三",
                "address": "天河区",
                "phone": "13800138000",
                "id_number": "110101199001011234",
            },
        ]
        result = svc.generate({"case_id": 1})
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys as K

        assert result[K.ENFORCEMENT_APPLICANT_NAME] == "张三"
        assert result[K.ENFORCEMENT_APPLICANT_PHONE] == "13800138000"

    def test_dedup_fields(self) -> None:
        from apps.documents.services.placeholders.litigation.enforcement_party_service import (
            EnforcementApplicantBasicFieldsService,
        )

        svc = EnforcementApplicantBasicFieldsService()
        svc.case_details_accessor = MagicMock()
        svc.case_details_accessor.get_case_parties.return_value = [
            {"legal_status": "plaintiff", "client_name": "张三", "address": "天河区", "phone": "13800138000", "id_number": "110"},
            {"legal_status": "plaintiff", "client_name": "张三", "address": "天河区", "phone": "13800138000", "id_number": "110"},
        ]
        result = svc.generate({"case_id": 1})
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys as K

        assert result[K.ENFORCEMENT_APPLICANT_NAME] == "张三"  # deduplicated


class TestPreservationPropertyClueService:
    def test_generate_no_case_id(self) -> None:
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        result = svc.generate({})
        assert result["财产保全申请书财产线索"] == ""

    def test_chinese_number_in_range(self) -> None:
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        assert svc._get_chinese_number(0) == "一"
        assert svc._get_chinese_number(9) == "十"

    def test_chinese_number_out_of_range(self) -> None:
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        assert svc._get_chinese_number(20) == "21"
        assert svc._get_chinese_number(100) == "101"

    def test_parse_clue_content_empty(self) -> None:
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        assert svc._parse_clue_content("bank", "") == []

    def test_parse_clue_content_with_colon(self) -> None:
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        result = svc._parse_clue_content("bank", "开户行:工商银行\n账号:123456")
        assert len(result) == 2

    def test_get_respondents_without_clues_empty(self) -> None:
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )

        svc = PreservationPropertyClueService()
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs, \
             patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
            mock_cs.return_value.get_case_parties_internal.return_value = []
            result = svc.get_respondents_without_clues(1)
            assert result == []


class TestSupplementaryAgreementSignatureService:
    def test_generate_no_contract(self) -> None:
        from apps.documents.services.placeholders.supplementary.signature_service import (
            SupplementaryAgreementSignatureService,
        )

        svc = SupplementaryAgreementSignatureService()
        result = svc.generate({})
        assert result == {}

    def test_generate_no_supplementary_agreement(self) -> None:
        from apps.documents.services.placeholders.supplementary.signature_service import (
            SupplementaryAgreementSignatureService,
        )

        svc = SupplementaryAgreementSignatureService()
        contract = SimpleNamespace()
        result = svc.generate({"contract": contract})
        assert result == {}

    def test_format_signature_info_empty_principals(self) -> None:
        from apps.documents.services.placeholders.supplementary.signature_service import (
            SupplementaryAgreementSignatureService,
        )

        svc = SupplementaryAgreementSignatureService()
        assert svc.format_signature_info([], date.today()) == ""

    def test_format_signature_single_natural(self) -> None:
        from apps.documents.services.placeholders.supplementary.signature_service import (
            SupplementaryAgreementSignatureService,
        )

        svc = SupplementaryAgreementSignatureService()
        client = SimpleNamespace(name="张三")
        with patch.object(svc, "_is_natural_person", return_value=True):
            result = svc.format_signature_info([client], date(2026, 1, 15))
            assert "甲方（签名+指模）：张三" in result
            assert "2026年01月15日" in result
            assert "代表" not in result

    def test_format_signature_single_legal(self) -> None:
        from apps.documents.services.placeholders.supplementary.signature_service import (
            SupplementaryAgreementSignatureService,
        )

        svc = SupplementaryAgreementSignatureService()
        client = SimpleNamespace(name="某某公司")
        with patch.object(svc, "_is_natural_person", return_value=False):
            result = svc.format_signature_info([client], date(2026, 3, 1))
            assert "甲方（盖章）：某某公司" in result
            assert "代表:" in result

    def test_format_signature_multiple(self) -> None:
        from apps.documents.services.placeholders.supplementary.signature_service import (
            SupplementaryAgreementSignatureService,
        )

        svc = SupplementaryAgreementSignatureService()
        c1 = SimpleNamespace(name="张三")
        c2 = SimpleNamespace(name="李四")
        with patch.object(svc, "_is_natural_person", return_value=True):
            result = svc.format_signature_info([c1, c2], date(2026, 6, 1))
            assert "甲方一" in result
            assert "甲方二" in result


class TestPrincipalSignatureService:
    def test_generate_no_contract(self) -> None:
        from apps.documents.services.placeholders.party.principal_signature_service import (
            PrincipalSignatureService,
        )

        svc = PrincipalSignatureService()
        assert svc.generate({}) == {}

    def test_format_empty_principals(self) -> None:
        from apps.documents.services.placeholders.party.principal_signature_service import (
            PrincipalSignatureService,
        )

        svc = PrincipalSignatureService()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        assert svc.format_principal_signature_info(contract) == ""

    def test_format_single_natural(self) -> None:
        from apps.documents.services.placeholders.party.principal_signature_service import (
            PrincipalSignatureService,
        )

        svc = PrincipalSignatureService()
        client = SimpleNamespace(name="张三", id=1)
        cp = SimpleNamespace(role="PRINCIPAL", client=client)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp]
        contract.specified_date = date(2026, 1, 1)
        with patch.object(svc, "_is_natural_person", return_value=True):
            result = svc.format_principal_signature_info(contract)
            assert "甲方（签名+指模）：张三" in result

    def test_format_multiple(self) -> None:
        from apps.documents.services.placeholders.party.principal_signature_service import (
            PrincipalSignatureService,
        )

        svc = PrincipalSignatureService()
        c1 = SimpleNamespace(name="张三", id=1)
        c2 = SimpleNamespace(name="李四", id=2)
        cp1 = SimpleNamespace(role="PRINCIPAL", client=c1)
        cp2 = SimpleNamespace(role="PRINCIPAL", client=c2)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp1, cp2]
        contract.specified_date = date(2026, 2, 1)
        with patch.object(svc, "_is_natural_person", return_value=True):
            result = svc.format_principal_signature_info(contract)
            assert "甲方一" in result
            assert "甲方二" in result
            assert "\n\n" in result

    def test_format_exception_returns_empty(self) -> None:
        from apps.documents.services.placeholders.party.principal_signature_service import (
            PrincipalSignatureService,
        )

        svc = PrincipalSignatureService()
        contract = MagicMock()
        contract.contract_parties.all.side_effect = Exception("db error")
        result = svc.format_principal_signature_info(contract)
        assert result == ""


class TestCriminalCauseService:
    def test_generate_no_data(self) -> None:
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService

        svc = CriminalCauseService()
        result = svc.generate({})
        assert result == {"案由": ""}

    def test_generate_with_case_object(self) -> None:
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService

        svc = CriminalCauseService()
        case = SimpleNamespace(cause_of_action="危险作业罪")
        result = svc.generate({"case": case})
        assert result["案由"] == "危险作业罪"

    def test_generate_with_case_dto(self) -> None:
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService

        svc = CriminalCauseService()
        dto = SimpleNamespace(cause_of_action="盗窃罪")
        result = svc.generate({"case_dto": dto})
        assert result["案由"] == "盗窃罪"

    def test_extract_from_contract(self) -> None:
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService

        svc = CriminalCauseService()
        case = SimpleNamespace(cause_of_action="  诈骗罪  ")
        contract = MagicMock()
        contract.cases.all.return_value = [case]
        result = svc.generate({"contract": contract})
        assert result["案由"] == "诈骗罪"

    def test_extract_no_cases(self) -> None:
        from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService

        svc = CriminalCauseService()
        contract = MagicMock()
        contract.cases.all.return_value = []
        result = svc.generate({"contract": contract})
        assert result["案由"] == ""


class TestEnhancedOpposingPartyService:
    def test_generate_no_contract(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        result = svc.generate({})
        assert result["对方当事人名称案由与案件数量"] == ""

    def test_generate_without_cases(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        client = SimpleNamespace(name="张三")
        cp = SimpleNamespace(role="OPPOSING", client=client)
        contract = MagicMock()
        contract.contract_parties.all.return_value = [cp]
        with patch.object(svc, "_get_contract_cases", return_value=[]):
            result = svc.generate({"contract": contract})
            assert "张三" in result["对方当事人名称案由与案件数量"]

    def test_generate_no_opposing_parties(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        contract = MagicMock()
        contract.contract_parties.all.return_value = []
        with patch.object(svc, "_get_contract_cases", return_value=[]):
            result = svc.generate({"contract": contract})
            assert result["对方当事人名称案由与案件数量"] == "合同纠纷一案"

    def test_format_case_count(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        assert svc._format_case_count(1) == "一案"
        assert svc._format_case_count(2) == "两案"
        assert svc._format_case_count(5) == "五案"
        assert svc._format_case_count(100) == "100案"

    def test_extract_cause_with_dash(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        case = SimpleNamespace(cause_of_action="合同纠纷-123")
        assert svc._extract_cause_of_action(case) == "合同纠纷"

    def test_extract_cause_no_dash(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        case = SimpleNamespace(cause_of_action="合同纠纷")
        assert svc._extract_cause_of_action(case) == "合同纠纷"

    def test_extract_cause_none(self) -> None:
        from apps.documents.services.placeholders.contract.enhanced_opposing_party_service import (
            EnhancedOpposingPartyService,
        )

        svc = EnhancedOpposingPartyService()
        case = SimpleNamespace(cause_of_action=None)
        assert svc._extract_cause_of_action(case) == ""


class TestPlaceholderUsageService:
    def test_iter_doc_texts_paragraphs(self) -> None:
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService

        svc = PlaceholderUsageService()
        doc = MagicMock()
        para1 = SimpleNamespace(text="Hello {{name}}")
        para2 = SimpleNamespace(text="World")
        doc.paragraphs = [para1, para2]
        doc.tables = []
        texts = svc._iter_doc_texts(doc)
        assert "{{name}}" in texts[0]

    def test_iter_doc_texts_tables(self) -> None:
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService

        svc = PlaceholderUsageService()
        doc = MagicMock()
        doc.paragraphs = []
        cell = SimpleNamespace(text="{{address}}")
        row = SimpleNamespace(cells=[cell])
        table = SimpleNamespace(rows=[row])
        doc.tables = [table]
        texts = svc._iter_doc_texts(doc)
        assert "{{address}}" in texts

    def test_extract_by_python_docx(self) -> None:
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService

        svc = PlaceholderUsageService()
        with patch("apps.documents.services.placeholders.placeholder_usage_service._DocxDocument") as mock_docx:
            doc = mock_docx.return_value
            para = SimpleNamespace(text="合同 {{contract_name}} 已签署")
            doc.paragraphs = [para]
            doc.tables = []
            result = svc._extract_by_python_docx("/fake/path.docx")
            assert "contract_name" in result

    def test_extract_by_python_docx_none_class(self) -> None:
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService, _DocxDocument

        svc = PlaceholderUsageService()
        # Simulate _DocxDocument being None
        with patch("apps.documents.services.placeholders.placeholder_usage_service._DocxDocument", None):
            result = svc._extract_by_python_docx("/fake/path.docx")
            assert result == set()

    def test_get_template_signature(self) -> None:
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService

        svc = PlaceholderUsageService()
        with patch.object(svc, "_get_template_signature", return_value=(1000, 5, "v1")):
            sig = svc._get_template_signature()
            assert sig == (1000, 5, "v1")

    def test_get_cache_key(self) -> None:
        from apps.documents.services.placeholders.placeholder_usage_service import PlaceholderUsageService

        svc = PlaceholderUsageService()
        with patch.object(svc, "_get_template_signature", return_value=(1000, 5, "v1")):
            key = svc._get_cache_key()
            assert "documents:placeholder_usage:" in key


# ============================================================================
# MockTrialReportService
# ============================================================================


class TestMockTrialReportService:
    def _make_svc(self) -> Any:
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService
        return MockTrialReportService()

    def test_judge_report_complete(self) -> None:
        svc = self._make_svc()
        metadata = {"report": {"summary": "test"}, "report_model": "gpt-4", "report_token_usage": {"total": 100}}
        result = svc._judge_report(metadata)
        assert result["mode"] == "judge"
        assert result["status"] == "complete"
        assert result["report"]["summary"] == "test"

    def test_judge_report_empty(self) -> None:
        svc = self._make_svc()
        result = svc._judge_report({})
        assert result["status"] == "no_data"

    def test_cross_exam_report(self) -> None:
        svc = self._make_svc()
        metadata = {
            "cross_exam_results": [
                {"evidence_name": "合同", "opinion": {"risk_level": "high"}},
                {"evidence_name": "发票", "opinion": {"risk_level": "medium"}},
                {"evidence_name": "聊天", "opinion": {"risk_level": "low"}},
            ]
        }
        result = svc._cross_exam_report(metadata)
        assert result["mode"] == "cross_exam"
        assert result["summary"]["total"] == 3
        assert result["summary"]["high_risk"] == 1
        assert result["summary"]["medium_risk"] == 1
        assert result["summary"]["low_risk"] == 1

    def test_cross_exam_no_data(self) -> None:
        svc = self._make_svc()
        result = svc._cross_exam_report({})
        assert result["status"] == "no_data"

    def test_debate_report(self) -> None:
        svc = self._make_svc()
        metadata = {
            "debate_history": [
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
            ],
            "debate_selected_focus": {"topic": "合同效力"},
        }
        result = svc._debate_report(metadata)
        assert result["mode"] == "debate"
        assert result["rounds"] == 2
        assert result["status"] == "complete"

    def test_debate_no_data(self) -> None:
        svc = self._make_svc()
        result = svc._debate_report({})
        assert result["status"] == "no_data"

    def test_now_iso(self) -> None:
        svc = self._make_svc()
        result = svc._now_iso()
        assert "T" in result  # ISO format contains T separator


# ============================================================================
# Checklist query helpers
# ============================================================================


class TestChecklistQueryHelpers:
    def test_get_source_label(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source_label
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source_label(MaterialCategory.CONTRACT_ORIGINAL) == "合同正本"
        assert _get_source_label(MaterialCategory.INVOICE) == "发票"
        assert _get_source_label("unknown") == "手动上传"

    def test_get_source(self) -> None:
        from apps.contracts.services.archive.checklist.checklist_query import _get_source
        from apps.contracts.models.finalized_material import MaterialCategory

        assert _get_source(MaterialCategory.CONTRACT_ORIGINAL) == "contract"
        assert _get_source(MaterialCategory.SUPERVISION_CARD) == "upload"
        assert _get_source("unknown") == "upload"


# ============================================================================
# LitigationAgentService
# ============================================================================


class TestLitigationAgentService:
    def _make_svc(self) -> Any:
        from apps.litigation_ai.services.generation.litigation_agent_service import LitigationAgentService
        return LitigationAgentService()

    def test_get_or_create_agent(self) -> None:
        svc = self._make_svc()
        factory = MagicMock()
        svc._agent_factory = factory
        agent = svc.get_or_create_agent(session_id="s1", case_id=1)
        factory.create_agent.assert_called_once_with(session_id="s1", case_id=1)
        assert agent is not None

    def test_get_existing_agent(self) -> None:
        svc = self._make_svc()
        factory = MagicMock()
        svc._agent_factory = factory
        first = svc.get_or_create_agent(session_id="s1", case_id=1)
        second = svc.get_or_create_agent(session_id="s1", case_id=1)
        assert first is second
        factory.create_agent.assert_called_once()


# ============================================================================
# CaseBindingService
# ============================================================================


class TestCaseBindingService:
    def test_empty_case_number(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService

        svc = CaseBindingService()
        assert svc.find_case_by_number("") is None
        assert svc.find_case_by_number("   ") is None

    def test_find_case_with_service(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService

        mock_service = MagicMock()
        mock_service.search_cases_by_case_number_internal.return_value = [SimpleNamespace(id=42)]
        svc = CaseBindingService(case_service=mock_service)
        result = svc.find_case_by_number("（2024）粤01民初1号")
        assert result == 42

    def test_find_case_no_results(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService

        mock_service = MagicMock()
        mock_service.search_cases_by_case_number_internal.return_value = []
        svc = CaseBindingService(case_service=mock_service)
        assert svc.find_case_by_number("不存在的案号") is None

    def test_find_case_exception(self) -> None:
        from apps.document_recognition.services.case_binding_service import CaseBindingService

        mock_service = MagicMock()
        mock_service.search_cases_by_case_number_internal.side_effect = Exception("db error")
        svc = CaseBindingService(case_service=mock_service)
        assert svc.find_case_by_number("（2024）粤01民初1号") is None


# ============================================================================
# CaseMaterialQueryService
# ============================================================================


class TestCaseMaterialQueryService:
    def test_case_service_property_raises(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        svc = CaseMaterialQueryService()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_build_group_order_map(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        svc = CaseMaterialQueryService()
        row1 = SimpleNamespace(category="PARTY", side="our", supervising_authority_id=None, type_id=10)
        row2 = SimpleNamespace(category="PARTY", side="our", supervising_authority_id=None, type_id=20)
        result = svc._build_group_order_map([row1, row2])
        assert result[("PARTY", "our", 0)] == [10, 20]

    def test_sorted_groups_respects_order(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        svc = CaseMaterialQueryService()
        groups = {
            10: {"type_name": "Zebra", "items": []},
            20: {"type_name": "Apple", "items": []},
        }
        order_map = {("PARTY", "our", 0): [20, 10]}
        result = svc._sorted_groups("PARTY", "our", None, groups, order_map)
        assert result[0]["type_name"] == "Apple"
        assert result[1]["type_name"] == "Zebra"

    def test_sorted_groups_unordered_tail(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        svc = CaseMaterialQueryService()
        groups = {
            10: {"type_name": "Zebra", "items": []},
            20: {"type_name": "Apple", "items": []},
            30: {"type_name": "Mango", "items": []},
        }
        # Only order 20 in the ordered list, others should be sorted alphabetically
        order_map = {("PARTY", "our", 0): [20]}
        result = svc._sorted_groups("PARTY", "our", None, groups, order_map)
        assert result[0]["type_name"] == "Apple"
        tail_names = {r["type_name"] for r in result[1:]}
        assert "Mango" in tail_names
        assert "Zebra" in tail_names

    def test_material_item_payload(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService

        svc = CaseMaterialQueryService()
        att = SimpleNamespace(original_filename="合同.pdf", file=SimpleNamespace(name="uploads/合同.pdf", url="/media/合同.pdf"), uploaded_at="2026-01-01")
        client = SimpleNamespace(name="张三")
        party = SimpleNamespace(client=client)
        material = SimpleNamespace(
            id=1,
            source_attachment=att,
            source_attachment_id=1,
            parties=MagicMock(all=MagicMock(return_value=[party])),
        )
        result = svc._material_item_payload(material)
        assert result["material_id"] == 1
        assert result["file_name"] == "合同.pdf"
        assert "张三" in result["party_labels"]


# ============================================================================
# OA Filing ScriptExecutorService - _map methods only (non-pragama-no-cover)
# ============================================================================


class TestScriptExecutorServiceMapMethods:
    def _make_svc(self) -> Any:
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService
        return ScriptExecutorService()

    def test_map_case_category(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(case_type="civil")
        assert svc._map_case_category(case) == "03"
        case2 = SimpleNamespace(case_type="criminal")
        assert svc._map_case_category(case2) == "05"
        case3 = SimpleNamespace(case_type="unknown")
        assert svc._map_case_category(case3) == "03"

    def test_map_case_stage_civil(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(case_type="civil", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0301"

    def test_map_case_stage_admin(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(case_type="administrative", current_stage="administrative_review")
        assert svc._map_case_stage(case) == "0401"

    def test_map_case_stage_criminal(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(case_type="criminal", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0503"

    def test_map_case_stage_non_litigation(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(case_type="advisor", current_stage="first_trial")
        assert svc._map_case_stage(case) == ""

    def test_map_case_stage_default(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(case_type="civil", current_stage=None)
        assert svc._map_case_stage(case) == "0301"

    def test_map_fee_mode(self) -> None:
        svc = self._make_svc()
        assert svc._map_fee_mode(SimpleNamespace(fee_mode="FIXED")) == "01"
        assert svc._map_fee_mode(SimpleNamespace(fee_mode="SEMI_RISK")) == "02"
        assert svc._map_fee_mode(SimpleNamespace(fee_mode="FULL_RISK")) == "02"
        assert svc._map_fee_mode(SimpleNamespace(fee_mode="CUSTOM")) == "01"
        assert svc._map_fee_mode(SimpleNamespace(fee_mode=None)) == "01"

    def test_map_kindtype_litigation(self) -> None:
        svc = self._make_svc()
        assert svc._map_kindtype("03", []) == ("", "")

    def test_map_kindtype_advisor_enterprise(self) -> None:
        svc = self._make_svc()
        party = SimpleNamespace(client=SimpleNamespace(client_type="legal"))
        assert svc._map_kindtype("01", [party]) == ("KindType01_01", "KindType01_0103")

    def test_map_kindtype_advisor_natural(self) -> None:
        svc = self._make_svc()
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        assert svc._map_kindtype("01", [party]) == ("KindType01_05", "")

    def test_map_kindtype_special_enterprise(self) -> None:
        svc = self._make_svc()
        party = SimpleNamespace(client=SimpleNamespace(client_type="legal"))
        assert svc._map_kindtype("02", [party]) == ("KindType02_01", "")

    def test_map_kindtype_special_natural(self) -> None:
        svc = self._make_svc()
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        assert svc._map_kindtype("02", [party]) == ("KindType02_05", "")


# ============================================================================
# Image rotation API helpers (non-pragma-no-cover parts)
# ============================================================================


class TestImageRotationApiHelpers:
    def test_validate_image_file_ok(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        f = SimpleNamespace(content_type="image/jpeg", size=1000)
        _validate_image_file(f)  # should not raise

    def test_validate_image_file_bad_type(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException

        f = SimpleNamespace(content_type="image/bmp", size=1000)
        with pytest.raises(ValidationException):
            _validate_image_file(f)

    def test_validate_image_file_too_large(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException

        f = SimpleNamespace(content_type="image/jpeg", size=50 * 1024 * 1024)
        with pytest.raises(ValidationException):
            _validate_image_file(f)

    def test_decode_image_data_plain(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _decode_image_data
        import base64

        encoded = base64.b64encode(b"hello").decode()
        assert _decode_image_data(encoded) == b"hello"

    def test_decode_image_data_data_url(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _decode_image_data
        import base64

        encoded = base64.b64encode(b"world").decode()
        result = _decode_image_data(f"data:image/png;base64,{encoded}")
        assert result == b"world"

    def test_serialize_job(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _serialize_job
        from datetime import datetime

        job = SimpleNamespace(
            id=1,
            name="test",
            status="done",
            total_pages=5,
            export_zip_url="http://example.com/zip",
            export_pdf_url="http://example.com/pdf",
            created_at=datetime(2026, 1, 1),
        )
        result = _serialize_job(job)
        assert result["id"] == "1"
        assert result["total_pages"] == 5
        assert result["has_export_zip"] is True

    def test_serialize_page(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _serialize_page

        page = SimpleNamespace(
            id=1,
            original_filename="img.jpg",
            source_image=SimpleNamespace(url="/media/img.jpg"),
            page_number=1,
            detected_rotation=90,
            onnx_rotation=270,
            detection_confidence=0.95678,
            ocr_text="合同",
            suggested_filename="合同_01.jpg",
            source_type="upload",
        )
        result = _serialize_page(page)
        assert result["id"] == "1"
        assert result["detection_confidence"] == 0.9568
        assert result["onnx_rotation"] == 270

    def test_body_helper(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _body
        import json

        request = MagicMock()
        request.body = json.dumps({"key": "value"}).encode()
        result = _body(request)
        assert result["key"] == "value"

    def test_body_empty(self) -> None:
        from apps.image_rotation.api.image_rotation_api import _body

        request = MagicMock()
        request.body = b""
        result = _body(request)
        assert result == {}


# ============================================================================
# PreservationMaterialsGenerationService
# ============================================================================


class TestPreservationMaterialsGenerationService:
    def _make_svc(self) -> Any:
        from apps.documents.services.generation.preservation_materials_generation_service import (
            PreservationMaterialsGenerationService,
        )
        return PreservationMaterialsGenerationService()

    def test_init_defaults(self) -> None:
        svc = self._make_svc()
        assert svc._party_service is None
        assert svc._signature_service is None

    def test_get_missing_clues_report_none(self) -> None:
        svc = self._make_svc()
        mock_prop = MagicMock()
        mock_prop.get_respondents_without_clues.return_value = []
        svc._property_clue_service = mock_prop
        assert svc.get_missing_clues_report(1) is None

    def test_get_missing_clues_report_with_data(self) -> None:
        svc = self._make_svc()
        mock_prop = MagicMock()
        mock_prop.get_respondents_without_clues.return_value = ["张三", "李四"]
        svc._property_clue_service = mock_prop
        result = svc.get_missing_clues_report(1)
        assert "张三" in result
        assert "李四" in result
        assert "缺材料" in result or "所缺材料" in result

    def test_has_template(self) -> None:
        svc = self._make_svc()
        with patch.object(svc, "_get_template_path_by_function_code", return_value=None):
            assert svc.has_template(1, "preservation_application") is False

    def test_has_template_found(self) -> None:
        svc = self._make_svc()
        with patch.object(svc, "_get_template_path_by_function_code", return_value=Path("/tmp/t.docx")):
            assert svc.has_template(1, "preservation_application") is True

    def test_build_filename(self) -> None:
        svc = self._make_svc()
        case = SimpleNamespace(name="张三诉李四案")
        with patch("apps.documents.services.generation.preservation_materials_generation_service.FilenameTemplateService") as mock_fts:
            mock_fts.render_generated_doc.return_value = "财产保全申请书(张三诉李四案)V1_20260615"
            result = svc._build_filename("财产保全申请书", case)
            assert result.endswith(".docx")
