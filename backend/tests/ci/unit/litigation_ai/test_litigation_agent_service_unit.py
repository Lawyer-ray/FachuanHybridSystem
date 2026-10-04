"""litigation_agent_service.py 单元测试（LLM/Agent/DB 全 mock）.

覆盖依赖注入、Agent 实例缓存与清理、响应内容提取、
handle_evidence_selection 的元数据 RMW 与会话缺失分支。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.litigation_ai.services.generation.litigation_agent_service import LitigationAgentService


def _msg(role: str, content: str) -> Any:
    """构造带 .type 属性的消息对象（LangChain 风格）。"""
    return SimpleNamespace(type=role, content=content)


class TestLazyProperties:
    def test_agent_factory_lazy(self) -> None:
        svc = LitigationAgentService()
        assert svc._agent_factory is None
        with patch("apps.litigation_ai.agent.factory.LitigationAgentFactory") as mock_cls:
            f1 = svc.agent_factory
            f2 = svc.agent_factory
        assert f1 is f2
        mock_cls.assert_called_once()

    def test_conversation_service_lazy(self) -> None:
        svc = LitigationAgentService()
        with patch("apps.litigation_ai.services.session.conversation_service.ConversationService") as mock_cls:
            s1 = svc.conversation_service
            s2 = svc.conversation_service
        assert s1 is s2
        mock_cls.assert_called_once()

    def test_injected_dependencies_not_overwritten(self) -> None:
        factory, conv = object(), object()
        svc = LitigationAgentService(agent_factory=factory, conversation_service=conv)
        assert svc.agent_factory is factory
        assert svc.conversation_service is conv


class TestGetOrCreateAgent:
    def test_creates_once_per_session(self) -> None:
        factory = MagicMock()
        factory.create_agent.return_value = object()
        svc = LitigationAgentService(agent_factory=factory)

        a1 = svc.get_or_create_agent("sess-1", case_id=3)
        a2 = svc.get_or_create_agent("sess-1", case_id=3)

        assert a1 is a2
        factory.create_agent.assert_called_once_with(session_id="sess-1", case_id=3)

    def test_different_sessions_get_different_agents(self) -> None:
        factory = MagicMock()
        factory.create_agent.side_effect = lambda **_: object()
        svc = LitigationAgentService(agent_factory=factory)

        a1 = svc.get_or_create_agent("sess-1", case_id=1)
        a2 = svc.get_or_create_agent("sess-2", case_id=1)

        assert a1 is not a2
        assert factory.create_agent.call_count == 2


class TestCleanupAgent:
    def test_cleanup_existing(self) -> None:
        factory = MagicMock()
        factory.create_agent.return_value = object()
        svc = LitigationAgentService(agent_factory=factory)
        svc.get_or_create_agent("sess-1", case_id=1)

        svc.cleanup_agent("sess-1")

        assert "sess-1" not in svc._agents
        # 清理后再次获取会重建
        svc.get_or_create_agent("sess-1", case_id=1)
        assert factory.create_agent.call_count == 2

    def test_cleanup_missing_is_noop(self) -> None:
        svc = LitigationAgentService()
        svc.cleanup_agent("ghost")  # 不抛 KeyError
        assert svc._agents == {}


class TestExtractResponseContent:
    def _svc(self) -> LitigationAgentService:
        return LitigationAgentService()

    def test_empty_messages(self) -> None:
        assert self._svc()._extract_response_content({"messages": []}) == ""

    def test_no_messages_key(self) -> None:
        assert self._svc()._extract_response_content({}) == ""

    def test_object_messages_returns_last_assistant(self) -> None:
        result = {"messages": [_msg("user", "问"), _msg("assistant", "答1"), _msg("assistant", "答2")]}
        assert self._svc()._extract_response_content(result) == "答2"

    def test_object_messages_ai_role(self) -> None:
        result = {"messages": [_msg("ai", "AI 回复")]}
        assert self._svc()._extract_response_content(result) == "AI 回复"

    def test_dict_messages(self) -> None:
        result = {"messages": [{"role": "user", "content": "问"}, {"role": "assistant", "content": "dict 答"}]}
        assert self._svc()._extract_response_content(result) == "dict 答"

    def test_dict_messages_ai_role(self) -> None:
        result = {"messages": [{"role": "ai", "content": "ai dict"}]}
        assert self._svc()._extract_response_content(result) == "ai dict"

    def test_no_assistant_message_returns_empty(self) -> None:
        result = {"messages": [_msg("user", "问"), _msg("tool", "中间结果")]}
        assert self._svc()._extract_response_content(result) == ""

    def test_non_string_content_coerced(self) -> None:
        result = {"messages": [SimpleNamespace(type="assistant", content=[1, 2])]}
        assert self._svc()._extract_response_content(result) == "[1, 2]"


class TestHandleEvidenceSelection:
    """handle_evidence_selection：session 元数据锁内更新 + 委托 handle_message。"""

    def _make_svc(self, agent_result: dict[str, Any]) -> tuple[LitigationAgentService, MagicMock]:
        agent = AsyncMock()
        agent.ainvoke.return_value = agent_result
        factory = MagicMock()
        factory.create_agent.return_value = agent
        conv = MagicMock()
        svc = LitigationAgentService(agent_factory=factory, conversation_service=conv)
        return svc, agent

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_updates_metadata_and_calls_agent(self) -> None:
        svc, agent = self._make_svc({"messages": [_msg("assistant", "已开始生成")], "tool_calls": [{"t": 1}]})

        session = SimpleNamespace(metadata={"existing": 1}, save=MagicMock())
        mock_model = MagicMock()
        mock_model.objects.select_for_update.return_value.filter.return_value.first.return_value = session

        with patch("apps.litigation_ai.models.LitigationSession", mock_model):
            result = await svc.handle_evidence_selection(
                session_id="sess-e",
                case_id=8,
                evidence_item_ids=[1, 2],
                our_evidence_item_ids=[1],
                opponent_evidence_item_ids=[2],
            )

        # 元数据合并而非覆盖
        assert session.metadata["existing"] == 1
        assert session.metadata["evidence_item_ids"] == [1, 2]
        assert session.metadata["our_evidence_item_ids"] == [1]
        assert session.metadata["opponent_evidence_item_ids"] == [2]
        session.save.assert_called_once_with(update_fields=["metadata"])

        assert result["type"] == "assistant_complete"
        assert result["content"] == "已开始生成"
        assert result["metadata"]["tool_calls"] == [{"t": 1}]
        # ainvoke 收到的消息是证据选择摘要
        invoke_kwargs = agent.ainvoke.await_args.args[0]
        assert "我方证据 1 项" in invoke_kwargs["messages"][0]["content"]
        assert "对方证据 1 项" in invoke_kwargs["messages"][0]["content"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_missing_session_raises_not_found(self) -> None:
        svc, _agent = self._make_svc({"messages": []})
        mock_model = MagicMock()
        mock_model.objects.select_for_update.return_value.filter.return_value.first.return_value = None

        with (
            patch("apps.litigation_ai.models.LitigationSession", mock_model),
            pytest.raises(NotFoundError, match="会话不存在"),
        ):
            await svc.handle_evidence_selection(
                session_id="ghost",
                case_id=1,
                evidence_item_ids=[],
                our_evidence_item_ids=[],
                opponent_evidence_item_ids=[],
            )


class TestHandleMessagePersistence:
    """handle_message 的消息持久化与流式分支（通过 evidence 委托之外的直接调用）。"""

    @pytest.mark.asyncio
    async def test_saves_user_and_assistant_messages(self) -> None:
        agent = AsyncMock()
        agent.astream.return_value = {"messages": [_msg("assistant", "流式回复")]}
        factory = MagicMock()
        factory.create_agent.return_value = agent
        conv = MagicMock()
        conv.add_message.return_value = object()
        svc = LitigationAgentService(agent_factory=factory, conversation_service=conv)

        chunks: list[str] = []

        async def stream_cb(chunk: str) -> None:
            chunks.append(chunk)

        result = await svc.handle_message(
            session_id="sess-m",
            case_id=2,
            user_message="写起诉状",
            metadata={"src": "test"},
            stream_callback=stream_cb,
        )

        # 有 stream_callback → 走 astream 而非 ainvoke
        agent.astream.assert_awaited_once()
        agent.ainvoke.assert_not_awaited()
        assert agent.astream.await_args.kwargs["stream_callback"] is stream_cb

        # 两条消息落库：user 在前，assistant 在后
        roles = [c.kwargs["role"] for c in conv.add_message.call_args_list]
        assert roles == ["user", "assistant"]
        assert conv.add_message.call_args_list[0].kwargs["content"] == "写起诉状"
        assert conv.add_message.call_args_list[1].kwargs["content"] == "流式回复"

        assert result == {
            "type": "assistant_complete",
            "content": "流式回复",
            "metadata": {"tool_calls": []},
        }

    @pytest.mark.asyncio
    async def test_without_stream_callback_uses_ainvoke(self) -> None:
        agent = AsyncMock()
        agent.ainvoke.return_value = {"messages": [_msg("assistant", "同步回复")]}
        factory = MagicMock()
        factory.create_agent.return_value = agent
        svc = LitigationAgentService(agent_factory=factory, conversation_service=MagicMock())

        result = await svc.handle_message(session_id="s", case_id=1, user_message="hi")

        agent.ainvoke.assert_awaited_once()
        agent.astream.assert_not_awaited()
        assert result["content"] == "同步回复"
