"""Unit tests for workbench.agents.definitions module."""

from __future__ import annotations

import asyncio
from contextvars import copy_context
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.workbench.agents.deps import WorkbenchDeps


class TestBuildInstructions:
    """Tests for the _build_instructions helper."""

    def test_basic_prompt_no_summary(self):
        from apps.workbench.agents.definitions import _build_instructions

        deps = WorkbenchDeps(
            session_id=1,
            user_id=10,
            llm_model="gpt-4",
            conversation_summary="",
        )
        result = _build_instructions("BASE", deps)
        assert result.startswith("BASE")
        assert "会话 ID：1" in result
        assert "使用模型：gpt-4" in result
        assert "之前对话摘要" not in result

    def test_prompt_with_summary(self):
        from apps.workbench.agents.definitions import _build_instructions

        deps = WorkbenchDeps(
            session_id=5,
            user_id=20,
            llm_model="gpt-3.5",
            conversation_summary="之前讨论了合同纠纷",
        )
        result = _build_instructions("PROMPT", deps)
        assert "之前讨论了合同纠纷" in result
        assert "之前对话摘要" in result

    def test_date_format(self):
        from apps.workbench.agents.definitions import _build_instructions

        deps = WorkbenchDeps(session_id=1, llm_model="")
        result = _build_instructions("X", deps)
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        expected_weekday = weekdays[now.weekday()]
        assert f"{now.year}年{now.month}月{now.day}日 {expected_weekday}" in result

    def test_empty_model_shows_default(self):
        from apps.workbench.agents.definitions import _build_instructions

        deps = WorkbenchDeps(session_id=1, llm_model="")
        result = _build_instructions("X", deps)
        assert "未指定" in result


class TestContextVars:
    """Tests for ContextVar-based event queue management."""

    def test_set_event_queue(self):
        from apps.workbench.agents.definitions import (
            _current_agent_name,
            _current_event_queue,
            _current_user_id,
            set_event_queue,
        )

        queue = asyncio.Queue()
        set_event_queue(queue, agent_name="case", user_id=42)
        assert _current_event_queue.get() is queue
        assert _current_agent_name.get() == "case"
        assert _current_user_id.get() == 42

    def test_set_event_queue_none(self):
        from apps.workbench.agents.definitions import (
            _current_event_queue,
            set_event_queue,
        )

        set_event_queue(None)
        assert _current_event_queue.get() is None


class TestToolFilterFunctions:
    """Tests for tool filter predicates."""

    def test_case_filter(self):
        from apps.workbench.agents.definitions import _case_filter

        tool_def = MagicMock()
        tool_def.name = "get_case"
        assert _case_filter(None, tool_def) is True

    def test_case_filter_non_match(self):
        from apps.workbench.agents.definitions import _case_filter

        tool_def = MagicMock()
        tool_def.name = "search_contract"
        assert _case_filter(None, tool_def) is False

    def test_contract_filter(self):
        from apps.workbench.agents.definitions import _contract_filter

        tool_def = MagicMock()
        tool_def.name = "get_agreement"
        assert _contract_filter(None, tool_def) is True

    def test_contract_filter_non_match(self):
        from apps.workbench.agents.definitions import _contract_filter

        tool_def = MagicMock()
        tool_def.name = "get_case"
        assert _contract_filter(None, tool_def) is False

    def test_research_filter(self):
        from apps.workbench.agents.definitions import _research_filter

        tool_def = MagicMock()
        tool_def.name = "web_search"
        assert _research_filter(None, tool_def) is True

    def test_research_filter_enterprise(self):
        from apps.workbench.agents.definitions import _research_filter

        tool_def = MagicMock()
        tool_def.name = "enterprise_lookup"
        assert _research_filter(None, tool_def) is True

    def test_research_filter_non_match(self):
        from apps.workbench.agents.definitions import _research_filter

        tool_def = MagicMock()
        tool_def.name = "create_case"
        assert _research_filter(None, tool_def) is False


