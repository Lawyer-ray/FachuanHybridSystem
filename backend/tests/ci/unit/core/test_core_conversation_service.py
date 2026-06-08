"""core/services/conversation_service.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.conversation_service import (
    AIMessage,
    ConversationService,
    HumanMessage,
    SystemMessage,
    _SimpleChatMemory,
    _SimpleConversationBufferWindowMemory,
)


class TestMessageDataclasses:
    """消息数据类测试。"""

    def test_human_message(self) -> None:
        msg = HumanMessage(content="hello")
        assert msg.content == "hello"

    def test_ai_message(self) -> None:
        msg = AIMessage(content="hi there")
        assert msg.content == "hi there"

    def test_system_message(self) -> None:
        msg = SystemMessage(content="system prompt")
        assert msg.content == "system prompt"


class TestSimpleChatMemory:
    """_SimpleChatMemory 测试。"""

    def test_init_empty(self) -> None:
        mem = _SimpleChatMemory(max_messages=5)
        assert mem.messages == []
        assert mem._max_messages == 5

    def test_add_message(self) -> None:
        mem = _SimpleChatMemory(max_messages=5)
        mem.add_message(HumanMessage("hi"))
        assert len(mem.messages) == 1

    def test_trim_when_exceeded(self) -> None:
        mem = _SimpleChatMemory(max_messages=3)
        for i in range(5):
            mem.add_message(HumanMessage(f"msg{i}"))
        assert len(mem.messages) == 3
        assert mem.messages[0].content == "msg2"

    def test_add_user_message(self) -> None:
        mem = _SimpleChatMemory(max_messages=5)
        mem.add_user_message("user says")
        assert isinstance(mem.messages[0], HumanMessage)
        assert mem.messages[0].content == "user says"

    def test_add_ai_message(self) -> None:
        mem = _SimpleChatMemory(max_messages=5)
        mem.add_ai_message("ai says")
        assert isinstance(mem.messages[0], AIMessage)
        assert mem.messages[0].content == "ai says"

    def test_clear(self) -> None:
        mem = _SimpleChatMemory(max_messages=5)
        mem.add_message(HumanMessage("hi"))
        mem.clear()
        assert mem.messages == []

    def test_trim_to_one(self) -> None:
        mem = _SimpleChatMemory(max_messages=1)
        mem.add_message(HumanMessage("first"))
        mem.add_message(AIMessage("second"))
        assert len(mem.messages) == 1
        assert mem.messages[0].content == "second"


class TestSimpleConversationBufferWindowMemory:
    """_SimpleConversationBufferWindowMemory 测试。"""

    def test_init(self) -> None:
        mem = _SimpleConversationBufferWindowMemory(k=5, return_messages=True, memory_key="history")
        assert mem.k == 5
        assert mem.return_messages is True
        assert mem.memory_key == "history"

    def test_chat_memory_max_messages(self) -> None:
        mem = _SimpleConversationBufferWindowMemory(k=3, return_messages=True, memory_key="key")
        assert mem.chat_memory._max_messages == 6  # k * 2

    def test_clear(self) -> None:
        mem = _SimpleConversationBufferWindowMemory(k=3, return_messages=True, memory_key="key")
        mem.chat_memory.add_message(HumanMessage("hi"))
        mem.clear()
        assert mem.chat_memory.messages == []

    def test_k_minimum_is_1(self) -> None:
        mem = _SimpleConversationBufferWindowMemory(k=0, return_messages=True, memory_key="key")
        assert mem.chat_memory._max_messages == 1  # max(1, 0*2)


class TestConversationServiceInit:
    """ConversationService 初始化测试。"""

    def test_auto_session_id(self) -> None:
        svc = ConversationService(repository=MagicMock())
        assert svc.session_id.startswith("session_")

    def test_custom_session_id(self) -> None:
        svc = ConversationService(session_id="my_session", repository=MagicMock())
        assert svc.session_id == "my_session"

    def test_custom_user_id(self) -> None:
        svc = ConversationService(user_id="user_123", repository=MagicMock())
        assert svc.user_id == "user_123"

    def test_default_user_id_empty(self) -> None:
        svc = ConversationService(repository=MagicMock())
        assert svc.user_id == ""


class TestConversationServiceGenerateSessionId:
    def test_format(self) -> None:
        svc = ConversationService(repository=MagicMock())
        sid = svc._generate_session_id()
        assert sid.startswith("session_")
        assert len(sid) == 20  # "session_" (8) + 12 hex chars


class TestConversationServiceGetMessagesForLlm:
    """get_messages_for_llm 测试。"""

    def test_empty(self) -> None:
        svc = ConversationService(repository=MagicMock())
        # Force memory initialization
        svc._memory = _SimpleConversationBufferWindowMemory(k=10, return_messages=True, memory_key="key")
        messages = svc.get_messages_for_llm()
        assert messages == []

    def test_with_messages(self) -> None:
        svc = ConversationService(repository=MagicMock())
        svc._memory = _SimpleConversationBufferWindowMemory(k=10, return_messages=True, memory_key="key")
        svc._memory.chat_memory.add_user_message("hi")
        svc._memory.chat_memory.add_ai_message("hello")
        svc._memory.chat_memory.add_message(SystemMessage(content="system"))
        messages = svc.get_messages_for_llm()
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "system"


class TestConversationServiceGetConversationSummary:
    """get_conversation_summary 测试。"""

    def test_empty(self) -> None:
        svc = ConversationService(repository=MagicMock())
        svc._memory = _SimpleConversationBufferWindowMemory(k=10, return_messages=True, memory_key="key")
        assert svc.get_conversation_summary() == "暂无对话记录"

    def test_with_messages(self) -> None:
        svc = ConversationService(repository=MagicMock())
        svc._memory = _SimpleConversationBufferWindowMemory(k=10, return_messages=True, memory_key="key")
        svc._memory.chat_memory.add_user_message("你好")
        svc._memory.chat_memory.add_ai_message("你好！")
        summary = svc.get_conversation_summary()
        assert "对话轮数: 1" in summary
        assert "你好" in summary


class TestConversationServiceMemoryLazyLoad:
    """memory 属性延迟加载测试。"""

    def test_memory_is_none_initially(self) -> None:
        svc = ConversationService(repository=MagicMock())
        assert svc._memory is None

    @patch("apps.core.services.conversation_service.ConversationHistoryRepository")
    def test_memory_lazy_loaded(self, MockRepo: MagicMock) -> None:
        mock_repo = MagicMock()
        mock_repo.get_by_session_id.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        svc = ConversationService(repository=mock_repo)
        mem = svc.memory
        assert mem is not None
        assert isinstance(mem, _SimpleConversationBufferWindowMemory)
        # Second access returns same instance
        assert svc.memory is mem
