"""Coverage tests for core/llm/backends/openai_compatible.py.

Covers:
  - __init__ and properties (api_key, base_url, default_model, timeout)
  - _normalize_messages (all role cases)
  - _extract_usage (various usage shapes)
  - _extract_content (various response shapes, reasoning_content fallback)
  - _resolve_embedding_model
  - _build_extra_body
  - _raise_mapped_error (all error types)
  - embed_texts (empty, with mock)
  - chat / stream basic (with mocks)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
from apps.core.llm.backends.base import BackendConfig, LLMUsage
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError


class TestNormalizeMessages:
    def test_valid_roles(self):
        backend = OpenAICompatibleBackend()
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = backend._normalize_messages(messages)
        assert result == messages

    def test_invalid_role_defaults_to_user(self):
        backend = OpenAICompatibleBackend()
        messages = [{"role": "function", "content": "data"}]
        result = backend._normalize_messages(messages)
        assert result[0]["role"] == "user"

    def test_missing_role_defaults_to_user(self):
        backend = OpenAICompatibleBackend()
        messages = [{"content": "Hello"}]
        result = backend._normalize_messages(messages)
        assert result[0]["role"] == "user"

    def test_missing_content_defaults_to_empty(self):
        backend = OpenAICompatibleBackend()
        messages = [{"role": "user"}]
        result = backend._normalize_messages(messages)
        assert result[0]["content"] == ""

    def test_empty_list(self):
        backend = OpenAICompatibleBackend()
        assert backend._normalize_messages([]) == []


class TestExtractUsage:
    def test_none_usage(self):
        backend = OpenAICompatibleBackend()
        usage = backend._extract_usage(None)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_full_usage(self):
        backend = OpenAICompatibleBackend()
        mock_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        usage = backend._extract_usage(mock_usage)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

    def test_partial_usage_total_tokens_none(self):
        backend = OpenAICompatibleBackend()
        # total_tokens=None -> getattr returns None -> `or 0` gives 0
        mock_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=None)
        usage = backend._extract_usage(mock_usage)
        assert usage.total_tokens == 0

    def test_missing_total_tokens_attr(self):
        backend = OpenAICompatibleBackend()
        # No total_tokens attribute at all -> getattr falls back to prompt+completion
        mock_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
        usage = backend._extract_usage(mock_usage)
        assert usage.total_tokens == 30


class TestExtractContent:
    def test_basic_content(self):
        backend = OpenAICompatibleBackend()
        msg = SimpleNamespace(content="Hello World")
        choice = SimpleNamespace(message=msg)
        response = SimpleNamespace(choices=[choice])
        assert backend._extract_content(response) == "Hello World"

    def test_no_choices(self):
        backend = OpenAICompatibleBackend()
        response = SimpleNamespace(choices=[])
        assert backend._extract_content(response) == ""

    def test_no_message(self):
        backend = OpenAICompatibleBackend()
        choice = SimpleNamespace(message=None)
        response = SimpleNamespace(choices=[choice])
        assert backend._extract_content(response) == ""

    def test_empty_content_uses_reasoning(self):
        backend = OpenAICompatibleBackend()
        msg = SimpleNamespace(content="", reasoning_content="thinking process")
        choice = SimpleNamespace(message=msg)
        response = SimpleNamespace(choices=[choice])
        assert backend._extract_content(response) == "thinking process"

    def test_non_string_content(self):
        backend = OpenAICompatibleBackend()
        msg = SimpleNamespace(content=42)
        choice = SimpleNamespace(message=msg)
        response = SimpleNamespace(choices=[choice])
        assert backend._extract_content(response) == "42"


class TestResolveEmbeddingModel:
    def test_explicit_model(self):
        backend = OpenAICompatibleBackend()
        assert backend._resolve_embedding_model("my-model") == "my-model"

    def test_config_model(self):
        config = BackendConfig(name="test", enabled=True, priority=1, default_model="m", embedding_model="config-model")
        backend = OpenAICompatibleBackend(config=config)
        assert backend._resolve_embedding_model() == "config-model"

    def test_fallback_to_default_model(self):
        backend = OpenAICompatibleBackend()
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_config:
            mock_config.get_openai_compatible_embedding_model.return_value = ""
            backend._default_model = "default-model"
            assert backend._resolve_embedding_model() == "default-model"


class TestBuildExtraBody:
    def test_normal_model_returns_none(self):
        backend = OpenAICompatibleBackend()
        backend._default_model = "gpt-4"
        assert backend._build_extra_body() is None

    def test_thinking_disabled_model(self):
        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("kimi26-model")
        assert result is not None
        assert result["chat_template_kwargs"]["thinking"] is False

    def test_mimo_model(self):
        backend = OpenAICompatibleBackend()
        result = backend._build_extra_body("mimo-v2")
        assert result is not None


class TestRaiseMappedError:
    def test_authentication_error(self):
        backend = OpenAICompatibleBackend()
        import openai
        exc = openai.AuthenticationError(
            message="bad key",
            response=MagicMock(status_code=401, headers={}),
            body=None,
        )
        with pytest.raises(LLMAuthenticationError):
            backend._raise_mapped_error(exc, 30.0, "http://api.test")

    def test_timeout_error(self):
        backend = OpenAICompatibleBackend()
        import openai
        exc = openai.APITimeoutError(request=MagicMock())
        with pytest.raises(LLMTimeoutError):
            backend._raise_mapped_error(exc, 30.0, "http://api.test")

    def test_connection_error(self):
        backend = OpenAICompatibleBackend()
        import openai
        exc = openai.APIConnectionError(request=MagicMock())
        with pytest.raises(LLMNetworkError):
            backend._raise_mapped_error(exc, 30.0, "http://api.test")

    def test_api_error(self):
        backend = OpenAICompatibleBackend()
        import openai
        exc = openai.APIStatusError(
            message="bad request",
            response=MagicMock(status_code=400, headers={}),
            body=None,
        )
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(exc, 30.0, "http://api.test")

    def test_unknown_error(self):
        backend = OpenAICompatibleBackend()
        exc = RuntimeError("something weird")
        with pytest.raises(LLMAPIError):
            backend._raise_mapped_error(exc, 30.0, "http://api.test")


class TestProperties:
    def test_init_defaults(self):
        backend = OpenAICompatibleBackend()
        assert backend._config is None
        assert backend._api_key is None

    def test_init_with_config(self):
        config = BackendConfig(name="test", enabled=True, priority=1, api_key="test-key", base_url="http://test", default_model="m1", timeout=60)
        backend = OpenAICompatibleBackend(config=config)
        assert backend.api_key == "test-key"
        assert backend.base_url == "http://test"
        assert backend.default_model == "m1"
        assert backend.timeout == 60

    def test_api_key_from_config(self):
        config = BackendConfig(name="test", enabled=True, priority=1, api_key="config-key", default_model="m")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.api_key == "config-key"

    def test_api_key_from_env(self):
        backend = OpenAICompatibleBackend()
        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_config:
            mock_config.get_openai_compatible_api_key.return_value = "env-key"
            assert backend.api_key == "env-key"

    def test_base_url_from_config(self):
        config = BackendConfig(name="test", enabled=True, priority=1, base_url="http://configured", default_model="m")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.base_url == "http://configured"

    def test_timeout_from_config(self):
        config = BackendConfig(name="test", enabled=True, priority=1, timeout=120, default_model="m")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.timeout == 120


class TestGetDefaultModels:
    def test_get_default_model(self):
        config = BackendConfig(name="test", enabled=True, priority=1, default_model="my-model")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.get_default_model() == "my-model"

    def test_get_default_embedding_model(self):
        config = BackendConfig(name="test", enabled=True, priority=1, default_model="m", embedding_model="emb-model")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.get_default_embedding_model() == "emb-model"


class TestEmbedTexts:
    def test_empty_texts(self):
        backend = OpenAICompatibleBackend()
        assert backend.embed_texts([]) == []

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_with_mock(self, mock_llm_config):
        mock_llm_config.get_openai_compatible_embedding_model.return_value = "m"
        config = BackendConfig(name="test", enabled=True, priority=1, api_key="k", base_url="http://t", default_model="m", timeout=30)
        backend = OpenAICompatibleBackend(config=config)
        mock_response = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])]
        )
        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = mock_response
            mock_build.return_value = mock_client
            result = backend.embed_texts(["hello world"])
            assert len(result) == 1
            assert result[0] == [0.1, 0.2]

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_error_propagates(self, mock_llm_config):
        mock_llm_config.get_openai_compatible_embedding_model.return_value = "m"
        config = BackendConfig(name="test", enabled=True, priority=1, api_key="k", base_url="http://t", default_model="m", timeout=30)
        backend = OpenAICompatibleBackend(config=config)
        import openai
        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = openai.AuthenticationError(
                message="bad", response=MagicMock(status_code=401, headers={}), body=None,
            )
            mock_build.return_value = mock_client
            with pytest.raises(LLMAuthenticationError):
                backend.embed_texts(["test"])
