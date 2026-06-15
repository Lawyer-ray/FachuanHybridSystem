"""Tests for apps.core.llm.client — LLMClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.backends.base import LLMResponse
from apps.core.llm.client import LLMClient


def _make_response(content: str = "ok") -> LLMResponse:
    return LLMResponse(
        content=content, model="m", prompt_tokens=1,
        completion_tokens=1, total_tokens=2, duration_ms=1.0, backend="test",
    )


class TestLLMClientResolveBackend:
    def test_explicit_backend(self):
        assert LLMClient._resolve_backend("ollama", None, "openai_compatible") == "ollama"

    def test_model_based_resolution(self):
        with patch("apps.core.llm.config.LLMConfig.resolve_backend_for_model", return_value="ollama") as mock_resolve:
            result = LLMClient._resolve_backend(None, "qwen3:0.6b", "openai_compatible")
            assert result == "ollama"
            mock_resolve.assert_called_once_with("qwen3:0.6b")

    def test_fallback_to_default(self):
        result = LLMClient._resolve_backend(None, None, "openai_compatible")
        assert result == "openai_compatible"


class TestLLMClientComplete:
    def test_complete_without_system_prompt(self):
        client = LLMClient(default_backend="test")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = _make_response("hi")
        result = client.complete(fallback_policy=mock_policy, prompt="hello")
        assert result.content == "hi"

    def test_complete_with_system_prompt(self):
        client = LLMClient(default_backend="test")
        mock_policy = MagicMock()
        captured = {}

        def fake_execute(operation=None, backend="", fallback=True):
            captured["op"] = operation
            return _make_response("reply")

        mock_policy.execute.side_effect = fake_execute
        client.complete(fallback_policy=mock_policy, prompt="hi", system_prompt="sys")
        op = captured["op"]
        mock_backend = MagicMock()
        mock_backend.chat.return_value = _make_response("reply")
        result = op(mock_backend)
        msgs = mock_backend.chat.call_args[1]["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_complete_passes_temperature_and_max_tokens(self):
        client = LLMClient(default_backend="t")
        mock_policy = MagicMock()
        captured = {}
        mock_policy.execute.side_effect = lambda operation=None, **kw: (captured.update(kw) or _make_response())
        client.complete(fallback_policy=mock_policy, prompt="x", temperature=0.1, max_tokens=100)
        assert "backend" in captured


class TestLLMClientChat:
    def test_chat_explicit_backend(self):
        client = LLMClient(default_backend="default")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = _make_response("chat_ok")
        msgs = [{"role": "user", "content": "hi"}]
        result = client.chat(fallback_policy=mock_policy, messages=msgs, backend="ollama")
        assert result.content == "chat_ok"
        assert mock_policy.execute.call_args[1]["backend"] == "ollama"

    def test_chat_default_backend(self):
        client = LLMClient(default_backend="def")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = _make_response()
        client.chat(fallback_policy=mock_policy, messages=[])
        assert mock_policy.execute.call_args[1]["backend"] == "def"

    def test_chat_fallback_false(self):
        client = LLMClient(default_backend="t")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = _make_response()
        client.chat(fallback_policy=mock_policy, messages=[], fallback=False)
        assert mock_policy.execute.call_args[1]["fallback"] is False

    def test_chat_operation_calls_backend_chat(self):
        client = LLMClient(default_backend="t")
        mock_policy = MagicMock()
        captured = {}
        def fake_execute(operation=None, **kw):
            captured["op"] = operation
            return _make_response()
        mock_policy.execute.side_effect = fake_execute
        client.chat(fallback_policy=mock_policy, messages=[{"role": "user", "content": "test"}])
        mock_b = MagicMock()
        mock_b.chat.return_value = _make_response()
        captured["op"](mock_b)
        mock_b.chat.assert_called_once()


class TestLLMClientAchat:
    @pytest.mark.asyncio
    async def test_achat(self):
        client = LLMClient(default_backend="ab")
        mock_policy = AsyncMock()
        mock_policy.execute_async.return_value = _make_response("async_ok")
        msgs = [{"role": "user", "content": "hi"}]
        result = await client.achat(fallback_policy=mock_policy, messages=msgs)
        assert result.content == "async_ok"
        assert mock_policy.execute_async.call_args[1]["backend"] == "ab"

    @pytest.mark.asyncio
    async def test_achat_explicit_backend(self):
        client = LLMClient(default_backend="ab")
        mock_policy = AsyncMock()
        mock_policy.execute_async.return_value = _make_response()
        await client.achat(fallback_policy=mock_policy, messages=[], backend="custom")
        assert mock_policy.execute_async.call_args[1]["backend"] == "custom"

    @pytest.mark.asyncio
    async def test_achat_operation_calls_backend(self):
        client = LLMClient(default_backend="ab")
        captured = {}
        async def fake_exec(operation=None, **kw):
            captured["op"] = operation
            return _make_response()
        mock_policy = AsyncMock()
        mock_policy.execute_async.side_effect = fake_exec
        await client.achat(fallback_policy=mock_policy, messages=[{"role": "user", "content": "x"}])
        mock_b = AsyncMock()
        mock_b.achat.return_value = _make_response()
        result = await captured["op"](mock_b)
        mock_b.achat.assert_called_once()


class TestLLMClientEmbedTexts:
    def test_embed_texts(self):
        client = LLMClient(default_backend="eb")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = [[0.1, 0.2]]
        result = client.embed_texts(fallback_policy=mock_policy, texts=["hello"])
        assert result == [[0.1, 0.2]]

    def test_embed_texts_explicit_backend(self):
        client = LLMClient(default_backend="eb")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = [[0.3]]
        client.embed_texts(fallback_policy=mock_policy, texts=["x"], backend="custom")
        assert mock_policy.execute.call_args[1]["backend"] == "custom"

    def test_embed_texts_no_backend_uses_default(self):
        client = LLMClient(default_backend="def")
        mock_policy = MagicMock()
        mock_policy.execute.return_value = []
        client.embed_texts(fallback_policy=mock_policy, texts=[])
        assert mock_policy.execute.call_args[1]["backend"] == "def"

    def test_embed_texts_operation_calls_backend(self):
        client = LLMClient(default_backend="def")
        captured = {}
        def fake_execute(operation=None, **kw):
            captured["op"] = operation
            return [[0.5]]
        mock_policy = MagicMock()
        mock_policy.execute.side_effect = fake_execute
        client.embed_texts(fallback_policy=mock_policy, texts=["test"])
        mock_b = MagicMock()
        mock_b.embed_texts.return_value = [[0.5]]
        result = captured["op"](mock_b)
        mock_b.embed_texts.assert_called_once()
