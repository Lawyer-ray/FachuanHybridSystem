"""litigation_consumer.py 流程模式（非 Agent 模式）行为测试.

覆盖 handle_user_message 的 step 分发、_handle_document_type_step 的
LLM 解析成功/失败分支、select_evidence / confirm_generate 直通 handler
以及 send_history_messages / agent_service 延迟加载。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.consumers.litigation_consumer import LitigationConsumer
from apps.litigation_ai.services import ConversationStep


def _make_consumer(**overrides: Any) -> LitigationConsumer:
    consumer = LitigationConsumer.__new__(LitigationConsumer)
    consumer.session_id = overrides.get("session_id", "sess-flow")
    consumer.user = overrides.get("user", SimpleNamespace(id=42))
    consumer.session = overrides.get("session", SimpleNamespace(case_id=7))
    consumer._agent_service = overrides.get("_agent_service")
    consumer.send = AsyncMock()
    consumer._add_message = AsyncMock()
    consumer._get_current_step = AsyncMock()
    return consumer


def _flow_mock() -> MagicMock:
    flow = MagicMock()
    flow.handle_init = AsyncMock()
    flow.handle_document_type_selection = AsyncMock()
    flow.handle_litigation_goal_collection = AsyncMock()
    flow.handle_evidence_selection = AsyncMock()
    flow.handle_doc_plan_selection = AsyncMock()
    flow.handle_refining = AsyncMock()
    flow.handle_confirm_generate = AsyncMock()
    flow.get_current_step = MagicMock(return_value=ConversationStep.INIT)
    return flow


class TestHandleUserMessageFlowMode:
    """handle_user_message 非 Agent 模式：写消息 + 按当前 step 分发。"""

    @pytest.mark.asyncio
    async def test_persists_user_message_then_dispatches(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        consumer._get_current_step = AsyncMock(return_value=ConversationStep.INIT)

        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_user_message({"content": "你好", "metadata": {"k": "v"}})

        consumer._add_message.assert_awaited_once_with("user", "你好", {"k": "v"})
        flow.handle_init.assert_awaited_once()
        # send_cb 传的是 _send_flow_message
        send_cb = flow.handle_init.await_args.args[1]
        assert send_cb == consumer._send_flow_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("step", "expected_call"),
        [
            (ConversationStep.DOCUMENT_TYPE, "__doc_type_step__"),  # 走 _handle_document_type_step，单独测
            (ConversationStep.LITIGATION_GOAL, "handle_litigation_goal_collection"),
            (ConversationStep.EVIDENCE_SELECTION, "handle_evidence_selection"),
            (ConversationStep.DOC_PLAN, "handle_doc_plan_selection"),
        ],
    )
    async def test_dispatch_by_step_routes(self, step: ConversationStep, expected_call: str) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        consumer._get_current_step = AsyncMock(return_value=step)

        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            # DOCUMENT_TYPE 分支内部查库 + LLM，这里替换成 spy 以免真实依赖
            if expected_call == "__doc_type_step__":
                consumer._handle_document_type_step = AsyncMock()
            await consumer.handle_user_message({"content": "生成起诉状"})

        assert consumer._add_message.await_count == 1
        if expected_call == "__doc_type_step__":
            assert consumer._handle_document_type_step.await_count == 1
        else:
            assert getattr(flow, expected_call).await_count == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("step", [ConversationStep.GENERATING, ConversationStep.REFINING])
    async def test_dispatch_by_step_generating_refining_uses_handle_refining(self, step: ConversationStep) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        consumer._get_current_step = AsyncMock(return_value=step)

        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_user_message({"content": "再改改"})

        assert flow.handle_refining.await_count == 1

    @pytest.mark.asyncio
    async def test_dispatch_by_step_unknown_step_noop(self) -> None:
        """COMPLETED 等未登记 step：不抛错也不调任何 handler。"""
        consumer = _make_consumer()
        flow = _flow_mock()
        consumer._get_current_step = AsyncMock(return_value=ConversationStep.COMPLETED)

        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_user_message({"content": "继续"})

        assert flow.handle_init.await_count == 0
        assert flow.handle_refining.await_count == 0
        assert consumer.send.await_count == 0  # 未触发错误帧

    @pytest.mark.asyncio
    async def test_agent_mode_short_circuits_flow(self) -> None:
        consumer = _make_consumer()
        agent_svc = AsyncMock()
        agent_svc.handle_message.return_value = {"type": "assistant_complete"}
        consumer._agent_service = agent_svc

        with patch("apps.litigation_ai.consumers.litigation_consumer._use_agent_mode", return_value=True):
            await consumer.handle_user_message({"content": "hello"})

        assert agent_svc.handle_message.await_count == 1
        assert consumer._add_message.await_count == 0


class TestHandleDocumentTypeStep:
    """_handle_document_type_step：LLM 解析成功 → selection；失败 → 提示语。"""

    @pytest.mark.asyncio
    async def test_parsed_type_calls_selection(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        db_session = SimpleNamespace(metadata={"recommended_types": ["complaint", "defense"]})
        mock_model = MagicMock()
        mock_model.objects.get.return_value = db_session

        chain = MagicMock()
        chain.arun = AsyncMock(return_value=SimpleNamespace(document_type="complaint"))

        with (
            patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow),
            patch("apps.litigation_ai.models.LitigationSession", mock_model),
            patch("apps.litigation_ai.chains.DocumentTypeParseChain", return_value=chain),
        ):
            await consumer._handle_document_type_step(flow, object(), "起诉状")

        chain.arun.assert_awaited_once()
        # recommended_types 透传为 allowed_types
        assert chain.arun.await_args.kwargs["allowed_types"] == ["complaint", "defense"]
        flow.handle_document_type_selection.assert_awaited_once()
        assert flow.handle_document_type_selection.await_args.args[1] == "complaint"

    @pytest.mark.asyncio
    async def test_parse_failure_sends_hint(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        db_session = SimpleNamespace(metadata=None)
        mock_model = MagicMock()
        mock_model.objects.get.return_value = db_session

        chain = MagicMock()
        chain.arun = AsyncMock(side_effect=RuntimeError("llm down"))

        with (
            patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow),
            patch("apps.litigation_ai.models.LitigationSession", mock_model),
            patch("apps.litigation_ai.chains.DocumentTypeParseChain", return_value=chain),
        ):
            await consumer._handle_document_type_step(flow, object(), "不知道")

        flow.handle_document_type_selection.assert_not_awaited()
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "system_message"
        assert "起诉状" in payload["content"]

    @pytest.mark.asyncio
    async def test_empty_parsed_type_sends_hint(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        mock_model = MagicMock()
        mock_model.objects.get.return_value = SimpleNamespace(metadata={})

        chain = MagicMock()
        chain.arun = AsyncMock(return_value=SimpleNamespace(document_type=""))

        with (
            patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow),
            patch("apps.litigation_ai.models.LitigationSession", mock_model),
            patch("apps.litigation_ai.chains.DocumentTypeParseChain", return_value=chain),
        ):
            await consumer._handle_document_type_step(flow, object(), "啥")

        # metadata 无 recommended_types 时回退到默认 4 类
        assert chain.arun.await_args.kwargs["allowed_types"] == [
            "complaint",
            "defense",
            "counterclaim",
            "counterclaim_defense",
        ]
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "system_message"


class TestDirectHandlers:
    """select_document_type / select_evidence / confirm_generate 直通 flow service。"""

    @pytest.mark.asyncio
    async def test_handle_select_document_type(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_select_document_type({"document_type": "defense"})

        flow.handle_document_type_selection.assert_awaited_once()
        ctx = flow.handle_document_type_selection.await_args.args[0]
        assert ctx.current_step == ConversationStep.DOCUMENT_TYPE
        assert ctx.case_id == 7

    @pytest.mark.asyncio
    async def test_handle_select_evidence_passes_ids(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_select_evidence(
                {
                    "evidence_list_ids": [1],
                    "evidence_item_ids": [2, 3],
                    "our_evidence_item_ids": [2],
                    "opponent_evidence_item_ids": [3],
                }
            )

        args = flow.handle_evidence_selection.await_args.args
        assert args[1:5] == ([1], [2, 3], [2], [3])
        assert args[0].current_step == ConversationStep.EVIDENCE_SELECTION

    @pytest.mark.asyncio
    async def test_handle_select_evidence_null_lists(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_select_evidence(
                {
                    "evidence_list_ids": None,
                    "evidence_item_ids": None,
                    "our_evidence_item_ids": None,
                    "opponent_evidence_item_ids": None,
                }
            )
        args = flow.handle_evidence_selection.await_args.args
        assert args[1:5] == ([], [], [], [])

    @pytest.mark.asyncio
    async def test_handle_confirm_generate(self) -> None:
        consumer = _make_consumer()
        flow = _flow_mock()
        with patch("apps.litigation_ai.services.ConversationFlowService", return_value=flow):
            await consumer.handle_confirm_generate({})
        flow.handle_confirm_generate.assert_awaited_once()
        ctx = flow.handle_confirm_generate.await_args.args[0]
        assert ctx.current_step == ConversationStep.COMPLETED


class TestAgentModeInternals:
    """Agent 模式内部：流式回调与 agent_service 延迟加载。"""

    def test_agent_service_lazy_loads_once(self) -> None:
        consumer = _make_consumer()
        with patch(
            "apps.litigation_ai.services.generation.litigation_agent_service.LitigationAgentService"
        ) as mock_cls:
            svc1 = consumer.agent_service
            svc2 = consumer.agent_service
        assert svc1 is svc2
        assert consumer._agent_service is svc1
        mock_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_user_message_agent_streams_then_completes(self) -> None:
        """带 stream_callback 的 agent 调用：回调推流式块，结果整包下发。"""
        consumer = _make_consumer()

        async def fake_handle_message(**kwargs: Any) -> dict[str, Any]:
            cb = kwargs["stream_callback"]
            await cb("chunk1 ")
            await cb("chunk2")
            return {"type": "assistant_complete", "content": "final"}

        agent_svc = AsyncMock()
        agent_svc.handle_message.side_effect = fake_handle_message
        consumer._agent_service = agent_svc

        await consumer._handle_user_message_agent("问题", {"m": 1})

        sent = [json.loads(c.kwargs["text_data"]) for c in consumer.send.await_args_list]
        assert {"type": "stream_chunk", "content": "chunk1 "} in sent
        assert {"type": "stream_chunk", "content": "chunk2"} in sent
        assert sent[-1] == {"type": "assistant_complete", "content": "final"}
        # 关键参数透传
        kwargs = agent_svc.handle_message.await_args.kwargs
        assert kwargs["session_id"] == "sess-flow"
        assert kwargs["case_id"] == 7
        assert kwargs["user_message"] == "问题"


class TestSendHistoryMessages:
    @pytest.mark.asyncio
    async def test_maps_message_rows(self) -> None:
        from datetime import datetime

        consumer = _make_consumer()
        rows = [
            SimpleNamespace(
                id=1,
                role="user",
                content="你好",
                metadata={"a": 1},
                created_at=datetime(2026, 1, 2, 3, 4, 5),
            )
        ]
        conv_service = MagicMock()
        conv_service.get_messages.return_value = rows

        with patch("apps.litigation_ai.services.LitigationConversationService", return_value=conv_service):
            await consumer.send_history_messages()

        conv_service.get_messages.assert_called_once_with("sess-flow", limit=50, offset=0)
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload["type"] == "history"
        assert payload["messages"][0]["id"] == 1
        assert payload["messages"][0]["created_at"] == "2026-01-02T03:04:05"

    @pytest.mark.asyncio
    async def test_empty_history(self) -> None:
        consumer = _make_consumer()
        conv_service = MagicMock()
        conv_service.get_messages.return_value = []
        with patch("apps.litigation_ai.services.LitigationConversationService", return_value=conv_service):
            await consumer.send_history_messages()
        payload = json.loads(consumer.send.await_args.kwargs["text_data"])
        assert payload == {"type": "history", "messages": []}
