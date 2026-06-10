"""Tests for AdversarialTrialService."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService
from apps.litigation_ai.services.mock_trial.types import AdversarialConfig, MockTrialStep


class TestCaseBrief:
    def setup_method(self):
        config = AdversarialConfig()
        case_info = {
            "case_name": "张三诉李四借贷纠纷",
            "cause_of_action": "民间借贷纠纷",
            "target_amount": "100000",
            "parties": [
                {"name": "张三", "legal_status": "原告", "is_our_side": True},
                {"name": "李四", "legal_status": "被告", "is_our_side": False},
            ],
        }
        self.service = AdversarialTrialService(config, case_info, "证据摘要文本")

    def test_case_brief_content(self):
        brief = self.service._case_brief()
        assert "张三诉李四" in brief
        assert "民间借贷纠纷" in brief
        assert "100000" in brief
        assert "张三" in brief
        assert "证据摘要文本" in brief

    def test_case_brief_no_amount(self):
        config = AdversarialConfig()
        case_info = {"case_name": "测试", "target_amount": None, "parties": []}
        svc = AdversarialTrialService(config, case_info, "")
        brief = svc._case_brief()
        assert "未知" in brief


class TestPartyNames:
    def setup_method(self):
        config = AdversarialConfig()
        self.case_info = {
            "parties": [
                {"name": "张三", "legal_status": "原告", "is_our_side": True},
                {"name": "李四", "legal_status": "被告", "is_our_side": False},
            ],
        }
        self.service = AdversarialTrialService(config, self.case_info, "")

    def test_party_names(self):
        p_name, d_name = self.service._party_names()
        assert p_name == "张三"
        assert d_name == "李四"

    def test_no_parties_uses_defaults(self):
        config = AdversarialConfig()
        svc = AdversarialTrialService(config, {"parties": []}, "")
        p_name, d_name = svc._party_names()
        assert p_name == "原告"
        assert d_name == "被告"


class TestIsSecond:
    def test_first_level(self):
        config = AdversarialConfig()
        config.trial_level = "first"
        svc = AdversarialTrialService(config, {"parties": []}, "")
        assert svc.is_second is False

    def test_second_level(self):
        config = AdversarialConfig()
        config.trial_level = "second"
        svc = AdversarialTrialService(config, {"parties": []}, "")
        assert svc.is_second is True


class TestRecordAndSend:
    def test_records_and_sends(self):
        config = AdversarialConfig()
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        asyncio.run(svc._record_and_send(send_cb, "plaintiff", "发言内容", "opening"))

        assert len(svc.transcript) == 1
        assert svc.transcript[0]["role"] == "plaintiff"
        assert svc.transcript[0]["content"] == "发言内容"
        assert svc.transcript[0]["stage"] == "opening"
        send_cb.assert_called_once()


class TestSendStage:
    def test_sends_stage_header(self):
        config = AdversarialConfig()
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        asyncio.run(svc._send_stage(send_cb, "opening", "宣布开庭"))

        send_cb.assert_called_once()
        call_args = send_cb.call_args[0][0]
        assert call_args["type"] == "system_message"
        assert "宣布开庭" in call_args["content"]


class TestAgentSpeak:
    def test_agent_speak(self):
        config = AdversarialConfig()
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        agent = MagicMock()
        agent.role = "plaintiff"
        agent.model = "gpt-4"
        agent.respond = AsyncMock(return_value="代理律师发言")

        result = asyncio.run(svc._agent_speak(agent, "请发言", send_cb, "statement"))

        assert result == "代理律师发言"
        assert len(svc.transcript) == 1


class TestWaitOrAi:
    def test_user_role_returns_none(self):
        config = AdversarialConfig()
        config.user_role = "plaintiff"
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        agent = MagicMock()
        agent.role = "plaintiff"

        result = asyncio.run(svc._wait_or_ai(agent, "prompt", send_cb, "stage"))
        assert result is None

    def test_ai_role_returns_content(self):
        config = AdversarialConfig()
        config.user_role = "observer"
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        agent = MagicMock()
        agent.role = "plaintiff"
        agent.model = "gpt-4"
        agent.respond = AsyncMock(return_value="AI发言")

        result = asyncio.run(svc._wait_or_ai(agent, "prompt", send_cb, "stage"))
        assert result == "AI发言"


class TestPhases:
    def test_phase_1_opening_first_trial(self):
        config = AdversarialConfig()
        config.trial_level = "first"
        case_info = {
            "case_name": "测试案件",
            "cause_of_action": "借贷纠纷",
            "parties": [
                {"name": "原告名", "legal_status": "原告", "is_our_side": True},
                {"name": "被告名", "legal_status": "被告", "is_our_side": False},
            ],
        }
        svc = AdversarialTrialService(config, case_info, "")
        send_cb = AsyncMock()

        asyncio.run(svc.phase_1_opening(send_cb))
        assert len(svc.transcript) >= 2

    def test_phase_1_opening_second_trial(self):
        config = AdversarialConfig()
        config.trial_level = "second"
        case_info = {
            "case_name": "测试案件",
            "cause_of_action": "借贷纠纷",
            "parties": [
                {"name": "上诉人", "legal_status": "原告", "is_our_side": True},
                {"name": "被上诉人", "legal_status": "被告", "is_our_side": False},
            ],
        }
        svc = AdversarialTrialService(config, case_info, "")
        send_cb = AsyncMock()

        asyncio.run(svc.phase_1_opening(send_cb))
        assert len(svc.transcript) >= 2

    def test_phase_3_rights_notice(self):
        config = AdversarialConfig()
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        asyncio.run(svc.phase_3_rights_notice(send_cb))
        assert len(svc.transcript) >= 3

    def test_phase_4_appeal_first_trial(self):
        config = AdversarialConfig()
        config.trial_level = "first"
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        result = asyncio.run(svc.phase_4_appeal(send_cb))
        assert result == ""

    def test_phase_10_mediation(self):
        config = AdversarialConfig()
        svc = AdversarialTrialService(config, {"parties": []}, "")
        send_cb = AsyncMock()

        asyncio.run(svc.phase_10_mediation(send_cb))
        assert len(svc.transcript) >= 3


class TestContinueDebate:
    def test_observer_role(self):
        config = AdversarialConfig()
        config.user_role = "observer"
        svc = AdversarialTrialService(config, {"parties": []}, "")

        send_cb = AsyncMock()
        set_step = AsyncMock()
        ctx = MagicMock()

        asyncio.run(svc._continue_debate(ctx, "input", send_cb, set_step))
        send_cb.assert_called()

    def test_plaintiff_role_calls_defendant(self):
        config = AdversarialConfig()
        config.user_role = "plaintiff"
        svc = AdversarialTrialService(config, {"parties": []}, "")

        svc.defendant = MagicMock()
        svc.defendant.role = "defendant"
        svc.defendant.model = "gpt-4"
        svc.defendant.respond = AsyncMock(return_value="被告反驳")

        send_cb = AsyncMock()
        set_step = AsyncMock()
        ctx = MagicMock()

        asyncio.run(svc._continue_debate(ctx, "原告论点", send_cb, set_step))
        assert send_cb.call_count >= 1

    def test_defendant_role_calls_plaintiff(self):
        config = AdversarialConfig()
        config.user_role = "defendant"
        svc = AdversarialTrialService(config, {"parties": []}, "")

        svc.plaintiff = MagicMock()
        svc.plaintiff.role = "plaintiff"
        svc.plaintiff.model = "gpt-4"
        svc.plaintiff.respond = AsyncMock(return_value="原告反驳")

        send_cb = AsyncMock()
        set_step = AsyncMock()
        ctx = MagicMock()

        asyncio.run(svc._continue_debate(ctx, "被告论点", send_cb, set_step))
        assert send_cb.call_count >= 1
