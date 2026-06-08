"""Tests for core.llm.backends.siliconflow."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError


def _cfg(**kwargs: Any) -> BackendConfig:
    """Helper to create BackendConfig with required defaults."""
    defaults = {"name": "sf", "enabled": True, "priority": 1, "default_model": ""}
    defaults.update(kwargs)
    return BackendConfig(**defaults)


class TestSiliconFlowBackendInit:
    def test_default_init(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        assert backend.BACKEND_NAME == "siliconflow"
        assert backend._config is None

    def test_init_with_config(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(name="sf", enabled=True, priority=1, default_model="model-1", api_key="test-key", base_url="http://test")  # allowlist secret
        backend = SiliconFlowBackend(config=config)
        assert backend._config is config


class TestSiliconFlowProperties:
    def test_api_key_from_config(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test")  # allowlist secret
        backend = SiliconFlowBackend(config=config)
        assert backend.api_key == "sk-test"

    @patch("apps.core.llm.backends.siliconflow.LLMConfig")
    def test_api_key_from_settings(self, mock_config) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        mock_config.get_api_key.return_value = "sk-from-settings"
        backend = SiliconFlowBackend()
        assert backend.api_key == "sk-from-settings"

    def test_base_url_from_config(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(base_url="http://custom")
        backend = SiliconFlowBackend(config=config)
        assert backend.base_url == "http://custom"

    @patch("apps.core.llm.backends.siliconflow.LLMConfig")
    def test_base_url_from_settings(self, mock_config) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        mock_config.get_base_url.return_value = "http://default"
        backend = SiliconFlowBackend()
        assert backend.base_url == "http://default"

    def test_default_model_from_config(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(default_model="gpt-4")
        backend = SiliconFlowBackend(config=config)
        assert backend.default_model == "gpt-4"

    @patch("apps.core.llm.backends.siliconflow.LLMConfig")
    def test_default_model_from_settings(self, mock_config) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        mock_config.get_default_model.return_value = "gpt-3.5"
        backend = SiliconFlowBackend()
        assert backend.default_model == "gpt-3.5"

    def test_timeout_from_config(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(timeout=60)
        backend = SiliconFlowBackend(config=config)
        assert backend.timeout == 60

    @patch("apps.core.llm.backends.siliconflow.LLMConfig")
    def test_timeout_from_settings(self, mock_config) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        mock_config.get_timeout.return_value = 120
        backend = SiliconFlowBackend()
        assert backend.timeout == 120


class TestSiliconFlowHelpers:
    def test_normalize_messages(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "custom", "content": "test"},
        ]
        result = backend._normalize_messages(messages)
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "user"  # custom -> user

    def test_normalize_messages_defaults(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        result = backend._normalize_messages([{"content": "hi"}])
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hi"

    def test_extract_usage_none(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        usage = backend._extract_usage(None)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_extract_usage_with_data(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150
        usage = backend._extract_usage(mock_usage)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_extract_content_normal(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="Hello world"))]
        assert backend._extract_content(mock_resp) == "Hello world"

    def test_extract_content_empty_choices(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        mock_resp = MagicMock()
        mock_resp.choices = []
        assert backend._extract_content(mock_resp) == ""

    def test_extract_content_no_message(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=None)]
        assert backend._extract_content(mock_resp) == ""

    def test_extract_content_reasoning_content(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        backend = SiliconFlowBackend()
        mock_msg = MagicMock()
        mock_msg.content = ""
        mock_msg.reasoning_content = "reasoning output"
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg)]
        assert backend._extract_content(mock_resp) == "reasoning output"

    def test_resolve_embedding_model_explicit(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(embedding_model="embed-v1", default_model="gpt-4")
        backend = SiliconFlowBackend(config=config)
        assert backend._resolve_embedding_model("custom-model") == "custom-model"

    def test_resolve_embedding_model_from_config(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(embedding_model="embed-v1", default_model="gpt-4")
        backend = SiliconFlowBackend(config=config)
        assert backend._resolve_embedding_model() == "embed-v1"

    def test_resolve_embedding_model_fallback(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(default_model="gpt-4")
        backend = SiliconFlowBackend(config=config)
        assert backend._resolve_embedding_model() == "gpt-4"


class TestSiliconFlowErrorMapping:
    def _make_backend(self) -> Any:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="test", base_url="http://test", default_model="m")  # allowlist secret
        return SiliconFlowBackend(config=config)

    def test_authentication_error(self) -> None:
        import openai

        backend = self._make_backend()
        err = openai.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )
        with pytest.raises(LLMAuthenticationError):
            backend._raise_mapped_error(err, 10.0, "http://test")

    def test_timeout_error(self) -> None:
        import openai

        backend = self._make_backend()
        err = openai.APITimeoutError(request=MagicMock())
        with pytest.raises(LLMTimeoutError):
            backend._raise_mapped_error(err, 10.0, "http://test")

    def test_connection_error(self) -> None:
        import openai

        backend = self._make_backend()
        err = openai.APIConnectionError(request=MagicMock())
        with pytest.raises(LLMNetworkError):
            backend._raise_mapped_error(err, 10.0, "http://test")

    def test_api_error(self) -> None:
        import openai

        backend = self._make_backend()
        err = openai.APIStatusError(
            message="Server error",
            response=MagicMock(status_code=500),
            body=None,
        )
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(err, 10.0, "http://test")

    def test_generic_error(self) -> None:
        backend = self._make_backend()
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(RuntimeError("unexpected"), 10.0, "http://test")


class TestSiliconFlowAvailability:
    def test_available(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", default_model="gpt-4")  # allowlist secret
        backend = SiliconFlowBackend(config=config)
        assert backend.is_available() is True

    def test_not_available_disabled(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", default_model="gpt-4", enabled=False)  # allowlist secret
        backend = SiliconFlowBackend(config=config)
        assert backend.is_available() is False

    def test_not_available_no_key(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        with patch("apps.core.llm.backends.siliconflow.LLMConfig") as mock_cfg:
            mock_cfg.get_api_key.return_value = ""
            backend = SiliconFlowBackend()
            assert backend.is_available() is False

    def test_not_available_no_model(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", default_model="")  # allowlist secret
        with patch("apps.core.llm.backends.siliconflow.LLMConfig") as mock_cfg:
            mock_cfg.get_default_model.return_value = ""
            backend = SiliconFlowBackend(config=config)
            assert backend.is_available() is False

    def test_get_default_model(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(default_model="gpt-4")
        backend = SiliconFlowBackend(config=config)
        assert backend.get_default_model() == "gpt-4"

    def test_get_default_embedding_model(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(embedding_model="embed-v1")
        backend = SiliconFlowBackend(config=config)
        assert backend.get_default_embedding_model() == "embed-v1"


class TestSiliconFlowChat:
    @patch("apps.core.llm.backends.siliconflow.openai.OpenAI")
    def test_chat_success(self, mock_openai_cls) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="m", timeout=10)  # allowlist secret
        backend = SiliconFlowBackend(config=config)

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="Hi there"))]
        mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai_cls.return_value = mock_client

        result = backend.chat([{"role": "user", "content": "Hello"}])
        assert result.content == "Hi there"
        assert result.model == "m"
        assert result.backend == "siliconflow"

    @patch("apps.core.llm.backends.siliconflow.openai.OpenAI")
    def test_chat_with_max_tokens(self, mock_openai_cls) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="m", timeout=10)  # allowlist secret
        backend = SiliconFlowBackend(config=config)

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_resp.usage = MagicMock(prompt_tokens=5, completion_tokens=2, total_tokens=7)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai_cls.return_value = mock_client

        result = backend.chat([{"role": "user", "content": "Hi"}], max_tokens=100)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 100

    @patch("apps.core.llm.backends.siliconflow.openai.OpenAI")
    def test_chat_error_raises_mapped(self, mock_openai_cls) -> None:
        import openai
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="m", timeout=10)  # allowlist secret
        backend = SiliconFlowBackend(config=config)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Invalid", response=MagicMock(status_code=401), body=None
        )
        mock_openai_cls.return_value = mock_client

        with pytest.raises(LLMAuthenticationError):
            backend.chat([{"role": "user", "content": "Hi"}])


class TestSiliconFlowStream:
    @patch("apps.core.llm.backends.siliconflow.openai.OpenAI")
    def test_stream_yields_chunks(self, mock_openai_cls) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="m", timeout=10)  # allowlist secret
        backend = SiliconFlowBackend(config=config)

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content=" world"))]
        chunk2.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2])
        mock_openai_cls.return_value = mock_client

        chunks = list(backend.stream([{"role": "user", "content": "Hi"}]))
        assert len(chunks) == 2
        assert chunks[0].content == "Hello"
        assert chunks[1].content == " world"


class TestSiliconFlowEmbed:
    @patch("apps.core.llm.backends.siliconflow.openai.OpenAI")
    def test_embed_texts_success(self, mock_openai_cls) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="m",  # allowlist secret
                               embedding_model="embed-v1", timeout=10)
        backend = SiliconFlowBackend(config=config)

        mock_item = MagicMock()
        mock_item.embedding = [0.1, 0.2, 0.3]
        mock_resp = MagicMock()
        mock_resp.data = [mock_item]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_resp
        mock_openai_cls.return_value = mock_client

        result = backend.embed_texts(["hello", "world"])
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]

    def test_embed_texts_empty(self) -> None:
        from apps.core.llm.backends.siliconflow import SiliconFlowBackend

        config = _cfg(api_key="sk-test", default_model="m")  # allowlist secret
        backend = SiliconFlowBackend(config=config)
        assert backend.embed_texts([]) == []
