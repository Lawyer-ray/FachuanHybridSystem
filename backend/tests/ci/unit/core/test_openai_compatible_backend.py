from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
from apps.core.llm.exceptions import (
    LLMAPIError,
    LLMAuthenticationError,
    LLMNetworkError,
    LLMTimeoutError,
)


def _config(**overrides):
    defaults = {
        "name": "openai_compatible",
        "enabled": True,
        "priority": 1,
        "default_model": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "timeout": 30,
        "embedding_model": "text-embedding-ada-002",
    }
    defaults.update(overrides)
    return BackendConfig(**defaults)


# ── __init__ ─────────────────────────────────────────────────────────────────


class TestInit:

    def test_default_state(self):
        b = OpenAICompatibleBackend()
        assert b._config is None
        assert b._api_key is None

    def test_with_config(self):
        b = OpenAICompatibleBackend(config=_config())
        assert b._config is not None


# ── Properties ───────────────────────────────────────────────────────────────


class TestProperties:

    def test_api_key_from_config(self):
        b = OpenAICompatibleBackend(config=_config(api_key="cfg-key"))
        assert b.api_key == "cfg-key"

    def test_api_key_from_llm_config(self):
        b = OpenAICompatibleBackend()
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_api_key.return_value = "env-key"
            assert b.api_key == "env-key"

    def test_base_url_from_config(self):
        b = OpenAICompatibleBackend(config=_config(base_url="http://test"))
        assert b.base_url == "http://test"

    def test_base_url_from_llm_config(self):
        b = OpenAICompatibleBackend()
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_base_url.return_value = "http://env"
            assert b.base_url == "http://env"

    def test_default_model_from_config(self):
        b = OpenAICompatibleBackend(config=_config(default_model="my-model"))
        assert b.default_model == "my-model"

    def test_default_model_from_llm_config(self):
        b = OpenAICompatibleBackend()
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_model.return_value = "env-model"
            assert b.default_model == "env-model"

    def test_timeout_from_config(self):
        b = OpenAICompatibleBackend(config=_config(timeout=42))
        assert b.timeout == 42

    def test_timeout_from_llm_config(self):
        b = OpenAICompatibleBackend()
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_timeout.return_value = 99
            assert b.timeout == 99


# ── _normalize_messages ─────────────────────────────────────────────────────


class TestNormalizeMessages:

    def test_valid_roles(self):
        b = OpenAICompatibleBackend(config=_config())
        msgs = [{"role": "system", "content": "hi"}, {"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        result = b._normalize_messages(msgs)
        assert len(result) == 3
        assert result[0]["role"] == "system"

    def test_unknown_role_becomes_user(self):
        b = OpenAICompatibleBackend(config=_config())
        result = b._normalize_messages([{"role": "function", "content": "x"}])
        assert result[0]["role"] == "user"

    def test_missing_role_defaults_to_user(self):
        b = OpenAICompatibleBackend(config=_config())
        result = b._normalize_messages([{"content": "x"}])
        assert result[0]["role"] == "user"

    def test_missing_content(self):
        b = OpenAICompatibleBackend(config=_config())
        result = b._normalize_messages([{"role": "user"}])
        assert result[0]["content"] == ""


# ── _extract_usage ──────────────────────────────────────────────────────────


class TestExtractUsage:

    def test_none_usage(self):
        b = OpenAICompatibleBackend(config=_config())
        usage = b._extract_usage(None)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_usage_with_values(self):
        b = OpenAICompatibleBackend(config=_config())
        obj = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        usage = b._extract_usage(obj)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

    def test_usage_with_zero_total(self):
        b = OpenAICompatibleBackend(config=_config())
        obj = SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=0)
        usage = b._extract_usage(obj)
        # total_tokens is 0 which is falsy; the `or 0` clause keeps it as 0
        assert usage.total_tokens == 0

    def test_usage_with_none_total(self):
        b = OpenAICompatibleBackend(config=_config())
        obj = SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=None)
        usage = b._extract_usage(obj)
        # total_tokens=None is falsy, fallback to prompt_tokens + completion_tokens = 8
        # but int(None or 0) = int(0) = 0
        assert usage.total_tokens == 0


# ── _extract_content ─────────────────────────────────────────────────────────


