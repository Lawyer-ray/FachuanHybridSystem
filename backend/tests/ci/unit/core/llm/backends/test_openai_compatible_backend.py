"""openai_compatible backend 补充覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from typing import Any

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError


def _cfg(**kwargs: Any) -> BackendConfig:
    defaults = {"name": "oai", "enabled": True, "priority": 1, "default_model": "gpt-4o"}
    defaults.update(kwargs)
    return BackendConfig(**defaults)


# ── _build_extra_body ─────────────────────────────────────────────

class TestBuildExtraBody:
    def test_kimi_model_disables_thinking(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("kimi26-chat")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_mimo_model_disables_thinking(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("mimo-v1")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_normal_model_no_extra(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("gpt-4o")
        assert result is None

    def test_none_model_uses_default(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="normal-model")
        backend = OpenAICompatibleBackend(config=config)
        result = backend._build_extra_body(None)
        assert result is None


# ── Properties ────────────────────────────────────────────────────

class TestProperties:
    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_api_key_from_config(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test-key")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.api_key == "sk-test-key"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_api_key_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_api_key.return_value = "sk-from-settings"
        backend = OpenAICompatibleBackend()
        assert backend.api_key == "sk-from-settings"

    def test_base_url_from_config(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(base_url="http://custom")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.base_url == "http://custom"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_base_url_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_base_url.return_value = "http://default"
        backend = OpenAICompatibleBackend()
        assert backend.base_url == "http://default"

    def test_default_model_from_config(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="deepseek-chat")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.default_model == "deepseek-chat"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_default_model_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_model.return_value = "gpt-3.5"
        backend = OpenAICompatibleBackend()
        assert backend.default_model == "gpt-3.5"

    def test_timeout_from_config(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(timeout=60)
        backend = OpenAICompatibleBackend(config=config)
        assert backend.timeout == 60

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_timeout_from_settings(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_timeout.return_value = 120
        backend = OpenAICompatibleBackend()
        assert backend.timeout == 120


# ── _resolve_embedding_model ──────────────────────────────────────

class TestResolveEmbeddingModel:
    def test_explicit_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)
        assert backend._resolve_embedding_model("text-embedding-3-small") == "text-embedding-3-small"

    def test_config_embedding_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(default_model="gpt-4o", embedding_model="embed-v2")
        backend = OpenAICompatibleBackend(config=config)
        assert backend._resolve_embedding_model() == "embed-v2"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_settings_embedding_model(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_api_key.return_value = "k"
        mock_cfg.get_openai_compatible_base_url.return_value = "http://test"
        mock_cfg.get_openai_compatible_model.return_value = "default-model"
        mock_cfg.get_openai_compatible_embedding_model.return_value = "embed-from-settings"
        mock_cfg.get_openai_compatible_timeout.return_value = 30
        backend = OpenAICompatibleBackend()
        assert backend._resolve_embedding_model() == "embed-from-settings"

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_fallback_to_default_model(self, mock_cfg):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        mock_cfg.get_openai_compatible_api_key.return_value = "k"
        mock_cfg.get_openai_compatible_base_url.return_value = "http://test"
        mock_cfg.get_openai_compatible_model.return_value = "gpt-4o"
        mock_cfg.get_openai_compatible_embedding_model.return_value = ""
        mock_cfg.get_openai_compatible_timeout.return_value = 30
        backend = OpenAICompatibleBackend()
        assert backend._resolve_embedding_model() == "gpt-4o"


# ── _raise_mapped_error ───────────────────────────────────────────

class TestRaiseMappedError:
    def test_authentication_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body=None,
        )
        with pytest.raises(LLMAuthenticationError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_timeout_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.APITimeoutError(request=MagicMock())
        with pytest.raises(LLMTimeoutError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_connection_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.APIConnectionError(request=MagicMock())
        with pytest.raises(LLMNetworkError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_api_error(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        err = openai.APIError(
            message="Server error",
            request=MagicMock(),
            body={"error": "internal"},
        )
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(err, 30.0, "http://test")

    def test_generic_error(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(RuntimeError("unexpected"), 30.0, "http://test")


# ── chat (sync) ───────────────────────────────────────────────────

class TestChat:
    def test_chat_success(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "Hi"}])
            assert result.content == "Hello!"
            assert result.model == "gpt-4o"
            assert result.prompt_tokens == 10
            assert result.completion_tokens == 5

    def test_chat_with_kimi_model_injects_extra_body(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="kimi26-chat")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "test"}])
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "extra_body" in call_kwargs
            assert call_kwargs["extra_body"]["chat_template_kwargs"]["thinking"] is False

    def test_chat_with_max_tokens(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "test"}], max_tokens=100)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["max_tokens"] == 100

    def test_chat_error_raises(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = openai.APITimeoutError(request=MagicMock())
            mock_build.return_value = mock_client

            with pytest.raises(LLMTimeoutError):
                backend.chat([{"role": "user", "content": "test"}])


# ── stream ────────────────────────────────────────────────────────

class TestStream:
    def test_stream_yields_chunks(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]
        chunk2.usage = None

        final_chunk = MagicMock()
        final_chunk.choices = []
        final_chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, final_chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}]))
            content_chunks = [c for c in chunks if c.content]
            assert len(content_chunks) == 2
            assert content_chunks[0].content == "Hello"
            assert content_chunks[1].content == " world"

    def test_stream_with_max_tokens(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="OK"))]
        chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}], max_tokens=50))
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["max_tokens"] == 50

    def test_stream_with_kimi_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="kimi26-chat")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content="OK"))]
        chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            list(backend.stream([{"role": "user", "content": "test"}]))
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "extra_body" in call_kwargs

    def test_stream_error_raises(self):
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = openai.APIConnectionError(request=MagicMock())
            mock_build.return_value = mock_client

            with pytest.raises(LLMNetworkError):
                list(backend.stream([{"role": "user", "content": "test"}]))

    def test_stream_empty_choices(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = []
        chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}]))
            # Should still yield the usage chunk
            assert any(c.usage is not None for c in chunks)

    def test_stream_no_content_no_usage(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=None))]
        chunk.usage = None

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = iter([chunk])
            mock_build.return_value = mock_client

            chunks = list(backend.stream([{"role": "user", "content": "test"}]))
            # No content and no usage => no chunks yielded
            assert len(chunks) == 0


# ── _build_sync_client ────────────────────────────────────────────

class TestBuildSyncClient:
    @patch.dict("os.environ", {"LLM_SSL_VERIFY": "false"})
    def test_ssl_verify_disabled(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test")
        backend = OpenAICompatibleBackend(config=config)
        client = backend._build_sync_client(timeout_seconds=30)
        assert client is not None

    @patch.dict("os.environ", {"LLM_SSL_VERIFY": "true"})
    def test_ssl_verify_enabled(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test")
        backend = OpenAICompatibleBackend(config=config)
        client = backend._build_sync_client()
        assert client is not None
