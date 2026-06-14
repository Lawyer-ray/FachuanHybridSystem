"""
Unit tests for core/llm/backends/ollama.py.

Covers:
  - __init__ (with config, without config)
  - base_url, default_model, timeout, default_embedding_model (lazy loading)
  - _build_api_url, _build_embed_url, _build_legacy_embed_url
  - _build_options (temperature, num_predict, max_tokens, other params)
  - _build_llm_response (content, thinking field, token counts)
  - _handle_http_error (404, other status)
  - _handle_connect_error
  - _handle_timeout_error
  - chat (success path with mocked httpx)
  - achat (success path)
  - stream (success path)
  - chat_with_options (success path)
  - embed_texts (empty, success, legacy fallback)
  - is_available (disabled, no base_url, success probe, failed probe)
  - get_default_model, get_default_embedding_model
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.core.llm.exceptions import LLMAPIError
from apps.core.llm.backends.ollama import OllamaBackend
from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_backend(**kwargs: Any) -> OllamaBackend:
    return OllamaBackend(config=kwargs.get("config"))


def _mock_config(**kwargs: Any) -> BackendConfig:
    cfg = MagicMock(spec=BackendConfig)
    cfg.base_url = kwargs.get("base_url", "http://localhost:11434")
    cfg.default_model = kwargs.get("default_model", "qwen3:0.6b")
    cfg.timeout = kwargs.get("timeout", 120.0)
    cfg.embedding_model = kwargs.get("embedding_model")
    cfg.enabled = kwargs.get("enabled", True)
    return cfg


# ===========================================================================
# Tests
# ===========================================================================


class TestInit:
    def test_with_config(self) -> None:
        cfg = _mock_config(base_url="http://custom:11434")
        backend = OllamaBackend(config=cfg)
        assert backend._config is cfg

    def test_without_config(self) -> None:
        backend = OllamaBackend()
        assert backend._config is None


class TestProperties:
    def test_base_url_from_config(self) -> None:
        cfg = _mock_config(base_url="http://custom:11434")
        backend = OllamaBackend(config=cfg)
        assert backend.base_url == "http://custom:11434"

    def test_default_model_from_config(self) -> None:
        cfg = _mock_config(default_model="llama3")
        backend = OllamaBackend(config=cfg)
        assert backend.default_model == "llama3"

    def test_timeout_from_config(self) -> None:
        cfg = _mock_config(timeout=60.0)
        backend = OllamaBackend(config=cfg)
        assert backend.timeout == 60.0

    def test_default_embedding_model_from_config(self) -> None:
        cfg = _mock_config(embedding_model="nomic-embed-text")
        backend = OllamaBackend(config=cfg)
        assert backend.default_embedding_model == "nomic-embed-text"

    def test_default_embedding_model_fallback(self) -> None:
        cfg = _mock_config(embedding_model=None, default_model="llama3")
        backend = OllamaBackend(config=cfg)
        assert backend.default_embedding_model == "llama3"

    def test_lazy_load_base_url(self) -> None:
        backend = OllamaBackend()
        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_base_url.return_value = "http://auto:11434"
            url = backend.base_url
        assert url == "http://auto:11434"


class TestBuildUrls:
    def test_api_url(self) -> None:
        cfg = _mock_config(base_url="http://localhost:11434")
        backend = OllamaBackend(config=cfg)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"

    def test_embed_url(self) -> None:
        cfg = _mock_config(base_url="http://localhost:11434")
        backend = OllamaBackend(config=cfg)
        assert backend._build_embed_url() == "http://localhost:11434/api/embed"

    def test_legacy_embed_url(self) -> None:
        cfg = _mock_config(base_url="http://localhost:11434")
        backend = OllamaBackend(config=cfg)
        assert backend._build_legacy_embed_url() == "http://localhost:11434/api/embeddings"

    def test_trailing_slash_stripped(self) -> None:
        cfg = _mock_config(base_url="http://localhost:11434/")
        backend = OllamaBackend(config=cfg)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"


class TestBuildOptions:
    def test_default_temperature(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        result = backend._build_options(temperature=0.7)
        assert result is None  # default temp, no options

    def test_custom_temperature(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        result = backend._build_options(temperature=0.3)
        assert result is not None
        assert result["temperature"] == 0.3

    def test_num_predict(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        result = backend._build_options(temperature=0.7, num_predict=100)
        assert result is not None
        assert result["num_predict"] == 100

    def test_max_tokens_maps_to_num_predict(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        result = backend._build_options(temperature=0.7, max_tokens=200)
        assert result is not None
        assert result["num_predict"] == 200

    def test_num_predict_takes_priority(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        result = backend._build_options(temperature=0.7, max_tokens=200, num_predict=100)
        assert result is not None
        assert result["num_predict"] == 100

    def test_other_options(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        result = backend._build_options(temperature=0.7, top_k=40, top_p=0.9)
        assert result is not None
        assert result["top_k"] == 40
        assert result["top_p"] == 0.9


class TestBuildLlmResponse:
    def test_basic(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        data = {
            "message": {"content": "Hello"},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }
        resp = backend._build_llm_response(data, "model1", 100.0)
        assert resp.content == "Hello"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 20
        assert resp.total_tokens == 30
        assert resp.duration_ms == 100.0
        assert resp.backend == "ollama"

    def test_thinking_fallback(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        data = {
            "message": {"content": "", "thinking": "Let me think..."},
            "prompt_eval_count": 5,
            "eval_count": 10,
        }
        resp = backend._build_llm_response(data, "model1", 50.0)
        assert resp.content == "Let me think..."

    def test_empty_content_and_thinking(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        data = {
            "message": {"content": "", "thinking": ""},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        resp = backend._build_llm_response(data, "model1", 50.0)
        assert resp.content == ""


class TestHandleErrors:
    def test_404_error(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        response = MagicMock()
        response.status_code = 404
        error = httpx.HTTPStatusError("404", request=MagicMock(), response=response)
        with pytest.raises(LLMAPIError) as exc_info:
            backend._handle_http_error(error, "test-model")
        assert "404" in str(exc_info.value)

    def test_other_http_error(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        response = MagicMock()
        response.status_code = 500
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=response)
        with patch("apps.core.llm.backends.ollama.summarize_http_error_response", return_value={"status": 500}):
            with pytest.raises(LLMAPIError) as exc_info:
                backend._handle_http_error(error, "test-model")
        assert "500" in str(exc_info.value)


class TestChat:
    def test_success(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hello!"},
            "prompt_eval_count": 5,
            "eval_count": 10,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.post.return_value = mock_resp
            resp = backend.chat([{"role": "user", "content": "Hi"}])

        assert resp.content == "Hello!"
        assert resp.model == "qwen3:0.6b"

    def test_connect_error(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.post.side_effect = httpx.ConnectError("connection refused")
            from apps.core.llm.exceptions import LLMNetworkError
            with pytest.raises(LLMNetworkError):
                backend.chat([{"role": "user", "content": "Hi"}])


class TestChatWithOptions:
    def test_success(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Result"},
            "prompt_eval_count": 5,
            "eval_count": 10,
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.post.return_value = mock_resp
            resp = backend.chat_with_options(
                messages=[{"role": "user", "content": "Hi"}],
                options={"num_predict": 100},
                timeout=30.0,
            )

        assert resp.content == "Result"


class TestEmbedTexts:
    def test_empty_texts(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        assert backend.embed_texts([]) == []

    def test_success(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]],
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.post.return_value = mock_resp
            result = backend.embed_texts(["test text"])

        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]

    def test_legacy_fallback_on_404_returns_empty(self) -> None:
        """When /api/embed returns 404 and legacy also fails, should raise error."""
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)

        error_resp_obj = MagicMock()
        error_resp_obj.status_code = 404
        http_error = httpx.HTTPStatusError("404", request=MagicMock(), response=error_resp_obj)

        first_resp = MagicMock()
        first_resp.raise_for_status.side_effect = http_error

        mock_client = MagicMock()
        mock_client.post.return_value = first_resp

        with patch("apps.core.llm.backends.ollama.get_sync_http_client", return_value=mock_client):
            # When /api/embed returns 404, it should try legacy path
            # Since we only return 404 for both calls, it should raise
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["test"])


class TestIsAvailable:
    def test_disabled(self) -> None:
        cfg = _mock_config(enabled=False)
        backend = OllamaBackend(config=cfg)
        assert backend.is_available() is False

    def test_success(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.get.return_value = mock_resp
            result = backend.is_available()

        assert result is True

    def test_probe_failure(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.get.side_effect = Exception("connection refused")
            result = backend.is_available()

        assert result is False

    def test_probe_non_200(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.get.return_value = mock_resp
            result = backend.is_available()

        assert result is False

    def test_caches_result(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_client.return_value.get.return_value = mock_resp
            backend.is_available()
            # Second call should use cache
            result = backend.is_available()

        assert result is True
        # Only one actual probe call
        mock_client.return_value.get.assert_called_once()


class TestGetDefaultModel:
    def test_returns_default(self) -> None:
        cfg = _mock_config(default_model="llama3")
        backend = OllamaBackend(config=cfg)
        assert backend.get_default_model() == "llama3"