class TestExtractContent:

    def test_normal_content(self):
        b = OpenAICompatibleBackend(config=_config())
        msg = SimpleNamespace(content="hello", reasoning_content=None)
        resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        assert b._extract_content(resp) == "hello"

    def test_empty_content_with_reasoning(self):
        b = OpenAICompatibleBackend(config=_config())
        msg = SimpleNamespace(content=None, reasoning_content="thought process")
        resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        assert b._extract_content(resp) == "thought process"

    def test_no_choices(self):
        b = OpenAICompatibleBackend(config=_config())
        resp = SimpleNamespace(choices=[])
        assert b._extract_content(resp) == ""

    def test_no_message(self):
        b = OpenAICompatibleBackend(config=_config())
        resp = SimpleNamespace(choices=[SimpleNamespace(message=None)])
        assert b._extract_content(resp) == ""

    def test_non_string_content(self):
        b = OpenAICompatibleBackend(config=_config())
        msg = SimpleNamespace(content=12345, reasoning_content=None)
        resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        assert b._extract_content(resp) == "12345"


# ── _resolve_embedding_model ────────────────────────────────────────────────


class TestResolveEmbeddingModel:

    def test_explicit_model(self):
        b = OpenAICompatibleBackend(config=_config())
        assert b._resolve_embedding_model("custom-model") == "custom-model"

    def test_from_config(self):
        b = OpenAICompatibleBackend(config=_config(embedding_model="emb-config"))
        assert b._resolve_embedding_model() == "emb-config"

    def test_falls_back_to_default_model(self):
        b = OpenAICompatibleBackend(config=_config(default_model="gpt-4", embedding_model=None))
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_embedding_model.return_value = ""
            assert b._resolve_embedding_model() == "gpt-4"


# ── _build_extra_body ────────────────────────────────────────────────────────


class TestBuildExtraBody:

    def test_kimi_model(self):
        b = OpenAICompatibleBackend(config=_config())
        result = b._build_extra_body("kimi26")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_mimo_model(self):
        b = OpenAICompatibleBackend(config=_config())
        result = b._build_extra_body("MiMo-7B")
        assert result is not None

    def test_normal_model_returns_none(self):
        b = OpenAICompatibleBackend(config=_config())
        assert b._build_extra_body("gpt-4") is None

    def test_none_model_uses_default(self):
        b = OpenAICompatibleBackend(config=_config(default_model="gpt-4"))
        assert b._build_extra_body(None) is None


# ── _raise_mapped_error ─────────────────────────────────────────────────────


class TestRaiseMappedError:

    def test_auth_error(self):
        b = OpenAICompatibleBackend(config=_config())
        import openai

        err = openai.AuthenticationError(
            "Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body={"error": {"message": "Invalid API key"}},
        )
        with pytest.raises(LLMAuthenticationError):
            b._raise_mapped_error(err, 30.0, "http://test")

    def test_timeout_error(self):
        b = OpenAICompatibleBackend(config=_config())
        import openai

        err = openai.APITimeoutError(request=MagicMock())
        with pytest.raises(LLMTimeoutError):
            b._raise_mapped_error(err, 30.0, "http://test")

    def test_httpx_timeout(self):
        b = OpenAICompatibleBackend(config=_config())
        err = httpx.TimeoutException("timeout")
        with pytest.raises(LLMTimeoutError):
            b._raise_mapped_error(err, 30.0, "http://test")

    def test_connection_error(self):
        b = OpenAICompatibleBackend(config=_config())
        import openai

        err = openai.APIConnectionError(request=MagicMock())
        with pytest.raises(LLMNetworkError):
            b._raise_mapped_error(err, 30.0, "http://test")

    def test_httpx_connect_error(self):
        b = OpenAICompatibleBackend(config=_config())
        err = httpx.ConnectError("connection refused")
        with pytest.raises(LLMNetworkError):
            b._raise_mapped_error(err, 30.0, "http://test")

    def test_api_error(self):
        b = OpenAICompatibleBackend(config=_config())
        import openai

        err = openai.APIStatusError(
            "Server error",
            response=MagicMock(status_code=500, headers={}),
            body={"error": {"message": "Server error"}},
        )
        with pytest.raises(LLMAPIError):
            b._raise_mapped_error(err, 30.0, "http://test")

    def test_generic_error(self):
        b = OpenAICompatibleBackend(config=_config())
        with pytest.raises(LLMAPIError):
            b._raise_mapped_error(ValueError("weird"), 30.0, "http://test")


# ── chat ─────────────────────────────────────────────────────────────────────


