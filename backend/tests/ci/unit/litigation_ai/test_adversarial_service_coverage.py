"""测试模拟庭审对抗服务的纯逻辑方法

覆盖: apps/litigation_ai/services/mock_trial/adversarial_service.py
重点: _case_brief, _party_names, __init__ 属性设置
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.services.mock_trial.types import AdversarialConfig, MockTrialStep, TrialLevel


# ============================================================
# Helper
# ============================================================


def _make_config(
    *,
    trial_level: TrialLevel = TrialLevel.FIRST,
    user_role: str = "plaintiff",
    debate_rounds: int = 2,
    plaintiff_model: str = "gpt-4o",
    defendant_model: str = "gpt-4o",
    judge_model: str = "gpt-4o",
) -> AdversarialConfig:
    return AdversarialConfig(
        trial_level=trial_level,
        user_role=user_role,
        debate_rounds=debate_rounds,
        plaintiff_model=plaintiff_model,
        defendant_model=defendant_model,
        judge_model=judge_model,
    )


def _make_case_info() -> dict:
    return {
        "case_name": "张三诉李四借款合同纠纷",
        "cause_of_action": "借款合同纠纷",
        "target_amount": "100000",
        "parties": [
            {"name": "张三", "legal_status": "原告", "is_our_side": True},
            {"name": "李四", "legal_status": "被告", "is_our_side": False},
        ],
    }


# ============================================================
# __init__
# ============================================================


class TestAdversarialTrialServiceInit:
    """测试初始化"""

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_is_second_true_for_second_trial(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        config = _make_config(trial_level=TrialLevel.SECOND)
        svc = AdversarialTrialService(config, _make_case_info(), "证据文本")
        assert svc.is_second is True

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_is_second_false_for_first_trial(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        config = _make_config(trial_level=TrialLevel.FIRST)
        svc = AdversarialTrialService(config, _make_case_info(), "证据文本")
        assert svc.is_second is False

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_transcript_starts_empty(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "")
        assert svc.transcript == []

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_agents_created(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "")
        assert mock_agent.call_count == 3  # plaintiff, defendant, judge


# ============================================================
# _case_brief
# ============================================================


class TestCaseBrief:
    """测试案件摘要生成"""

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_contains_case_name(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "借据证据")
        brief = svc._case_brief()
        assert "张三诉李四借款合同纠纷" in brief
        assert "借款合同纠纷" in brief
        assert "100000" in brief
        assert "张三" in brief
        assert "被告" in brief
        assert "借据证据" in brief

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_with_empty_case_info(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), {}, "")
        brief = svc._case_brief()
        assert "案件名称：" in brief
        assert "当事人：" in brief

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_our_side_label(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        info = _make_case_info()
        svc = AdversarialTrialService(_make_config(), info, "")
        brief = svc._case_brief()
        assert "我方" in brief
        assert "对方" in brief


# ============================================================
# _party_names
# ============================================================


class TestPartyNames:
    """测试当事人名称提取"""

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_extracts_plaintiff_and_defendant(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "")
        p_name, d_name = svc._party_names()
        assert p_name == "张三"
        assert d_name == "李四"

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_fallback_to_defaults(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), {"parties": []}, "")
        p_name, d_name = svc._party_names()
        assert p_name == "原告"
        assert d_name == "被告"

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    def test_our_side_is_plaintiff(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        info = {
            "parties": [
                {"name": "王五", "legal_status": "原告", "is_our_side": True},
                {"name": "赵六", "legal_status": "被告", "is_our_side": False},
            ]
        }
        svc = AdversarialTrialService(_make_config(), info, "")
        p_name, d_name = svc._party_names()
        assert p_name == "王五"
        assert d_name == "赵六"


# ============================================================
# _record_and_send
# ============================================================


class TestRecordAndSend:
    """测试记录和发送"""

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    @pytest.mark.asyncio
    async def test_appends_to_transcript(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "")
        send_cb = AsyncMock()
        await svc._record_and_send(send_cb, "judge", "test content", "opening")
        assert len(svc.transcript) == 1
        assert svc.transcript[0]["role"] == "judge"
        assert svc.transcript[0]["content"] == "test content"
        assert svc.transcript[0]["stage"] == "opening"

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    @pytest.mark.asyncio
    async def test_calls_send_callback(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "")
        send_cb = AsyncMock()
        await svc._record_and_send(send_cb, "judge", "content", "opening")
        send_cb.assert_called_once()
        call_args = send_cb.call_args[0][0]
        assert call_args["type"] == "assistant_complete"
        assert "content" in call_args


# ============================================================
# _send_stage
# ============================================================


class TestSendStage:
    """测试阶段通知发送"""

    @patch("apps.litigation_ai.services.mock_trial.adversarial_service.Agent")
    @pytest.mark.asyncio
    async def test_sends_system_message(self, mock_agent: MagicMock) -> None:
        from apps.litigation_ai.services.mock_trial.adversarial_service import AdversarialTrialService

        svc = AdversarialTrialService(_make_config(), _make_case_info(), "")
        send_cb = AsyncMock()
        await svc._send_stage(send_cb, "opening", "宣布开庭")
        call_args = send_cb.call_args[0][0]
        assert call_args["type"] == "system_message"
        assert "宣布开庭" in call_args["content"]
        assert call_args["metadata"]["stage"] == "opening"
