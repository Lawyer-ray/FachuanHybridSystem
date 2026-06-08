"""Tests for core.llm.backends.ollama."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk, LLMUsage
from apps.core.llm.backends.ollama import OllamaBackend
from apps.core.llm.exceptions import LLMAPIError


def _cfg(**kwargs: Any) -> BackendConfig:
    """Helper to create BackendConfig with required defaults."""
    defaults = {"name": "ollama", "enabled": True, "priority": 2, "default_model": ""}
    defaults.update(kwargs)
    return BackendConfig(**defaults)


class TestOllamaBackendInit:
    def test_default_init(self) -> None:
        backend = OllamaBackend()
        assert backend.BACKEND_NAME == "ollama"
        assert backend.DEFAULT_MODEL == "qwen3:0.6b"
        assert backend.DEFAULT_BASE_URL == "http://localhost:11434"
        assert backend.DEFAULT_TIMEOUT == 120.0

    def test_init_with_config(self) -> None:
        config = _cfg(base_url="http://custom", default_model="m1", timeout=30)
        backend = OllamaBackend(config=config)
        assert backend._config is config


class TestOllamaProperties:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_base_url_from_config(self, mock_cfg) -> None:
        config = _cfg(base_url="http://custom")
        backend = OllamaBackend(config=config)
        assert backend.base_url == "http://custom"

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_base_url_from_settings(self, mock_cfg) -> None:
        mock_cfg.get_ollama_base_url.return_value = "http://default"
        backend = OllamaBackend()
        assert backend.base_url == "http://default"

    def test_default_model_from_config(self) -> None:
        config = _cfg(default_model="llama3")
        backend = OllamaBackend(config=config)
        assert backend.default_model == "llama3"

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_default_model_from_settings(self, mock_cfg) -> None:
        mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
        backend = OllamaBackend()
        assert backend.default_model == "qwen3:0.6b"

    def test_timeout_from_config(self) -> None:
        config = _cfg(timeout=60)
        backend = OllamaBackend(config=config)
        assert backend.timeout == 60.0

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_timeout_from_settings(self, mock_cfg) -> None:
        mock_cfg.get_ollama_timeout.return_value = 90
        backend = OllamaBackend()
        assert backend.timeout == 90.0

    def test_embedding_model_from_config(self) -> None:
        config = _cfg(embedding_model="nomic-embed")
        backend = OllamaBackend(config=config)
        assert backend.default_embedding_model == "nomic-embed"

    def test_embedding_model_fallback_to_default(self) -> None:
        config = _cfg(default_model="llama3")
        backend = OllamaBackend(config=config)
        assert backend.default_embedding_model == "llama3"


class TestOllamaBuildUrls:
    def test_build_api_url(self) -> None:
        config = _cfg(base_url="http://localhost:11434")
        backend = OllamaBackend(config=config)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"

    def test_build_api_url_trailing_slash(self) -> None:
        config = _cfg(base_url="http://localhost:11434/")
        backend = OllamaBackend(config=config)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"

    def test_build_embed_url(self) -> None:
        config = _cfg(base_url="http://localhost:11434")
        backend = OllamaBackend(config=config)
        assert backend._build_embed_url() == "http://localhost:11434/api/embed"

    def test_build_legacy_embed_url(self) -> None:
        config = _cfg(base_url="http://localhost:11434")
        backend = OllamaBackend(config=config)
        assert backend._build_legacy_embed_url() == "http://localhost:11434/api/embeddings"


class TestOllamaBuildOptions:
    def test_default_temperature(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        result = backend._build_options(temperature=0.7)
        assert result is None

    def test_custom_temperature(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        result = backend._build_options(temperature=0.3)
        assert result is not None
        assert result["temperature"] == 0.3

    def test_max_tokens(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        result = backend._build_options(temperature=0.7, max_tokens=100)
        assert result is not None
        assert result["num_predict"] == 100

    def test_num_predict_takes_priority(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        result = backend._build_options(temperature=0.7, max_tokens=100, num_predict=200)
        assert result["num_predict"] == 200

    def test_ollama_specific_options(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        result = backend._build_options(temperature=0.5, top_k=40, top_p=0.9, seed=42)
        assert result["top_k"] == 40
        assert result["top_p"] == 0.9
        assert result["seed"] == 42

    def test_none_values_ignored(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        result = backend._build_options(temperature=0.5, top_k=None)
        assert "top_k" not in (result or {})


class TestOllamaBuildLLMResponse:
    def test_normal_content(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        data = {
            "message": {"content": "Hello"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        resp = backend._build_llm_response(data, "m", 100.0)
        assert resp.content == "Hello"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.total_tokens == 15
        assert resp.backend == "ollama"

    def test_thinking_content(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        data = {
            "message": {"content": "", "thinking": "Let me think..."},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        resp = backend._build_llm_response(data, "m", 100.0)
        assert resp.content == "Let me think..."

    def test_empty_message(self) -> None:
        config = _cfg(default_model="m")
        backend = OllamaBackend(config=config)
        data = {
            "message": {},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        resp = backend._build_llm_response(data, "m", 50.0)
        assert resp.content == ""


class TestOllamaHandleHttpError:
    def test_404_raises_descriptive_error(self) -> None:
        config = _cfg(base_url="http://localhost:11434", default_model="m")
        backend = OllamaBackend(config=config)

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_resp.headers = {}
        error = MagicMock()
        error.response = mock_resp
        error.__class__.__name__ = "HTTPStatusError"

        with pytest.raises(LLMAPIError, match="未找到"):
            backend._handle_http_error(error, "m")

    def test_500_raises_api_error(self) -> None:
        config = _cfg(base_url="http://localhost:11434", default_model="m")
        backend = OllamaBackend(config=config)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.headers = {}
        error = MagicMock()
        error.response = mock_resp
        error.__class__.__name__ = "HTTPStatusError"

        with pytest.raises(LLMAPIError):
            backend._handle_http_error(error, "m")


class TestOllamaChat:
    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    @patch("apps.core.llm.backends.ollama.build_ollama_chat_payload")
    @patch("apps.core.llm.backends.ollama.parse_ollama_chat_response")
    def test_chat_success(self, mock_parse, mock_build, mock_get_client) -> None:
        config = _cfg(base_url="http://localhost:11434", default_model="m", timeout=10)
        backend = OllamaBackend(config=config)

        mock_build.return_value = {"model": "m", "messages": []}
        mock_parse.return_value = {
            "message": {"content": "Hi"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        result = backend.chat([{"role": "user", "content": "Hello"}])
        assert result.content == "Hi"
        assert result.backend == "ollama"

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    @patch("apps.core.llm.backends.ollama.build_ollama_chat_payload")
    def test_chat_with_think(self, mock_build, mock_get_client) -> None:
        config = _cfg(base_url="http://localhost:11434", default_model="m", timeout=10)
        backend = OllamaBackend(config=config)

        mock_build.return_value = {"model": "m", "messages": [], "think": True}

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "OK"}, "prompt_eval_count": 1, "eval_count": 1}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        with patch("apps.core.llm.backends.ollama.parse_ollama_chat_response") as mock_parse:
            mock_parse.return_value = {
                "message": {"content": "OK"},
                "prompt_eval_count": 1,
                "eval_count": 1,
            }
            result = backend.chat([{"role": "user", "content": "Hi"}], think=True)
            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args[1]
            assert call_kwargs["think"] is True


class TestOllamaAvailability:
    def test_disabled_in_config(self) -> None:
        config = _cfg(enabled=False)
        backend = OllamaBackend(config=config)
        assert backend.is_available() is False

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_available_when_probe_succeeds(self, mock_get_client) -> None:
        config = _cfg(base_url="http://localhost:11434")
        backend = OllamaBackend(config=config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        assert backend.is_available() is True

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_not_available_when_probe_fails(self, mock_get_client) -> None:
        config = _cfg(base_url="http://localhost:11434")
        backend = OllamaBackend(config=config)

        mock_get_client.side_effect = Exception("Connection refused")
        assert backend.is_available() is False

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_availability_cached(self, mock_get_client) -> None:
        config = _cfg(base_url="http://localhost:11434")
        backend = OllamaBackend(config=config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        # First call
        backend.is_available()
        # Second call should use cache
        backend.is_available()
        # Only one probe request
        assert mock_client.get.call_count == 1


class TestOllamaEmbed:
    def test_empty_texts(self) -> None:
        config = _cfg(base_url="http://localhost:11434", default_model="m")
        backend = OllamaBackend(config=config)
        assert backend.embed_texts([]) == []

    def test_get_default_model(self) -> None:
        config = _cfg(default_model="llama3")
        backend = OllamaBackend(config=config)
        assert backend.get_default_model() == "llama3"

    def test_get_default_embedding_model(self) -> None:
        config = _cfg(embedding_model="nomic-embed")
        backend = OllamaBackend(config=config)
        assert backend.get_default_embedding_model() == "nomic-embed"