class TestProcessToolCall:
    """Tests for _process_tool_call callback."""

    @pytest.mark.asyncio
    async def test_no_queue_direct_call(self):
        from apps.workbench.agents.definitions import _current_event_queue, _process_tool_call

        # Ensure queue is None
        _current_event_queue.set(None)
        call_tool = AsyncMock(return_value="direct_result")
        ctx = MagicMock()

        # When queue is None, process_tool_call_with_approval is NOT called
        # call_tool is called directly
        result = await _process_tool_call(ctx, call_tool, "some_tool", {"arg": 1})
        assert result == "direct_result"
        call_tool.assert_called_once_with("some_tool", {"arg": 1})

    @pytest.mark.asyncio
    async def test_with_queue_and_handoff(self):
        from apps.workbench.agents.definitions import (
            _current_event_queue,
            _current_agent_name,
            _current_user_id,
            _process_tool_call,
            set_event_queue,
        )

        queue = asyncio.Queue()
        set_event_queue(queue, agent_name="triage", user_id=1)

        ctx = MagicMock()
        call_tool = AsyncMock(return_value="ok")

        with patch(
            "apps.workbench.agents.definitions.process_tool_call_with_approval",
            new_callable=AsyncMock,
        ) as mock_approval:
            mock_approval.return_value = "ok"
            result = await _process_tool_call(
                ctx, call_tool, "_handoff_to_case", {"query": "test"}
            )
            mock_approval.assert_called_once()

        assert not queue.empty()
        event = queue.get_nowait()
        assert event["type"] == "handoff"
        # name.replace("_handoff_to_", "") on "_handoff_to_case" gives "case"
        assert event["to_agent"] == "case"
        assert event["from_agent"] == "triage"

    @pytest.mark.asyncio
    async def test_non_handoff_tool_no_handoff_event(self):
        from apps.workbench.agents.definitions import (
            _current_event_queue,
            _process_tool_call,
            set_event_queue,
        )

        queue = asyncio.Queue()
        set_event_queue(queue, agent_name="triage", user_id=1)

        ctx = MagicMock()
        call_tool = AsyncMock(return_value="result")

        with patch(
            "apps.workbench.agents.definitions.process_tool_call_with_approval",
            new_callable=AsyncMock,
        ) as mock_approval:
            mock_approval.return_value = "result"
            await _process_tool_call(ctx, call_tool, "some_tool", {"arg": 1})

        assert queue.empty()


class TestModuleConstants:
    def test_base_system_prompt_exists(self):
        from apps.workbench.agents.definitions import BASE_SYSTEM_PROMPT
        assert len(BASE_SYSTEM_PROMPT) > 0
        assert "法穿AI" in BASE_SYSTEM_PROMPT

    def test_triage_prompt_exists(self):
        from apps.workbench.agents.definitions import TRIAGE_PROMPT
        assert "分诊" in TRIAGE_PROMPT

    def test_backend_dir(self):
        from apps.workbench.agents.definitions import BACKEND_DIR
        assert isinstance(BACKEND_DIR, str)
        assert len(BACKEND_DIR) > 0


class TestAgentInstances:
    def test_agents_are_created(self):
        from apps.workbench.agents.definitions import (
            case_agent,
            contract_agent,
            research_agent,
            triage_agent,
        )
        assert case_agent is not None
        assert contract_agent is not None
        assert research_agent is not None
        assert triage_agent is not None

    def test_agent_names(self):
        from apps.workbench.agents.definitions import (
            case_agent,
            contract_agent,
            research_agent,
            triage_agent,
        )
        assert case_agent.name == "案件管理助手"
        assert contract_agent.name == "合同管理助手"
        assert research_agent.name == "法律检索助手"
        assert triage_agent.name == "分诊助手"


class TestInstructionFunctions:
    def test_case_instructions(self):
        from apps.workbench.agents.definitions import _case_instructions

        mock_ctx = MagicMock()
        mock_ctx.deps = WorkbenchDeps(session_id=1, llm_model="gpt-4")
        result = _case_instructions(mock_ctx)
        assert "案件管理" in result

    def test_contract_instructions(self):
        from apps.workbench.agents.definitions import _contract_instructions

        mock_ctx = MagicMock()
        mock_ctx.deps = WorkbenchDeps(session_id=1, llm_model="gpt-4")
        result = _contract_instructions(mock_ctx)
        assert "合同管理" in result

    def test_research_instructions(self):
        from apps.workbench.agents.definitions import _research_instructions

        mock_ctx = MagicMock()
        mock_ctx.deps = WorkbenchDeps(session_id=1, llm_model="gpt-4")
        result = _research_instructions(mock_ctx)
        assert "法律检索" in result

    def test_triage_instructions(self):
        from apps.workbench.agents.definitions import _triage_instructions

        mock_ctx = MagicMock()
        mock_ctx.deps = WorkbenchDeps(session_id=1, llm_model="gpt-4")
        result = _triage_instructions(mock_ctx)
        assert "分诊" in result


class TestBuildModel:
    @patch("apps.workbench.agents.definitions.LLMConfig")
    def test_ollama_backend(self, mock_config):
        from apps.workbench.agents.definitions import build_model

        mock_config.resolve_backend_for_model.return_value = "ollama"
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434/v1"
        model = build_model("llama3")
        assert model is not None

    @patch("apps.workbench.agents.definitions.LLMConfig")
    def test_openai_compatible_backend(self, mock_config):
        from apps.workbench.agents.definitions import build_model

        mock_config.resolve_backend_for_model.return_value = "openai_compatible"
        mock_config.get_openai_compatible_api_key.return_value = "sk-test"
        mock_config.get_openai_compatible_base_url.return_value = "https://api.openai.com/v1"
        model = build_model("gpt-4")
        assert model is not None
