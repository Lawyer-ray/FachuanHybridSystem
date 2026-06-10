"""Extended tests for workbench services - session_service, chat_service token estimation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.workbench.services.chat_service import _estimate_tokens, _convert_to_model_messages


class TestEstimateTokens:
    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_none(self):
        assert _estimate_tokens(None) == 0  # type: ignore[arg-type]

    def test_chinese_text(self):
        tokens = _estimate_tokens("买卖合同纠纷案件")
        assert tokens > 0

    def test_english_text(self):
        tokens = _estimate_tokens("hello world")
        assert tokens > 0

    def test_mixed_text(self):
        tokens = _estimate_tokens("Contract买卖合同")
        assert tokens > 0

    def test_minimum_one(self):
        # Even very short text should return at least 1
        tokens = _estimate_tokens("a")
        assert tokens >= 1


class TestConvertToModelMessages:
    def test_empty(self):
        result = _convert_to_model_messages([])
        assert result == []

    def test_user_message(self):
        msg = MagicMock()
        msg.role = "user"
        msg.content = "hello"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_assistant_message(self):
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "response"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_tool_message(self):
        msg = MagicMock()
        msg.role = "tool"
        msg.content = "tool call"
        msg.tool_output = {"result": "success"}
        msg.tool_call_id = "tc_123"
        msg.tool_name = "search"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_tool_message_string_output(self):
        msg = MagicMock()
        msg.role = "tool"
        msg.content = "tool call"
        msg.tool_output = "string result"
        msg.tool_call_id = "tc_123"
        msg.tool_name = "search"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_mixed_messages(self):
        user_msg = MagicMock()
        user_msg.role = "user"
        user_msg.content = "hello"
        asst_msg = MagicMock()
        asst_msg.role = "assistant"
        asst_msg.content = "response"
        result = _convert_to_model_messages([user_msg, asst_msg])
        assert len(result) == 2


class TestCalcMessageBytes:
    def test_import(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        assert callable(_calc_message_bytes)

    def test_empty(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes()
        assert result >= 0

    def test_with_content(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(content="hello world")
        assert result > 0

    def test_with_all_fields(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(
            content="test",
            tool_input={"key": "value"},
            tool_output={"result": "ok"},
            metadata={"meta": "data"},
        )
        assert result > 0


class TestWorkbenchSessionService:
    def test_import(self):
        from apps.workbench.services.session_service import WorkbenchSessionService

        assert WorkbenchSessionService is not None

    def test_invalidate_session_cache_no_user(self):
        from apps.workbench.services.session_service import WorkbenchSessionService

        # Should not raise
        WorkbenchSessionService._invalidate_session_cache(None)

    def test_invalidate_session_cache_anonymous(self):
        from apps.workbench.services.session_service import WorkbenchSessionService

        user = MagicMock()
        user.is_authenticated = False
        WorkbenchSessionService._invalidate_session_cache(user)


class TestWorkbenchChatService:
    def test_import(self):
        from apps.workbench.services.chat_service import WorkbenchChatService

        assert WorkbenchChatService is not None

    def test_agent_map(self):
        from apps.workbench.services.chat_service import AGENT_MAP

        assert "triage" in AGENT_MAP
        assert "case" in AGENT_MAP
        assert "contract" in AGENT_MAP
        assert "research" in AGENT_MAP
