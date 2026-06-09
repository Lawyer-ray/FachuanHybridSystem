"""ollama backend 补充覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock
from typing import Any

import pytest
import httpx

from apps.core.llm.backends.base import LLMResponse, LLMStreamChunk
from apps.core.llm.exceptions import LLMAPIError, LLMTimeoutError, LLMNetworkError


# ── _build_llm_response ──────────────────────────────────────────

class TestBuildLLMResponse:
    def test_basic_response(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {
            "message": {"content": "Hello!", "role": "assistant"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        result = backend._build_llm_response(data, "llama3", 100.0)
        assert result.content == "Hello!"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.total_tokens == 15
        assert result.backend == "ollama"

    def test_thinking_fallback(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {
            "message": {"content": "", "thinking": "Let me think..."},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        result = backend._build_llm_response(data, "qwq", 100.0)
        assert result.content == "Let me think..."

    def test_empty_content(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {
            "message": {"content": ""},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        result = backend._build_llm_response(data, "llama3", 100.0)
        assert result.content == ""

    def test_no_message_key(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        data = {"prompt_eval_count": 10, "eval_count": 5}
        result = backend._build_llm_response(data, "llama3", 100.0)
        assert result.content == ""


# ── _build_options ────────────────────────────────────────────────

class TestBuildOptions:
    def test_default_temperature(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.7)
        assert options is None or "temperature" not in options

    def test_custom_temperature(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.3)
        assert options is not None
        assert options["temperature"] == 0.3

    def test_max_tokens_mapped(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.7, max_tokens=100)
        assert options is not None
        assert options["num_predict"] == 100

    def test_num_predict_takes_priority(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.7, max_tokens=100, num_predict=200)
        assert options is not None
        assert options["num_predict"] == 200

    def test_extra_ollama_options(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.7, top_k=40, top_p=0.9)
        assert options is not None
        assert options["top_k"] == 40
        assert options["top_p"] == 0.9

    def test_seed_option(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.7, seed=42)
        assert options is not None
        assert options["seed"] == 42

    def test_no_extra_params_returns_none(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        options = backend._build_options(temperature=0.7)
        assert options is None or len(options) == 0


# ── _build_api_url ────────────────────────────────────────────────

class TestBuildApiUrl:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_default_url(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()
        url = backend._build_api_url()
        assert "/api/chat" in url

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_custom_base_url(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_base_url.return_value = "http://custom:8080"
        backend = OllamaBackend()
        url = backend._build_api_url()
        assert "custom:8080" in url
        assert url.endswith("/api/chat")


# ── _handle_timeout_error ─────────────────────────────────────────

class TestHandleTimeoutError:
    def test_raises_timeout(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        error = httpx.TimeoutException("timeout")
        with pytest.raises(LLMTimeoutError):
            backend._handle_timeout_error(error, 30.0)


# ── _handle_connect_error ─────────────────────────────────────────

class TestHandleConnectError:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_raises_network_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()
        error = httpx.ConnectError("connection refused")
        with pytest.raises(LLMNetworkError):
            backend._handle_connect_error(error)


# ── _handle_http_error ────────────────────────────────────────────

class TestHandleHttpError:
    def test_raises_api_error(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        error = httpx.HTTPStatusError("error", request=MagicMock(), response=mock_response)
        with pytest.raises(LLMAPIError):
            backend._handle_http_error(error, "llama3")


# ── Properties (mocked) ──────────────────────────────────────────

class TestOllamaProperties:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_default_model(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        backend = OllamaBackend()
        assert backend.default_model == "llama3"

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_timeout(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_timeout.return_value = 120
        backend = OllamaBackend()
        assert backend.timeout == 120

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_base_url(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()
        assert backend.base_url == "http://localhost:11434"


# ── Backend name ──────────────────────────────────────────────────

class TestBackendName:
    def test_name(self):
        from apps.core.llm.backends.ollama import OllamaBackend

        backend = OllamaBackend()
        assert backend.BACKEND_NAME == "ollama"


# ── chat method ───────────────────────────────────────────────────

class TestOllamaChat:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_chat_success(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Hello!", "role": "assistant"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            result = backend.chat([{"role": "user", "content": "Hi"}])
            assert result.content == "Hello!"

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_chat_with_think_param(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "qwq"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "", "thinking": "Deep thought"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            result = backend.chat([{"role": "user", "content": "Hi"}], think=True)
            assert result.content == "Deep thought"

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_chat_timeout_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.TimeoutException("timeout")
            mock_client.return_value = mock_http

            with pytest.raises(LLMTimeoutError):
                backend.chat([{"role": "user", "content": "Hi"}])

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_chat_connect_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.ConnectError("connection refused")
            mock_client.return_value = mock_http

            with pytest.raises(LLMNetworkError):
                backend.chat([{"role": "user", "content": "Hi"}])

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_chat_generic_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.side_effect = RuntimeError("unexpected error")
            mock_client.return_value = mock_http

            with pytest.raises(LLMAPIError):
                backend.chat([{"role": "user", "content": "Hi"}])

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_chat_with_custom_options(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "OK"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            result = backend.chat(
                [{"role": "user", "content": "Hi"}],
                num_predict=100,
                top_k=40,
                timeout=60,
            )
            assert result.content == "OK"


# ── async achat (sync runner) ─────────────────────────────────────

class TestOllamaAchat:
    def test_achat_success(self):
        """Test achat via asyncio.run (since -p no:asyncio is used)."""
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "Async Hello!", "role": "assistant"},
                "prompt_eval_count": 10,
                "eval_count": 5,
            }

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = AsyncMock()
                mock_http.post.return_value = mock_response
                mock_client.return_value = mock_http

                result = asyncio.run(backend.achat([{"role": "user", "content": "Hi"}]))
                assert result.content == "Async Hello!"

    def test_achat_timeout_error(self):
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = AsyncMock()
                mock_http.post.side_effect = httpx.TimeoutException("timeout")
                mock_client.return_value = mock_http

                with pytest.raises(LLMTimeoutError):
                    asyncio.run(backend.achat([{"role": "user", "content": "Hi"}]))

    def test_achat_connect_error(self):
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = AsyncMock()
                mock_http.post.side_effect = httpx.ConnectError("connection refused")
                mock_client.return_value = mock_http

                with pytest.raises(LLMNetworkError):
                    asyncio.run(backend.achat([{"role": "user", "content": "Hi"}]))

    def test_achat_generic_error(self):
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = AsyncMock()
                mock_http.post.side_effect = RuntimeError("unexpected error")
                mock_client.return_value = mock_http

                with pytest.raises(LLMAPIError):
                    asyncio.run(backend.achat([{"role": "user", "content": "Hi"}]))
