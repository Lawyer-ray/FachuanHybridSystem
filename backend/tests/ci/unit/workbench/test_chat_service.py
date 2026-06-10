"""Workbench chat service tests with mocked LLM."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workbench.services.chat_service import (
    AGENT_MAP,
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_TOKENS,
    SUMMARY_THRESHOLD,
    USAGE_LIMITS,
    WorkbenchChatService,
    _convert_to_model_messages,
    _estimate_tokens,
)


class TestEstimateTokens:
    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_chinese_text(self):
        result = _estimate_tokens("买卖合同纠纷")
        assert result > 0

    def test_english_text(self):
        result = _estimate_tokens("hello world")
        assert result > 0

    def test_mixed_text(self):
        result = _estimate_tokens("买卖contract纠纷case")
        assert result > 0


class TestConvertToModelMessages:
    def test_empty_list(self):
        result = _convert_to_model_messages([])
        assert result == []

    def test_user_message(self):
        msg = MagicMock()
        msg.role = "user"
        msg.content = "Hello"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_assistant_message(self):
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "Response"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_tool_message(self):
        msg = MagicMock()
        msg.role = "tool"
        msg.content = "Tool result"
        msg.tool_output = {"result": "data"}
        msg.tool_call_id = "tc_1"
        msg.tool_name = "search"
        result = _convert_to_model_messages([msg])
        assert len(result) == 1


class TestWorkbenchChatService:
    def test_init(self):
        svc = WorkbenchChatService()
        assert svc.approval_manager is not None

    def test_resolve_approval(self):
        svc = WorkbenchChatService()
        with patch.object(svc.approval_manager, "resolve", return_value=True):
            result = svc.resolve_approval("approval-1", True, user_id=1)
            assert result is True


class TestConstants:
    def test_agent_map_keys(self):
        assert "triage" in AGENT_MAP
        assert "case" in AGENT_MAP
        assert "contract" in AGENT_MAP
        assert "research" in AGENT_MAP

    def test_usage_limits(self):
        assert USAGE_LIMITS.request_limit == 50
        assert USAGE_LIMITS.total_tokens_limit == 100_000

    def test_history_constants(self):
        assert MAX_HISTORY_TOKENS == 10000
        assert MAX_HISTORY_MESSAGES == 100
        assert SUMMARY_THRESHOLD == 30
