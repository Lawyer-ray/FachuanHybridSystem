"""Tests for litigation_ai.agent.factory - LitigationAgent and LitigationAgentFactory."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.agent.factory import LitigationAgent, LitigationAgentFactory


# ---------------------------------------------------------------------------
# LitigationAgent tests
# ---------------------------------------------------------------------------


class TestLitigationAgent:
    def _make_agent(self, **overrides: Any) -> LitigationAgent:
        return LitigationAgent(
            llm=overrides.get("llm", MagicMock()),
            tools=overrides.get("tools", []),
            system_prompt=overrides.get("system_prompt", "You are helpful"),
            session_id=overrides.get("session_id", "s1"),
            case_id=overrides.get("case_id", 1),
            max_iterations=overrides.get("max_iterations", 3),
        )

    def test_prepare_messages_basic(self):
        agent = self._make_agent()
        result = agent._prepare_messages([{"role": "user", "content": "hello"}])
        assert len(result) == 2  # system + user
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "hello"

    def test_prepare_messages_skips_system(self):
        agent = self._make_agent()
        result = agent._prepare_messages([{"role": "system", "content": "ignore"}])
        assert len(result) == 1  # only the initial system

    def test_prepare_messages_ai_to_assistant(self):
        agent = self._make_agent()
        result = agent._prepare_messages([{"role": "ai", "content": "hi"}])
        assert result[1]["role"] == "assistant"

    def test_prepare_messages_unknown_role_becomes_user(self):
        agent = self._make_agent()
        result = agent._prepare_messages([{"role": "custom", "content": "test"}])
        assert result[1]["role"] == "user"

    def test_prepare_messages_with_object_messages(self):
        agent = self._make_agent()
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "response"
        result = agent._prepare_messages([msg])
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "response"

    def test_prepare_messages_with_type_attr(self):
        agent = self._make_agent()
        msg = MagicMock(spec=[])  # No role attr
        msg.type = "user"
        msg.content = "test"
        del msg.role
        result = agent._prepare_messages([msg])
        assert result[1]["role"] == "user"

    def test_execute_tool_unknown(self):
        agent = self._make_agent(tools=[])
        result = agent._execute_tool("unknown_tool", {})
        assert "error" in result

    def test_execute_tool_known(self):
        tool = MagicMock()
        tool.name = "my_tool"
        tool.invoke.return_value = "result"
        agent = self._make_agent(tools=[tool])
        result = agent._execute_tool("my_tool", {"arg": 1})
        assert result == "result"

    def test_execute_tool_exception(self):
        tool = MagicMock()
        tool.name = "bad_tool"
        tool.invoke.side_effect = RuntimeError("boom")
        agent = self._make_agent(tools=[tool])
        result = agent._execute_tool("bad_tool", {})
        assert "error" in result

    def test_invoke_no_tool_calls(self):
        llm = MagicMock()
        response = MagicMock()
        response.content = "simple answer"
        response.tool_calls = []
        llm.invoke.return_value = response
        agent = self._make_agent(llm=llm)
        result = agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
        assert "messages" in result
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 0

    def test_invoke_with_tool_calls(self):
        llm = MagicMock()
        tool = MagicMock()
        tool.name = "search"
        tool.invoke.return_value = "found"

        response_with_tool = MagicMock()
        response_with_tool.content = "let me search"
        response_with_tool.tool_calls = [{"name": "search", "args": {"q": "test"}, "id": "tc1"}]

        response_final = MagicMock()
        response_final.content = "here are results"
        response_final.tool_calls = []

        llm.invoke.side_effect = [response_with_tool, response_final]
        agent = self._make_agent(llm=llm, tools=[tool])
        result = agent.invoke({"messages": []})
        assert len(result["tool_calls"]) == 1

    def test_invoke_max_iterations(self):
        llm = MagicMock()
        tool = MagicMock()
        tool.name = "loop"
        tool.invoke.return_value = "ok"

        response = MagicMock()
        response.content = "looping"
        response.tool_calls = [{"name": "loop", "args": {}, "id": "tc1"}]
        llm.invoke.return_value = response

        agent = self._make_agent(llm=llm, tools=[tool], max_iterations=2)
        result = agent.invoke({"messages": []})
        assert llm.invoke.call_count == 2

    def test_tools_map(self):
        tool = MagicMock()
        tool.name = "t1"
        agent = self._make_agent(tools=[tool])
        assert "t1" in agent.tools_map


# ---------------------------------------------------------------------------
# LitigationAgentFactory tests
# ---------------------------------------------------------------------------


class TestLitigationAgentFactory:
    @patch("apps.litigation_ai.agent.factory.LLMConfig")
    @patch("apps.litigation_ai.agent.factory.LitigationLLMProvider")
    def test_create_agent(self, MockProvider, MockConfig):
        MockConfig.get_openai_compatible_model.return_value = "test-model"
        provider = MagicMock()
        provider.create_llm_with_tools.return_value = MagicMock()
        MockProvider.return_value = provider

        factory = LitigationAgentFactory(model="test-model", temperature=0.5, max_iterations=5)
        with patch("apps.litigation_ai.agent.factory.settings", MagicMock()):
            with patch("apps.litigation_ai.agent.tools.get_litigation_tools", return_value=[]):
                with patch("apps.litigation_ai.agent.prompts.get_system_prompt", return_value="prompt"):
                    agent = factory.create_agent(session_id="s1", case_id=1)
                    assert isinstance(agent, LitigationAgent)
                    assert agent.session_id == "s1"
                    assert agent.case_id == 1

    @patch("apps.litigation_ai.agent.factory.LLMConfig")
    @patch("apps.litigation_ai.agent.factory.LitigationLLMProvider")
    def test_get_config(self, MockProvider, MockConfig):
        MockConfig.get_openai_compatible_model.return_value = "default"
        provider = MagicMock()
        MockProvider.return_value = provider
        factory = LitigationAgentFactory(model="my-model", temperature=0.3)
        config = factory.get_config()
        assert config["model"] == "my-model"
        assert config["temperature"] == 0.3

    @patch("apps.litigation_ai.agent.factory.LLMConfig")
    @patch("apps.litigation_ai.agent.factory.LitigationLLMProvider")
    def test_get_model_name_fallback(self, MockProvider, MockConfig):
        MockConfig.get_openai_compatible_model.return_value = "fallback-model"
        provider = MagicMock()
        MockProvider.return_value = provider
        factory = LitigationAgentFactory()
        assert factory.get_model_name() == "fallback-model"
