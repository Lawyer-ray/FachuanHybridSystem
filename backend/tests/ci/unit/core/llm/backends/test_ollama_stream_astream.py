"""Coverage tests for ollama backend: stream, astream, chat_with_options, embed_texts."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

import httpx
import pytest

from apps.core.llm.backends.base import LLMStreamChunk
from apps.core.llm.exceptions import LLMAPIError, LLMNetworkError, LLMTimeoutError


class TestOllamaStream:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_stream_success(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        lines = [
            json.dumps({"message": {"content": "Hello "}, "done": False}),
            json.dumps({"message": {"content": "World"}, "done": False}),
            json.dumps({"done": True, "prompt_eval_count": 10, "eval_count": 5}),
        ]

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.stream.return_value = mock_resp
            mock_client.return_value = mock_http

            chunks = list(backend.stream([{"role": "user", "content": "Hi"}]))
            assert len(chunks) >= 2
            content_chunks = [c for c in chunks if c.content]
            assert any("Hello" in c.content for c in content_chunks)

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_stream_timeout_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.stream.return_value.__enter__ = MagicMock(side_effect=httpx.TimeoutException("timeout"))
            mock_http.stream.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_http

            with pytest.raises(LLMTimeoutError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_stream_connect_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.stream.return_value.__enter__ = MagicMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            mock_http.stream.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_http

            with pytest.raises(LLMNetworkError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_stream_generic_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.stream.return_value.__enter__ = MagicMock(
                side_effect=RuntimeError("unexpected")
            )
            mock_http.stream.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_http

            with pytest.raises(LLMAPIError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_stream_empty_lines_skipped(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        lines = [
            "",
            json.dumps({"message": {"content": "Hi"}, "done": False}),
            json.dumps({"done": True, "prompt_eval_count": 1, "eval_count": 1}),
        ]

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.stream.return_value = mock_resp
            mock_client.return_value = mock_http

            chunks = list(backend.stream([{"role": "user", "content": "Hi"}]))
            content_chunks = [c for c in chunks if c.content]
            assert len(content_chunks) == 1


class TestOllamaAstream:
    def test_astream_success(self):
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            lines = [
                json.dumps({"message": {"content": "Hi"}, "done": False}),
                json.dumps({"done": True, "prompt_eval_count": 1, "eval_count": 1}),
            ]

            async def mock_aiter_lines():
                for line in lines:
                    yield line

            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.aiter_lines = mock_aiter_lines

            # Create an async context manager mock
            class MockAsyncContextManager:
                async def __aenter__(self):
                    return mock_resp
                async def __aexit__(self, *args):
                    pass

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = MagicMock()
                mock_http.stream.return_value = MockAsyncContextManager()
                mock_client.return_value = mock_http

                async def run():
                    chunks = []
                    async for chunk in backend.astream([{"role": "user", "content": "Hi"}]):
                        chunks.append(chunk)
                    return chunks

                chunks = asyncio.run(run())
                assert len(chunks) >= 1

    def test_astream_timeout_error(self):
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = MagicMock()

                class FailingAsyncContext:
                    async def __aenter__(self):
                        raise httpx.TimeoutException("timeout")
                    async def __aexit__(self, *args):
                        pass

                mock_http.stream.return_value = FailingAsyncContext()
                mock_client.return_value = mock_http

                async def run():
                    async for _ in backend.astream([{"role": "user", "content": "Hi"}]):
                        pass

                with pytest.raises(LLMTimeoutError):
                    asyncio.run(run())

    def test_astream_generic_error(self):
        import asyncio
        from apps.core.llm.backends.ollama import OllamaBackend

        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_model.return_value = "llama3"
            mock_config.get_ollama_timeout.return_value = 30
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            backend = OllamaBackend()

            with patch("apps.core.llm.backends.ollama.get_async_http_client") as mock_client:
                mock_http = MagicMock()

                class FailingAsyncContext:
                    async def __aenter__(self):
                        raise RuntimeError("unexpected")
                    async def __aexit__(self, *args):
                        pass

                mock_http.stream.return_value = FailingAsyncContext()
                mock_client.return_value = mock_http

                async def run():
                    async for _ in backend.astream([{"role": "user", "content": "Hi"}]):
                        pass

                with pytest.raises(LLMAPIError):
                    asyncio.run(run())


class TestOllamaChatWithOptions:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_success(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
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

            result = backend.chat_with_options(
                messages=[{"role": "user", "content": "Hi"}],
                options={"num_predict": 100},
                timeout=60,
            )
            assert result.content == "OK"

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_with_think(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "qwq"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "", "thinking": "thinking..."},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            result = backend.chat_with_options(
                messages=[{"role": "user", "content": "Hi"}],
                think=True,
            )
            assert result.content == "thinking..."

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_generic_error(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.side_effect = RuntimeError("unexpected")
            mock_client.return_value = mock_http

            with pytest.raises(LLMAPIError):
                backend.chat_with_options(
                    messages=[{"role": "user", "content": "Hi"}],
                )


class TestOllamaEmbedTexts:
    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_success(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            result = backend.embed_texts(["text1", "text2"])
            assert len(result) == 2
            assert result[0] == [0.1, 0.2]

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_invalid_response_format(self, mock_config):
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embeddings": "not_a_list"}

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http

            with pytest.raises(LLMAPIError, match="格式异常"):
                backend.embed_texts(["text1"])

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_legacy_fallback_non_404_error(self, mock_config):
        """When modern endpoint returns non-404, it should be raised directly."""
        from apps.core.llm.backends.ollama import OllamaBackend

        mock_config.get_ollama_model.return_value = "llama3"
        mock_config.get_ollama_timeout.return_value = 30
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        backend = OllamaBackend()

        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.text = "Internal Server Error"
        error_resp.headers = {}

        mock_post = MagicMock()
        mock_post.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=error_resp
        )

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mock_client:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_post
            mock_client.return_value = mock_http

            with pytest.raises(LLMAPIError):
                backend.embed_texts(["text1"])

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_connect_error(self, mock_config):
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
                backend.embed_texts(["text1"])

    @patch("apps.core.llm.backends.ollama.LLMConfig")
    def test_timeout_error(self, mock_config):
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
                backend.embed_texts(["text1"])
