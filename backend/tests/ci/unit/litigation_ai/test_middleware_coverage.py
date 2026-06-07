"""Coverage tests for litigation_ai.agent.middleware."""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest


class TestLitigationMemoryMiddleware:
    def _make(self):
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        return LitigationMemoryMiddleware(session_id="test_session", max_messages=10)

    def test_init(self):
        mw = self._make()
        assert mw.session_id == "test_session"
        assert mw.max_messages == 10

    def test_before_agent_with_history(self):
        mw = self._make()
        mock_cs = MagicMock()
        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "hello"
        mock_cs.get_messages.return_value = [mock_msg]
        mw._conversation_service = mock_cs
        state = {"messages": [{"role": "assistant", "content": "hi"}]}
        result = mw.before_agent(state)
        assert len(result["messages"]) == 2

    @patch("apps.litigation_ai.agent.middleware.LitigationMemoryMiddleware.conversation_service", new_callable=lambda: property(lambda self: MagicMock()))
    def test_before_agent_empty_history(self, mock_cs):
        mw = self._make()
        mw.conversation_service.get_messages.return_value = []
        state = {"messages": []}
        result = mw.before_agent(state)
        assert result["messages"] == []

    @patch("apps.litigation_ai.agent.middleware.LitigationMemoryMiddleware.conversation_service", new_callable=lambda: property(lambda self: MagicMock()))
    def test_before_agent_error(self, mock_cs):
        mw = self._make()
        mw.conversation_service.get_messages.side_effect = Exception("db error")
        state = {"messages": []}
        result = mw.before_agent(state)
        assert result is state

    @patch("apps.litigation_ai.agent.middleware.LitigationMemoryMiddleware.conversation_service", new_callable=lambda: property(lambda self: MagicMock()))
    def test_after_agent_save(self, mock_cs):
        mw = self._make()
        state = {"messages": [{"role": "assistant", "content": "response"}]}
        result = mw.after_agent(state)
        assert result is state

    @patch("apps.litigation_ai.agent.middleware.LitigationMemoryMiddleware.conversation_service", new_callable=lambda: property(lambda self: MagicMock()))
    def test_after_agent_empty(self, mock_cs):
        mw = self._make()
        state = {"messages": []}
        result = mw.after_agent(state)
        assert result is state

    def test_save_user_message(self):
        mw = self._make()
        mock_cs = MagicMock()
        mw._conversation_service = mock_cs
        mw.save_user_message("hello", {"key": "value"})
        mock_cs.add_message.assert_called_once()


class TestSummarizationConfig:
    def test_defaults(self):
        from apps.litigation_ai.agent.middleware import SummarizationConfig

        cfg = SummarizationConfig()
        assert cfg.token_threshold == 2000
        assert cfg.preserve_messages == 10

    def test_custom(self):
        from apps.litigation_ai.agent.middleware import SummarizationConfig

        cfg = SummarizationConfig(token_threshold=5000, preserve_messages=5, model="gpt-4")
        assert cfg.token_threshold == 5000
        assert cfg.model == "gpt-4"


class TestLitigationSummarizationMiddleware:
    def _make(self):
        from apps.litigation_ai.agent.middleware import LitigationSummarizationMiddleware, SummarizationConfig

        cfg = SummarizationConfig(token_threshold=100, preserve_messages=2)
        return LitigationSummarizationMiddleware(session_id="s1", config=cfg)

    def test_should_summarize_true(self):
        mw = self._make()
        messages = [{"role": "user", "content": "x" * 500}]
        assert mw.should_summarize(messages) is True

    def test_should_summarize_false(self):
        mw = self._make()
        messages = [{"role": "user", "content": "short"}]
        assert mw.should_summarize(messages) is False

    @pytest.mark.asyncio
    async def test_summarize_short_messages(self):
        mw = self._make()
        messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        result = await mw.summarize(messages)
        assert result["summary"] is None

    def test_build_summary_prompt(self):
        mw = self._make()
        messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        prompt = mw._build_summary_prompt(messages)
        assert "user" in prompt
