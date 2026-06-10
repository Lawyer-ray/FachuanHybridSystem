"""Tests for OllamaBackend and ollama_protocol - targeting uncovered branches."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, LLMStreamChunk
from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload, parse_ollama_chat_response
from apps.core.llm.exceptions import LLMAPIError


# ==================== ollama_protocol.py ====================


class TestBuildOllamaChatPayload:
    """Test build_ollama_chat_payload."""

    def test_basic_payload(self):
        messages = [{"role": "user", "content": "hello"}]
        payload = build_ollama_chat_payload(messages=messages, model="qwen3:0.6b")
        assert payload["model"] == "qwen3:0.6b"
        assert payload["messages"] == messages
        assert payload["stream"] is False

    def test_with_options(self):
        payload = build_ollama_chat_payload(
            messages=[], model="qwen3:0.6b", options={"temperature": 0.5}
        )
        assert payload["options"] == {"temperature": 0.5}

    def test_with_think(self):
        payload = build_ollama_chat_payload(
            messages=[], model="qwen3:0.6b", think=True
        )
        assert payload["think"] is True

    def test_no_options_no_think(self):
        payload = build_ollama_chat_payload(messages=[], model="qwen3:0.6b")
        assert "options" not in payload
        assert "think" not in payload

    def test_think_false(self):
        payload = build_ollama_chat_payload(
            messages=[], model="qwen3:0.6b", think=False
        )
        assert payload["think"] is False


class TestParseOllamaChatResponse:
    """Test parse_ollama_chat_response."""

    def test_valid_json(self):
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "hello"}}
        result = parse_ollama_chat_response(resp=resp, model="test")
        assert result == {"message": {"content": "hello"}}

    def test_json_decode_error_with_valid_last_line(self):
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = "some garbage\n{\"message\": {\"content\": \"good\"}}"
        result = parse_ollama_chat_response(resp=resp, model="test")
        assert result["message"]["content"] == "good"

    def test_json_decode_error_no_valid_json_raises(self):
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = "no json here"
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="test")

    def test_json_decode_error_empty_text_raises(self):
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = ""
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="test")

    def test_json_decode_error_multiple_lines_picks_last_with_message(self):
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = (
            '{"status": "processing"}\n'
            '{"message": {"content": "first"}}\n'
            '{"message": {"content": "final"}}'
        )
        result = parse_ollama_chat_response(resp=resp, model="test")
        assert result["message"]["content"] == "final"


# ==================== OllamaBackend ====================


class TestOllamaBackendInit:
    """Test OllamaBackend initialization."""

    def test_default_init(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        assert backend._config is None

    def test_init_with_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://custom:11434",
            timeout=600,
        )
        backend = OllamaBackend(config=config)
        assert backend._config is config


class TestOllamaBackendProperties:
    """Test OllamaBackend property accessors."""

    def test_base_url_from_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://custom:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend.base_url == "http://custom:11434"

    def test_base_url_from_llm_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_base_url.return_value = "http://fromconfig:11434"
            assert backend.base_url == "http://fromconfig:11434"

    def test_default_model_from_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="mistral",
        )
        backend = OllamaBackend(config=config)
        assert backend.default_model == "mistral"

    def test_default_model_from_llm_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            assert backend.default_model == "llama3"

    def test_timeout_from_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", timeout=300,
        )
        backend = OllamaBackend(config=config)
        assert backend.timeout == 300.0

    def test_timeout_from_llm_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_timeout.return_value = 600
            assert backend.timeout == 600.0

    def test_default_embedding_model_from_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", embedding_model="nomic-embed",
        )
        backend = OllamaBackend(config=config)
        assert backend.default_embedding_model == "nomic-embed"

    def test_default_embedding_model_fallback(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        with patch.object(type(backend), 'default_model', new_callable=lambda: property(lambda self: "qwen3:0.6b")):
            assert backend.default_embedding_model == "qwen3:0.6b"


class TestOllamaBackendBuildUrls:
    """Test URL building methods."""

    def test_build_api_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend._build_api_url() == "http://localhost:11434/api/chat"

    def test_build_embed_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend._build_embed_url() == "http://localhost:11434/api/embed"

    def test_build_legacy_embed_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend._build_legacy_embed_url() == "http://localhost:11434/api/embeddings"


class TestOllamaBackendBuildOptions:
    """Test _build_options."""

    def test_default_temperature_no_options(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        result = backend._build_options(temperature=0.7)
        assert result is None

    def test_custom_temperature(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        result = backend._build_options(temperature=0.5)
        assert result is not None
        assert result["temperature"] == 0.5

    def test_with_max_tokens(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        result = backend._build_options(temperature=0.7, max_tokens=100)
        assert result is not None
        assert result["num_predict"] == 100

    def test_num_predict_overrides_max_tokens(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        result = backend._build_options(temperature=0.7, max_tokens=100, num_predict=200)
        assert result["num_predict"] == 200

    def test_ollama_specific_options(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        result = backend._build_options(
            temperature=0.7, top_k=40, top_p=0.9, repeat_penalty=1.1, seed=42, num_ctx=2048
        )
        assert result is not None
        assert result["top_k"] == 40
        assert result["top_p"] == 0.9
        assert result["repeat_penalty"] == 1.1
        assert result["seed"] == 42
        assert result["num_ctx"] == 2048


class TestOllamaBackendBuildLLMResponse:
    """Test _build_llm_response."""

    def test_basic_response(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {
            "message": {"content": "hello world"},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }
        resp = backend._build_llm_response(data, "qwen3:0.6b", 100.0)
        assert resp.content == "hello world"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 20
        assert resp.total_tokens == 30
        assert resp.duration_ms == 100.0
        assert resp.backend == "ollama"

    def test_empty_content_uses_thinking(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {
            "message": {"content": "", "thinking": "deep thoughts"},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        resp = backend._build_llm_response(data, "qwen3:0.6b", 50.0)
        assert resp.content == "deep thoughts"

    def test_no_content_no_thinking(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {
            "message": {},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        resp = backend._build_llm_response(data, "qwen3:0.6b", 50.0)
        assert resp.content == ""


class TestOllamaBackendHandleErrors:
    """Test error handling methods."""

    def test_handle_http_error_404(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend(config=BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://test:11434",
        ))
        resp = MagicMock()
        resp.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=resp)

        with pytest.raises(LLMAPIError) as exc_info:
            backend._handle_http_error(error, "llama3")
        assert "404" in str(exc_info.value)

    def test_handle_http_error_other(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend(config=BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://test:11434",
        ))
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=resp)

        with pytest.raises(LLMAPIError):
            backend._handle_http_error(error, "llama3")

    def test_handle_connect_error(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend(config=BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://test:11434",
        ))
        error = httpx.ConnectError("Connection refused")
        from apps.core.llm.exceptions import LLMNetworkError

        with pytest.raises(LLMNetworkError):
            backend._handle_connect_error(error)

    def test_handle_timeout_error(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend(config=BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://test:11434",
        ))
        error = httpx.TimeoutException("Timeout")
        from apps.core.llm.exceptions import LLMTimeoutError

        with pytest.raises(LLMTimeoutError):
            backend._handle_timeout_error(error, 30.0)


class TestOllamaBackendGetMethods:
    """Test get_default_model and get_default_embedding_model."""

    def test_get_default_model(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3",
        )
        backend = OllamaBackend(config=config)
        assert backend.get_default_model() == "llama3"

    def test_get_default_embedding_model(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", embedding_model="nomic-embed",
        )
        backend = OllamaBackend(config=config)
        assert backend.get_default_embedding_model() == "nomic-embed"


class TestOllamaBackendIsAvailable:
    """Test is_available."""

    def test_disabled_in_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=False, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend.is_available() is False

    def test_no_base_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        backend._base_url = ""
        assert backend.is_available() is False

    def test_cached_result(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        backend._availability_checked = True
        backend._availability_result = True
        assert backend.is_available() is True

    def test_cached_result_false(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        backend._availability_checked = True
        backend._availability_result = False
        assert backend.is_available() is False

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_probe_success(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend.is_available() is True

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_probe_non_200(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend.is_available() is False

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_probe_exception(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        assert backend.is_available() is False


class TestOllamaBackendEmbedTexts:
    """Test embed_texts."""

    def test_empty_texts(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        assert backend.embed_texts([]) == []

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_successful_embed(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        result = backend.embed_texts(["hello"])
        assert result == [[0.1, 0.2, 0.3]]

    @patch("apps.core.llm.backends.ollama.get_sync_http_client")
    def test_embed_invalid_response(self, mock_get_client):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "bad request"}
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        config = BackendConfig(
            name="ollama", enabled=True, priority=2,
            default_model="llama3", base_url="http://localhost:11434",
        )
        backend = OllamaBackend(config=config)
        with pytest.raises(LLMAPIError):
            backend.embed_texts(["hello"])
