"""Additional coverage tests for automation.api.court_filing_helpers.

Covers remaining uncovered branches: _infer_filing_type with execution hints,
_build_agent_payloads edge cases, _build_material_slot_signals with attachment,
_score_slot_deduplicated edge cases, _match_slot execution fallback,
_build_session_status_payload timing, _update_session_task with all flags.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# _infer_filing_type — execution hints
# ---------------------------------------------------------------------------


class TestInferFilingTypeExecutionHints:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _infer_filing_type
        return _infer_filing_type

    def test_applicant_status_returns_execution(self):
        party = MagicMock()
        party.legal_status = "applicant"
        case = MagicMock()
        case.name = "普通案件"
        case.cause_of_action = "买卖合同纠纷"
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = []
            assert self._fn()(case=case, parties=[party]) == "execution"

    def test_case_name_with_execution_keyword(self):
        case = MagicMock()
        case.name = "申请执行案件"
        case.cause_of_action = ""
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = []
            assert self._fn()(case=case, parties=[]) == "execution"

    def test_material_type_with_execution_keyword(self):
        case = MagicMock()
        case.name = "普通案件"
        case.cause_of_action = ""
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = ["执行申请书"]
            assert self._fn()(case=case, parties=[]) == "execution"

    def test_civil_default(self):
        case = MagicMock()
        case.name = "买卖合同纠纷"
        case.cause_of_action = ""
        with patch("apps.cases.models.CaseMaterial") as MockCM:
            MockCM.objects.filter.return_value.values_list.return_value = []
            assert self._fn()(case=case, parties=[]) == "civil"


# ---------------------------------------------------------------------------
# _resolve_original_case_number
# ---------------------------------------------------------------------------


class TestResolveOriginalCaseNumber:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _resolve_original_case_number
        return _resolve_original_case_number

    def test_no_case_numbers(self):
        case = MagicMock()
        case.case_numbers = None
        assert self._fn()(case) == ""

    def test_active_number(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2025)粤01民初100号"
        case.case_numbers = qs
        assert self._fn()(case) == "(2025)粤01民初100号"

    def test_fallback_number(self):
        case = MagicMock()
        # active returns None
        active_qs = MagicMock()
        active_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        # fallback returns number
        fallback_qs = MagicMock()
        fallback_qs.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初50号"

        call_count = 0

        def qs_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return active_qs
            return fallback_qs

        case.case_numbers = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初50号"
        assert self._fn()(case) == "(2024)粤01民初50号"


# ---------------------------------------------------------------------------
# _build_party_payloads — legal person
# ---------------------------------------------------------------------------


class TestBuildPartyPayloadsLegal:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_party_payloads
        return _build_party_payloads

    def test_legal_person(self):
        party = MagicMock()
        party.client.client_type = "legal"
        party.client.name = "Test Corp"
        party.client.address = "地址"
        party.client.phone = "13800138000"
        party.client.id_number = "91440101MA59TEST8X"
        party.client.legal_representative = "张三"
        party.client.legal_representative_id_number = "110101199003077715"
        party.legal_status = "plaintiff"

        with patch("apps.core.utils.id_card_utils.IdCardUtils") as mock_id:
            plaintiffs, defendants, third_parties = self._fn()(parties=[party])
        assert len(plaintiffs) == 1
        assert plaintiffs[0]["uscc"] == "91440101MA59TEST8X"
        assert plaintiffs[0]["legal_rep"] == "张三"

    def test_third_party(self):
        party = MagicMock()
        party.client.client_type = "natural"
        party.client.name = "第三人"
        party.client.address = ""
        party.client.phone = ""
        party.client.id_number = "110101199003077715"
        party.legal_status = "third"

        with patch("apps.core.utils.id_card_utils.IdCardUtils") as mock_id:
            mock_id.extract_gender.return_value = "男"
            plaintiffs, defendants, third_parties = self._fn()(parties=[party])
        assert len(third_parties) == 1

    def test_unknown_status_excluded(self):
        party = MagicMock()
        party.client.client_type = "natural"
        party.client.name = "未知"
        party.client.address = ""
        party.client.phone = ""
        party.client.id_number = ""
        party.legal_status = "unknown_status"

        with patch("apps.core.utils.id_card_utils.IdCardUtils"):
            plaintiffs, defendants, third_parties = self._fn()(parties=[party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 0
        assert len(third_parties) == 0


# ---------------------------------------------------------------------------
# _to_valid_mobile
# ---------------------------------------------------------------------------


class TestToValidMobile:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _to_valid_mobile
        return _to_valid_mobile

    def test_valid_mobile(self):
        assert self._fn()("13800138000") == "13800138000"

    def test_with_dashes(self):
        assert self._fn()("138-0013-8000") == "13800138000"

    def test_invalid_too_short(self):
        assert self._fn()("12345") == ""

    def test_invalid_starts_with_wrong_digit(self):
        assert self._fn()("23800138000") == ""

    def test_empty(self):
        assert self._fn()("") == ""


# ---------------------------------------------------------------------------
# _apply_execution_party_fallbacks
# ---------------------------------------------------------------------------


class TestApplyExecutionPartyFallbacks:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _apply_execution_party_fallbacks
        return _apply_execution_party_fallbacks

    def test_fills_phone_from_agent(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": "addr"},
        ]
        agents = [{"phone": "13800138000"}]
        self._fn()(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_skips_non_natural(self):
        plaintiffs = [
            {"client_type": "legal", "phone": "", "address": ""},
        ]
        agents = [{"phone": "13800138000"}]
        self._fn()(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_no_agents(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": "addr"},
        ]
        self._fn()(plaintiffs=plaintiffs, agents=[])
        assert plaintiffs[0]["phone"] == ""


# ---------------------------------------------------------------------------
# _build_execution_reason_text
# ---------------------------------------------------------------------------


class TestBuildExecutionReasonText:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_execution_reason_text
        return _build_execution_reason_text

    def test_with_cause(self):
        case = MagicMock()
        case.cause_of_action = "买卖合同纠纷"
        result = self._fn()(case=case, original_case_number="(2025)粤01民初100号")
        assert "买卖合同纠纷" in result

    def test_without_cause(self):
        case = MagicMock()
        case.cause_of_action = ""
        result = self._fn()(case=case, original_case_number="(2025)粤01民初100号")
        assert "生效法律文书" in result

    def test_empty_case_number(self):
        case = MagicMock()
        case.cause_of_action = ""
        result = self._fn()(case=case, original_case_number="")
        assert "相关" in result


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _normalize_text
        return _normalize_text

    def test_strips_special_chars(self):
        result = self._fn()("hello-world (test)")
        assert result == "helloworldtest"

    def test_lowercase(self):
        assert self._fn()("ABC") == "abc"


# ---------------------------------------------------------------------------
# _score_slot_for_signal
# ---------------------------------------------------------------------------


class TestScoreSlotForSignal:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _score_slot_for_signal
        return _score_slot_for_signal

    def test_empty_signal(self):
        assert self._fn()(signal="", strong=("a",), weak=(), exclude=()) == 0

    def test_strong_match(self):
        assert self._fn()(signal="起诉状", strong=("起诉状",), weak=(), exclude=()) == 5

    def test_weak_match(self):
        assert self._fn()(signal="证据材料", strong=(), weak=("证据",), exclude=()) == 2

    def test_exclude_penalty(self):
        assert self._fn()(signal="执行申请书", strong=(), weak=(), exclude=("执行申请书",)) == -6


# ---------------------------------------------------------------------------
# _score_slot_deduplicated — primary signals
# ---------------------------------------------------------------------------


class TestScoreSlotDeduplicated:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _score_slot_deduplicated
        return _score_slot_deduplicated

    def test_empty_signals(self):
        assert self._fn()(
            primary_signals=[], secondary_signals=[], strong=("a",), weak=(), exclude=()
        ) == 0

    def test_primary_strong_match_doubled(self):
        assert self._fn()(
            primary_signals=["起诉状"], secondary_signals=[], strong=("起诉状",), weak=(), exclude=()
        ) == 10  # 5 * 2

    def test_primary_exclude_doubled(self):
        assert self._fn()(
            primary_signals=["执行申请书"], secondary_signals=[], strong=(), weak=(), exclude=("执行申请书",)
        ) == -12  # -6 * 2

    def test_secondary_deduplicated(self):
        # Same keyword in multiple secondary signals should only count once
        score = self._fn()(
            primary_signals=[],
            secondary_signals=["起诉状.pdf", "起诉状_副本.pdf"],
            strong=("起诉状",), weak=(), exclude=()
        )
        assert score == 5  # counted once, not twice


# ---------------------------------------------------------------------------
# _match_slot — execution fallback
# ---------------------------------------------------------------------------


class TestMatchSlotFallback:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _match_slot
        return _match_slot

    def test_execution_apply_fallback(self):
        material = MagicMock()
        material.type_name = "执行申请书"
        material.type = MagicMock()
        material.type.name = ""
        material.source_attachment = None
        material.source_attachment = MagicMock()
        material.source_attachment.file.name = ""
        material.source_attachment.log = None

        file_path = Path("/test/执行申请书.pdf")

        with patch(
            "plugins.court_automation.filing.helpers._build_material_slot_signals",
            return_value=(["执行申请书"], ["/test/执行申请书.pdf"]),
        ):
            with patch(
                "plugins.court_automation.filing.helpers._score_slot_deduplicated",
                return_value=0,
            ):
                result = self._fn()(material=material, file_path=file_path, filing_type="execution")
        assert result == "0"

    def test_delivery_address_fallback(self):
        material = MagicMock()
        file_path = Path("/test/送达地址确认书.pdf")

        with patch(
            "plugins.court_automation.filing.helpers._build_material_slot_signals",
            return_value=([], ["送达地址确认书"]),
        ):
            with patch(
                "plugins.court_automation.filing.helpers._score_slot_deduplicated",
                return_value=0,
            ):
                result = self._fn()(material=material, file_path=file_path, filing_type="civil")
        assert result == "4"

    def test_preservation_fallback(self):
        material = MagicMock()
        file_path = Path("/test/保全申请书.pdf")

        with patch(
            "plugins.court_automation.filing.helpers._build_material_slot_signals",
            return_value=([], ["保全申请书"]),
        ):
            with patch(
                "plugins.court_automation.filing.helpers._score_slot_deduplicated",
                return_value=0,
            ):
                result = self._fn()(material=material, file_path=file_path, filing_type="civil")
        assert result == "5"


# ---------------------------------------------------------------------------
# _build_session_status_payload — all statuses
# ---------------------------------------------------------------------------


class TestBuildSessionStatusPayload:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_session_status_payload
        return _build_session_status_payload

    def test_pending_status(self):
        task = MagicMock()
        task.status = "pending"
        task.id = 1
        task.result = {"message": "执行中...", "timing": {"start": 1.0}}
        result = self._fn()(task=task)
        assert result["status"] == "in_progress"
        assert "timing" in result

    def test_success_status(self):
        task = MagicMock()
        task.status = "success"
        task.id = 2
        task.result = {"message": "完成", "timing": {"start": 1.0}}
        result = self._fn()(task=task)
        assert result["status"] == "completed"

    def test_failed_status_with_error_message(self):
        task = MagicMock()
        task.status = "failed"
        task.id = 3
        task.error_message = "网络错误"
        task.result = {"timing": None}
        result = self._fn()(task=task)
        assert result["status"] == "failed"
        assert result["message"] == "网络错误"

    def test_failed_status_no_error_uses_result_message(self):
        task = MagicMock()
        task.status = "failed"
        task.id = 4
        task.error_message = ""
        task.result = {"message": "失败原因", "timing": None}
        result = self._fn()(task=task)
        assert result["message"] == "失败原因"

    def test_failed_status_no_messages_uses_default(self):
        task = MagicMock()
        task.status = "failed"
        task.id = 5
        task.error_message = ""
        task.result = {"timing": None}
        result = self._fn()(task=task)
        assert result["message"] == "立案失败"


# ---------------------------------------------------------------------------
# _update_session_task — with all flags
# ---------------------------------------------------------------------------


class TestUpdateSessionTask:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _update_session_task
        return _update_session_task

    def test_none_session_id(self):
        self._fn()(session_id=None, status="running")

    def test_with_all_flags(self):
        # _do_update runs in the current thread when no event loop is running
        # We need to patch the inner imports too
        with patch("apps.automation.models.ScraperTask") as MockTask, \
             patch("django.db.close_old_connections"):
            self._fn()(
                session_id=1,
                status="success",
                error_message="",
                result={"key": "val"},
                set_started=True,
                set_finished=True,
            )
            MockTask.objects.filter.assert_called_once()
