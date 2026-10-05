"""mock_trial_consumer.py 各消息 handler 的行为测试.

覆盖 MODE_SELECT / MODEL_CONFIG / SIMULATION / SUMMARY 四类 step 分发、
select_mode / skip_evidence / end_debate / set_difficulty handler、
receive 的错误输入路径，以及「同一连接复用 flow 实例」回归的补充面。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.mock_trial_consumer import MockTrialConsumer
from apps.litigation_ai.services.mock_trial.types import MockTrialStep


def _make_consumer(**overrides: Any) -> MockTrialConsumer:
    consumer = MockTrialConsumer.__new__(MockTrialConsumer)
    consumer.session_id = overrides.get("session_id", "mt-sess")
    consumer.user = overrides.get("user", SimpleNamespace(id=9))
    consumer.session = overrides.get("session", SimpleNamespace(case_id=5))
    consumer.flow = None
    consumer.send = AsyncMock()
    consumer._add_message = AsyncMock()
    consumer._get_current_step = AsyncMock(return_value=MockTrialStep.MODE_SELECT)
    return consumer


def _flow_mock() -> MagicMock:
    flow = MagicMock()
    flow.handle_init = AsyncMock()
    flow.handle_mode_select = AsyncMock()
    flow.handle_model_config = AsyncMock()
    flow.handle_simulation = AsyncMock()
    flow.get_current_step = MagicMock(return_value=MockTrialStep.MODE_SELECT)
    return flow


class TestHandleUserMessageSteps:
    @pytest.mark.asyncio
    async def test_mode_select_step_routes_to_handle_mode_select(self) -> None:
        consumer = _make_consumer()
        consumer._get_current_step = AsyncMock(return_value=MockTrialStep.MODE_SELECT)
        flow = _flow_mock()

        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_user_message({"content": "judge"})

        consumer._add_message.assert_awaited_once_with("user", "judge")
        flow.handle_mode_select.assert_awaited_once()
        ctx = flow.handle_mode_select.await_args.args[0]
        assert ctx.session_id == "mt-sess"
        assert ctx.case_id == 5
        assert ctx.user_id == 9

    @pytest.mark.asyncio
    async def test_model_config_step_routes_to_handle_model_config(self) -> None:
        consumer = _make_consumer()
        consumer._get_current_step = AsyncMock(return_value=MockTrialStep.MODEL_CONFIG)
        flow = _flow_mock()

        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_user_message({"content": "gpt-4o"})

        assert flow.handle_model_config.await_count == 1
        assert flow.handle_simulation.await_count == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "step",
        [
            MockTrialStep.SIMULATION,
            MockTrialStep.FOCUS_ANALYSIS,
            MockTrialStep.COURT_OPENING,
            MockTrialStep.IDENTITY_CHECK,
            MockTrialStep.RIGHTS_NOTICE,
            MockTrialStep.APPEAL_STATEMENT,
            MockTrialStep.PLAINTIFF_STATEMENT,
            MockTrialStep.DEFENDANT_RESPONSE,
            MockTrialStep.COURT_INVESTIGATION,
            MockTrialStep.COURT_DEBATE,
            MockTrialStep.FINAL_STATEMENT,
            MockTrialStep.MEDIATION,
            MockTrialStep.COURT_SUMMARY,
        ],
    )
    async def test_simulation_family_steps_route_to_handle_simulation(self, step: MockTrialStep) -> None:
        consumer = _make_consumer()
        consumer._get_current_step = AsyncMock(return_value=step)
        flow = _flow_mock()

        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_user_message({"content": "反对"})

        assert flow.handle_simulation.await_count == 1

    @pytest.mark.asyncio
    async def test_summary_step_tells_session_closed(self) -> None:
        consumer = _make_consumer()
        consumer._get_current_step = AsyncMock(return_value=MockTrialStep.SUMMARY)
        flow = _flow_mock()

        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_user_message({"content": "总结一下"})

        flow.handle_simulation.assert_not_awaited()
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "system_message"
        assert "已结束" in payload["content"]

    @pytest.mark.asyncio
    async def test_empty_content_rejected_before_db_write(self) -> None:
        consumer = _make_consumer()
        await consumer._handle_user_message({"content": "   "})
        consumer._add_message.assert_not_awaited()
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"

    @pytest.mark.asyncio
    async def test_missing_content_key_rejected(self) -> None:
        consumer = _make_consumer()
        await consumer._handle_user_message({})
        consumer._add_message.assert_not_awaited()
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"


class TestSelectModeHandler:
    @pytest.mark.asyncio
    async def test_select_mode_dispatches(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_select_mode({"mode": "judge"})

        consumer._add_message.assert_awaited_once_with("user", "选择模式：judge")
        flow.handle_mode_select.assert_awaited_once()
        assert flow.handle_mode_select.await_args.args[1] == "judge"
        ctx = flow.handle_mode_select.await_args.args[0]
        assert ctx.current_step == MockTrialStep.MODE_SELECT

    @pytest.mark.asyncio
    async def test_select_mode_missing_mode(self) -> None:
        consumer = _make_consumer()
        await consumer._handle_select_mode({"mode": ""})
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"
        assert "mode" in payload["message"]


class TestSkipEvidenceAndEndDebate:
    @pytest.mark.asyncio
    async def test_skip_evidence_sends_skip_keyword(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_skip_evidence({})

        consumer._add_message.assert_awaited_once_with("user", "跳过剩余证据")
        flow.handle_simulation.assert_awaited_once()
        assert flow.handle_simulation.await_args.args[1] == "跳过"
        ctx = flow.handle_simulation.await_args.args[0]
        assert ctx.current_step == MockTrialStep.SIMULATION

    @pytest.mark.asyncio
    async def test_end_debate_sends_end_keyword(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch(
            "apps.litigation_ai.services.mock_trial.mock_trial_flow_service.MockTrialFlowService",
            return_value=flow,
        ):
            await consumer._handle_end_debate({})

        consumer._add_message.assert_awaited_once_with("user", "结束辩论")
        flow.handle_simulation.assert_awaited_once()
        assert flow.handle_simulation.await_args.args[1] == "结束"


class TestSetDifficulty:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    async def test_valid_difficulty_persisted(self, difficulty: str) -> None:
        consumer = _make_consumer()
        repo = MagicMock()
        repo.update_metadata = AsyncMock()

        with patch(
            "apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository",
            return_value=repo,
        ):
            await consumer._handle_set_difficulty({"difficulty": difficulty})

        assert repo.update_metadata.await_args.args == ("mt-sess", {"debate_difficulty": difficulty})
        assert repo.update_metadata.await_count == 1

    @pytest.mark.asyncio
    async def test_invalid_difficulty_rejected(self) -> None:
        consumer = _make_consumer()
        with patch("apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository") as repo_cls:
            await consumer._handle_set_difficulty({"difficulty": "impossible"})

        assert repo_cls.call_count == 0
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"
        assert "难度" in payload["message"]

    @pytest.mark.asyncio
    async def test_default_difficulty_is_medium(self) -> None:
        consumer = _make_consumer()
        repo = MagicMock()
        repo.update_metadata = AsyncMock()
        with patch(
            "apps.litigation_ai.services.flow.session_repository.LitigationSessionRepository",
            return_value=repo,
        ):
            await consumer._handle_set_difficulty({})
        assert repo.update_metadata.await_args.args == ("mt-sess", {"debate_difficulty": "medium"})


class TestReceivePaths:
    """receive 的输入校验分支（JSON 坏格式 / 非对象 / 缺 type / 未知 type）。"""

    def _consumer(self) -> MockTrialConsumer:
        consumer = _make_consumer()
        consumer.receive = MockTrialConsumer.receive.__get__(consumer)
        return consumer

    @pytest.mark.asyncio
    async def test_empty_text(self) -> None:
        consumer = self._consumer()
        await consumer.receive(text_data="")
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"
        assert payload["message"] == "消息内容为空"

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        consumer = self._consumer()
        await consumer.receive(text_data="not-json{")
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"
        assert "格式错误" in payload["message"]

    @pytest.mark.asyncio
    async def test_non_dict_payload(self) -> None:
        consumer = self._consumer()
        await consumer.receive(text_data='["array"]')
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["message"] == "消息必须是 JSON 对象"

    @pytest.mark.asyncio
    async def test_missing_type(self) -> None:
        consumer = self._consumer()
        await consumer.receive(text_data='{"content": "hi"}')
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["message"] == "缺少消息类型"

    @pytest.mark.asyncio
    async def test_unknown_type(self) -> None:
        consumer = self._consumer()
        await consumer.receive(text_data='{"type": "wat"}')
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert "不支持的消息类型" in payload["message"]

    @pytest.mark.asyncio
    async def test_handler_exception_surfaced_as_error(self) -> None:
        consumer = self._consumer()
        consumer._get_current_step = AsyncMock(side_effect=RuntimeError("db down"))
        await consumer.receive(text_data='{"type": "user_message", "content": "hi"}')
        # 异常被 receive 捕获并走 ExceptionPresenter 包装为 error 帧
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "error"


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_exception_swallowed(self) -> None:
        consumer = _make_consumer()
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_discard = AsyncMock(side_effect=RuntimeError("layer gone"))
        consumer.channel_name = "chan-1"
        # 不抛错即通过；再断言确实尝试过 discard
        result = await consumer.disconnect(1000)
        assert result is None
        assert consumer.channel_layer.group_discard.await_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_without_session(self) -> None:
        consumer = _make_consumer(session_id=None)
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_discard = AsyncMock()
        await consumer.disconnect(1001)
        assert consumer.channel_layer.group_discard.await_count == 0


class TestDbBackedHelpers:
    """_get_session / _add_message / _get_current_step 的委托逻辑。"""

    def _bare_consumer(self, **overrides: Any) -> MockTrialConsumer:
        """构造未遮蔽 DB helper 的 consumer（删除实例级 AsyncMock 代理）。"""
        consumer = _make_consumer(**overrides)
        del consumer._add_message
        del consumer._get_current_step
        return consumer

    @pytest.mark.asyncio
    async def test_get_session_filters_mock_trial_type(self) -> None:
        consumer = _make_consumer()
        found = SimpleNamespace(pk=1)
        with patch("apps.litigation_ai.models.LitigationSession") as mock_model:
            mock_model.objects.filter.return_value.first.return_value = found
            result = await consumer._get_session("mt-sess")

        assert result is found
        # 必须限定 session_type="mock_trial"，防止串到文书生成会话
        assert mock_model.objects.filter.call_args.kwargs == {"session_id": "mt-sess", "session_type": "mock_trial"}

    @pytest.mark.asyncio
    async def test_add_message_uses_conversation_service(self) -> None:
        consumer = self._bare_consumer()
        created = object()
        conv_service = MagicMock()
        conv_service.add_message.return_value = created
        with patch("apps.litigation_ai.services.LitigationConversationService", return_value=conv_service):
            result = await consumer._add_message("user", "内容", {"k": 1})

        assert result is created
        conv_service.add_message.assert_called_once_with(
            session_id="mt-sess", role="user", content="内容", metadata={"k": 1}
        )

    @pytest.mark.asyncio
    async def test_add_message_defaults(self) -> None:
        consumer = self._bare_consumer(session_id=None)
        conv_service = MagicMock()
        with patch("apps.litigation_ai.services.LitigationConversationService", return_value=conv_service):
            await consumer._add_message("user", "hi")
        assert conv_service.add_message.call_count == 1
        assert conv_service.add_message.call_args.kwargs == {
            "session_id": "",
            "role": "user",
            "content": "hi",
            "metadata": {},
        }

    @pytest.mark.asyncio
    async def test_get_current_step_delegates_to_flow(self) -> None:
        consumer = self._bare_consumer(session_id="step-sess")
        flow = MagicMock()
        flow.get_current_step = MagicMock(return_value=MockTrialStep.SUMMARY)
        result = await consumer._get_current_step(flow)
        assert result == MockTrialStep.SUMMARY
        flow.get_current_step.assert_called_once_with("step-sess")
