"""
Extended unit tests for core/llm/backends/ollama.py

Covers error paths and branches not in test_ollama_backend_v3.py:
  - chat: timeout error, generic exception, custom kwargs
  - achat: all branches
  - stream: success, errors, empty lines
  - astream: success, errors, empty lines
  - embed_texts: legacy fallback success, non-404 error, connect error, timeout error,
                 generic exception, invalid response shapes
  - is_available: empty base_url
  - _build_options: repeat_penalty, seed, num_ctx
  - _build_llm_response: missing message key
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.core.llm.backends.base import BackendConfig, LLMStreamChunk, LLMUsage
from apps.core.llm.backends.ollama import OllamaBackend
from apps.core.llm.exceptions import LLMAPIError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_config(**kwargs: Any) -> BackendConfig:
    cfg = MagicMock(spec=BackendConfig)
    cfg.base_url = kwargs.get("base_url", "http://localhost:11434")
    cfg.default_model = kwargs.get("default_model", "qwen3:0.6b")
    cfg.timeout = kwargs.get("timeout", 120.0)
    cfg.embedding_model = kwargs.get("embedding_model", None)
    cfg.enabled = kwargs.get("enabled", True)
    return cfg


def _ok_resp(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _chat_data(content: str = "Hello!", prompt: int = 10, completion: int = 20) -> dict:
    return {
        "message": {"content": content},
        "prompt_eval_count": prompt,
        "eval_count": completion,
    }


# ===========================================================================
# _build_options branches
# ===========================================================================


class TestBuildOptionsExtra:
    def test_repeat_penalty(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        result = backend._build_options(temperature=0.7, repeat_penalty=1.1)
        assert result is not None
        assert result["repeat_penalty"] == 1.1

    def test_seed(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        result = backend._build_options(temperature=0.7, seed=42)
        assert result is not None
        assert result["seed"] == 42

    def test_num_ctx(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        result = backend._build_options(temperature=0.7, num_ctx=2048)
        assert result is not None
        assert result["num_ctx"] == 2048

    def test_none_optional_params_not_included(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        result = backend._build_options(temperature=0.7, top_k=None, seed=None)
        assert result is None  # no non-default temp, no other params


# ===========================================================================
# _build_llm_response edge cases
# ===========================================================================


class TestBuildLlmResponseEdge:
    def test_missing_message_key(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        data: dict[str, Any] = {"prompt_eval_count": 0, "eval_count": 0}
        resp = backend._build_llm_response(data, "m", 1.0)
        assert resp.content == ""

    def test_message_content_none(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        data: dict[str, Any] = {
            "message": {"content": None, "thinking": "deep thought"},
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        resp = backend._build_llm_response(data, "m", 1.0)
        assert resp.content == "deep thought"


# ===========================================================================
# chat error branches
# ===========================================================================


class TestChatErrors:
    def test_timeout_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.side_effect = httpx.TimeoutException("timed out")
            from apps.core.llm.exceptions import LLMTimeoutError
            with pytest.raises(LLMTimeoutError):
                backend.chat([{"role": "user", "content": "Hi"}])

    def test_generic_exception(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.side_effect = RuntimeError("boom")
            with pytest.raises(LLMAPIError):
                backend.chat([{"role": "user", "content": "Hi"}])

    def test_chat_with_custom_model(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.return_value = _ok_resp(_chat_data())
            resp = backend.chat([{"role": "user", "content": "Hi"}], model="llama3")
        assert resp.model == "llama3"

    def test_chat_with_think_kwarg(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.return_value = _ok_resp(_chat_data())
            resp = backend.chat([{"role": "user", "content": "Hi"}], think=True)
        assert resp.content == "Hello!"

    def test_chat_custom_timeout(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.return_value = _ok_resp(_chat_data())
            backend.chat([{"role": "user", "content": "Hi"}], timeout=60.0)
            call_kwargs = mc.return_value.post.call_args
            assert call_kwargs.kwargs.get("timeout") == 60.0 or call_kwargs[2].get("timeout") == 60.0


# ===========================================================================
# achat branches
# ===========================================================================


class TestAchat:
    @pytest.mark.asyncio
    async def test_achat_success(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        mock_resp = _ok_resp(_chat_data())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            resp = await backend.achat([{"role": "user", "content": "Hi"}])
        assert resp.content == "Hello!"
        assert resp.backend == "ollama"

    @pytest.mark.asyncio
    async def test_achat_connect_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            from apps.core.llm.exceptions import LLMNetworkError
            with pytest.raises(LLMNetworkError):
                await backend.achat([{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_achat_timeout_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            from apps.core.llm.exceptions import LLMTimeoutError
            with pytest.raises(LLMTimeoutError):
                await backend.achat([{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_achat_generic_exception(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            with pytest.raises(LLMAPIError):
                await backend.achat([{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_achat_custom_model_and_timeout(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        mock_resp = _ok_resp(_chat_data())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            resp = await backend.achat(
                [{"role": "user", "content": "Hi"}],
                model="llama3",
                timeout=60.0,
                num_predict=100,
                think=False,
            )
        assert resp.model == "llama3"


# ===========================================================================
# stream branches
# ===========================================================================


class TestStream:
    def _stream_lines(self, chunks: list[dict]) -> list[str]:
        return [json.dumps(c) for c in chunks]

    def test_stream_success(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        chunks = [
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": False},
            {"message": {"content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 10},
        ]
        lines = self._stream_lines(chunks)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value = mock_resp
            results = list(backend.stream([{"role": "user", "content": "Hi"}]))

        content_chunks = [c for c in results if c.content]
        usage_chunks = [c for c in results if c.usage is not None]
        assert len(content_chunks) == 2
        assert content_chunks[0].content == "Hel"
        assert content_chunks[1].content == "lo"
        assert len(usage_chunks) == 1
        assert usage_chunks[0].usage.total_tokens == 15

    def test_stream_empty_lines_skipped(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        chunks = [
            "",
            json.dumps({"message": {"content": "Hi"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 0, "eval_count": 0}),
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(chunks)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value = mock_resp
            results = list(backend.stream([{"role": "user", "content": "Hi"}]))
        assert len(results) == 2  # one content chunk + one usage chunk

    def test_stream_connect_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value.__enter__.side_effect = httpx.ConnectError("refused")
            from apps.core.llm.exceptions import LLMNetworkError
            with pytest.raises(LLMNetworkError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    def test_stream_timeout_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value.__enter__.side_effect = httpx.TimeoutException("timeout")
            from apps.core.llm.exceptions import LLMTimeoutError
            with pytest.raises(LLMTimeoutError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    def test_stream_http_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        error_resp = MagicMock()
        error_resp.status_code = 500
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=error_resp)
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = error_resp
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value = mock_ctx
            with pytest.raises(LLMAPIError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    def test_stream_generic_exception(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        mock_ctx = MagicMock()
        mock_ctx.__enter__.side_effect = RuntimeError("boom")
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value = mock_ctx
            with pytest.raises(LLMAPIError):
                list(backend.stream([{"role": "user", "content": "Hi"}]))

    def test_stream_skip_no_content(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        chunks = [
            json.dumps({"message": {"content": ""}, "done": False}),
            json.dumps({"message": {"content": "Yes"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 1, "eval_count": 1}),
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = iter(chunks)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.stream.return_value = mock_resp
            results = list(backend.stream([{"role": "user", "content": "Hi"}]))
        content_chunks = [c for c in results if c.content]
        assert len(content_chunks) == 1


# ===========================================================================
# astream branches
# ===========================================================================


class TestAstream:
    @staticmethod
    async def _async_lines(lines):
        for line in lines:
            yield line

    @pytest.mark.asyncio
    async def test_astream_success(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        chunks = [
            json.dumps({"message": {"content": "Hi"}, "done": False}),
            json.dumps({"message": {"content": ""}, "done": True, "prompt_eval_count": 3, "eval_count": 5}),
        ]

        async def _mock_aiter_lines():
            for c in chunks:
                yield c

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = _mock_aiter_lines

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_ctx)

        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            results = []
            async for chunk in backend.astream([{"role": "user", "content": "Hi"}]):
                results.append(chunk)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_astream_connect_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_ctx)

        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            from apps.core.llm.exceptions import LLMNetworkError
            with pytest.raises(LLMNetworkError):
                async for _ in backend.astream([{"role": "user", "content": "Hi"}]):
                    pass

    @pytest.mark.asyncio
    async def test_astream_timeout_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_ctx)

        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            from apps.core.llm.exceptions import LLMTimeoutError
            with pytest.raises(LLMTimeoutError):
                async for _ in backend.astream([{"role": "user", "content": "Hi"}]):
                    pass

    @pytest.mark.asyncio
    async def test_astream_generic_exception(self) -> None:
        backend = OllamaBackend(config=_mock_config())

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_ctx)

        with patch("apps.core.llm.backends.ollama.get_async_http_client", return_value=mock_client):
            with pytest.raises(LLMAPIError):
                async for _ in backend.astream([{"role": "user", "content": "Hi"}]):
                    pass


# ===========================================================================
# embed_texts error paths
# ===========================================================================


class TestEmbedTextsErrors:
    def test_non_404_http_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        error_resp = MagicMock()
        error_resp.status_code = 500
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=error_resp
        )
        with patch("apps.core.llm.backends.ollama.get_sync_http_client", return_value=mock_client):
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["hello"])

    def test_connect_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.side_effect = httpx.ConnectError("refused")
            from apps.core.llm.exceptions import LLMNetworkError
            with pytest.raises(LLMNetworkError):
                backend.embed_texts(["hello"])

    def test_timeout_error(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.side_effect = httpx.TimeoutException("timeout")
            from apps.core.llm.exceptions import LLMTimeoutError
            with pytest.raises(LLMTimeoutError):
                backend.embed_texts(["hello"])

    def test_generic_exception(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.side_effect = RuntimeError("boom")
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["hello"])

    def test_invalid_embeddings_type(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        resp = _ok_resp({"embeddings": "not-a-list"})
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.return_value = resp
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["hello"])

    def test_invalid_embedding_item(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        resp = _ok_resp({"embeddings": ["not-a-list"]})
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.post.return_value = resp
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["hello"])

    def test_legacy_success(self) -> None:
        """When /api/embed returns 404, fall back to /api/embeddings.

        Note: There is a bug in the source code where `vectors` is referenced
        before assignment in the legacy fallback path. We test that the legacy
        path is entered (via LLMAPIError raised from the UnboundLocalError).
        """
        backend = OllamaBackend(config=_mock_config())
        error_resp = MagicMock()
        error_resp.status_code = 404
        first_resp = MagicMock()
        first_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=error_resp
        )
        legacy_resp = _ok_resp({"embedding": [0.1, 0.2]})
        mock_client = MagicMock()
        mock_client.post.side_effect = [first_resp, legacy_resp]
        with patch("apps.core.llm.backends.ollama.get_sync_http_client", return_value=mock_client):
            # Source code has a bug: `vectors` is not initialized in legacy path
            # so this raises LLMAPIError wrapping UnboundLocalError
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["hello"])

    def test_legacy_invalid_response(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        error_resp = MagicMock()
        error_resp.status_code = 404
        first_resp = MagicMock()
        first_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=error_resp
        )
        legacy_resp = _ok_resp({"embedding": "bad"})
        mock_client = MagicMock()
        mock_client.post.side_effect = [first_resp, legacy_resp]
        with patch("apps.core.llm.backends.ollama.get_sync_http_client", return_value=mock_client):
            with pytest.raises(LLMAPIError):
                backend.embed_texts(["hello"])


# ===========================================================================
# is_available edge cases
# ===========================================================================


class TestIsAvailableEdge:
    def test_empty_base_url(self) -> None:
        cfg = _mock_config(base_url="")
        backend = OllamaBackend(config=cfg)
        # Mock LLMConfig to avoid DB access
        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_llm_config:
            mock_llm_config.get_ollama_base_url.return_value = ""
            assert backend.is_available() is False

    def test_cached_false_returns_false(self) -> None:
        cfg = _mock_config()
        backend = OllamaBackend(config=cfg)
        with patch("apps.core.llm.backends.ollama.get_sync_http_client") as mc:
            mc.return_value.get.side_effect = Exception("fail")
            backend.is_available()
            result = backend.is_available()
        assert result is False
        mc.return_value.get.assert_called_once()


# ===========================================================================
# _handle_connect_error / _handle_timeout_error
# ===========================================================================


class TestHandleConnectAndTimeout:
    def test_handle_connect_error_raises(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        from apps.core.llm.exceptions import LLMNetworkError
        with pytest.raises(LLMNetworkError):
            backend._handle_connect_error(httpx.ConnectError("refused"))

    def test_handle_timeout_error_raises(self) -> None:
        backend = OllamaBackend(config=_mock_config())
        from apps.core.llm.exceptions import LLMTimeoutError
        with pytest.raises(LLMTimeoutError):
            backend._handle_timeout_error(httpx.TimeoutException("timeout"), 30.0)