class TestChat:

    def test_successful_chat(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi", reasoning_content=None))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            result = b.chat([{"role": "user", "content": "hello"}])
            assert isinstance(result, LLMResponse)
            assert result.content == "hi"
            assert result.prompt_tokens == 5
            assert result.backend == "openai_compatible"

    def test_chat_with_max_tokens(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", reasoning_content=None))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            result = b.chat([{"role": "user", "content": "hi"}], max_tokens=100)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["max_tokens"] == 100

    def test_chat_with_extra_body_for_kimi(self):
        b = OpenAICompatibleBackend(config=_config(default_model="kimi26"))
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", reasoning_content=None))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            b.chat([{"role": "user", "content": "hi"}])
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "extra_body" in call_kwargs

    def test_chat_error_mapped(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = httpx.TimeoutException("timeout")
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            with pytest.raises(LLMTimeoutError):
                b.chat([{"role": "user", "content": "hi"}])


# ── stream ───────────────────────────────────────────────────────────────────


class TestStream:

    def test_yields_content_chunks(self):
        b = OpenAICompatibleBackend(config=_config())
        chunk1 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel"))],
            usage=None,
        )
        chunk2 = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))],
            usage=None,
        )
        chunk3 = SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            chunks = list(b.stream([{"role": "user", "content": "hi"}]))
            assert len(chunks) == 3
            assert chunks[0].content == "Hel"
            assert chunks[1].content == "lo"
            assert chunks[2].usage is not None

    def test_stream_error_mapped(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = httpx.ConnectError("fail")
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            with pytest.raises(LLMNetworkError):
                list(b.stream([{"role": "user", "content": "hi"}]))

    def test_stream_with_extra_body(self):
        b = OpenAICompatibleBackend(config=_config(default_model="mimo"))
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([])
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            list(b.stream([{"role": "user", "content": "hi"}]))
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "extra_body" in call_kwargs


# ── embed_texts ──────────────────────────────────────────────────────────────


class TestEmbedTexts:

    def test_empty_texts(self):
        b = OpenAICompatibleBackend(config=_config())
        assert b.embed_texts([]) == []

    def test_successful_embedding(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_resp = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3]), SimpleNamespace(embedding=[0.4, 0.5, 0.6])]
        )
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_resp
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            result = b.embed_texts(["hello", "world"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2, 0.3]

    def test_embedding_error(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = httpx.TimeoutException("timeout")
        with patch.object(b, "_build_sync_client", return_value=mock_client):
            with pytest.raises(LLMTimeoutError):
                b.embed_texts(["text"])


# ── is_available ─────────────────────────────────────────────────────────────


class TestIsAvailable:

    def test_available(self):
        b = OpenAICompatibleBackend(config=_config())
        assert b.is_available() is True

    def test_disabled(self):
        b = OpenAICompatibleBackend(config=_config(enabled=False))
        assert b.is_available() is False

    def test_no_api_key(self):
        b = OpenAICompatibleBackend(config=_config(api_key=""))
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_api_key.return_value = ""
            assert b.is_available() is False

    def test_no_model(self):
        b = OpenAICompatibleBackend(config=_config(default_model=""))
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_model.return_value = ""
            assert b.is_available() is False


# ── get_default_model / get_default_embedding_model ──────────────────────────


class TestGetters:

    def test_get_default_model(self):
        b = OpenAICompatibleBackend(config=_config(default_model="mymodel"))
        assert b.get_default_model() == "mymodel"

    def test_get_default_embedding_model(self):
        b = OpenAICompatibleBackend(config=_config(embedding_model="emb"))
        assert b.get_default_embedding_model() == "emb"


# ── _build_sync_client ──────────────────────────────────────────────────────


class TestBuildSyncClient:

    def test_builds_client(self):
        b = OpenAICompatibleBackend(config=_config())
        client = b._build_sync_client(timeout_seconds=15)
        assert client is not None


# ── achat ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAchat:

    async def test_successful_achat(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="async hi", reasoning_content=None))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch.object(b, "_build_async_client", return_value=mock_client):
            result = await b.achat([{"role": "user", "content": "hello"}])
            assert result.content == "async hi"

    async def test_achat_error(self):
        b = OpenAICompatibleBackend(config=_config())
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch.object(b, "_build_async_client", return_value=mock_client):
            with pytest.raises(LLMTimeoutError):
                await b.achat([{"role": "user", "content": "hi"}])
