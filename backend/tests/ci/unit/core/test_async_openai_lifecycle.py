"""Tests for AsyncClient lifecycle in openai_compatible backend.

契约（客户端缓存重构后）：
- AsyncClient 按（事件循环, timeout）缓存复用，不再每次调用后 close
- 同一 backend 连续调用复用同一 client 实例
- 显式 aclose_clients() 用于清理缓存的全部客户端
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_config():
    from apps.core.llm.backends.base import BackendConfig

    return BackendConfig(
        name="test",
        enabled=True,
        priority=1,
        default_model="gpt-4",
        base_url="https://api.test/v1",
        api_key="sk-test",
        timeout=30,
        embedding_model="text-embedding-ada-002",
    )


def _make_config_with_key(api_key: str, base_url: str):
    from apps.core.llm.backends.base import BackendConfig

    return BackendConfig(
        name="test",
        enabled=True,
        priority=1,
        default_model="gpt-4",
        base_url=base_url,
        api_key=api_key,
        timeout=30,
        embedding_model="text-embedding-ada-002",
    )


def _make_backend():
    from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

    return OpenAICompatibleBackend(config=_make_config())


def _make_response():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="hello", reasoning_content=None))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return mock_response


class TestAsyncClientCache:
    """AsyncClient 按（事件循环, timeout）缓存复用。"""

    @pytest.mark.asyncio
    async def test_build_async_client_reuses_cached_instance(self):
        backend = _make_backend()

        with (
            patch("apps.core.llm.backends.openai_compatible.httpx.AsyncHTTPTransport"),
            patch("apps.core.llm.backends.openai_compatible.httpx.AsyncClient") as mock_http,
            patch("apps.core.llm.backends.openai_compatible.openai.AsyncOpenAI") as mock_openai_cls,
        ):
            first = await backend._build_async_client("sk-test", "https://api.test/v1", 30.0)
            second = await backend._build_async_client("sk-test", "https://api.test/v1", 30.0)

        assert first is second
        assert mock_http.call_count == 1
        assert mock_openai_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_different_timeout_gets_separate_client(self):
        backend = _make_backend()

        with (
            patch("apps.core.llm.backends.openai_compatible.httpx.AsyncHTTPTransport"),
            patch("apps.core.llm.backends.openai_compatible.httpx.AsyncClient"),
            patch("apps.core.llm.backends.openai_compatible.openai.AsyncOpenAI") as mock_openai_cls,
        ):
            await backend._build_async_client("sk-test", "https://api.test/v1", 30.0)
            await backend._build_async_client("sk-test", "https://api.test/v1", timeout_seconds=999)

        assert mock_openai_cls.call_count == 2


class TestNoPerCallClose:
    """achat/astream/aembed 不再每次调用后 close 客户端。"""

    @pytest.mark.asyncio
    async def test_achat_does_not_close_client_on_success(self):
        backend = _make_backend()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

        with patch.object(backend, "_build_async_client", return_value=mock_client):
            await backend.achat(messages=[{"role": "user", "content": "hi"}])

        mock_client.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_achat_does_not_close_client_on_error(self):
        backend = _make_backend()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("network error"))

        with patch.object(backend, "_build_async_client", return_value=mock_client):
            with pytest.raises(Exception, match="network error"):
                await backend.achat(messages=[{"role": "user", "content": "hi"}])

        mock_client.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_astream_does_not_close_client_on_error(self):
        backend = _make_backend()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("stream error"))

        with patch.object(backend, "_build_async_client", return_value=mock_client):
            with pytest.raises(Exception, match="stream error"):
                async for _ in backend.astream(messages=[{"role": "user", "content": "hi"}]):
                    pass

        mock_client.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_aembed_does_not_close_client_on_success(self):
        backend = _make_backend()
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])]))

        with patch.object(backend, "_build_async_client", return_value=mock_client):
            await backend.aembed_texts(texts=["a"])

        mock_client.close.assert_not_awaited()


class TestExplicitClose:
    """aclose_clients() 显式清理缓存的客户端。"""

    @pytest.mark.asyncio
    async def test_aclose_clients_closes_and_clears(self):
        backend = _make_backend()
        mock_client = AsyncMock()
        mock_client2 = AsyncMock()
        backend._async_clients[("loop-a", "sk-a", "https://a/v1", 30.0)] = mock_client
        backend._async_clients[("loop-b", "sk-b", "https://b/v1", 30.0)] = mock_client2

        await backend.aclose_clients()

        mock_client.close.assert_awaited_once()
        mock_client2.close.assert_awaited_once()
        assert backend._async_clients == {}

    def test_close_clients_closes_and_clears_sync(self):
        backend = _make_backend()
        mock_client = MagicMock()
        backend._sync_clients[("sk-a", "https://a/v1", 30.0)] = mock_client

        backend.close_clients()

        mock_client.close.assert_called_once()
        assert backend._sync_clients == {}


class TestConfigFingerprintCache:
    """配置（api_key/base_url/timeout）轮换后客户端缓存自动失效。"""

    def test_sync_client_invalidates_on_config_change(self):
        backend = _make_backend()

        with (
            patch("apps.core.llm.backends.openai_compatible.httpx.HTTPTransport"),
            patch("apps.core.llm.backends.openai_compatible.httpx.Client"),
            patch("apps.core.llm.backends.openai_compatible.openai.OpenAI") as mock_openai_cls,
        ):
            backend._build_sync_client("sk-test", "https://api.test/v1", 30.0)

            backend._config = _make_config_with_key("sk-new", "https://api.test/v2")
            backend._api_key = None
            backend._base_url = None

            backend._build_sync_client("sk-new", "https://api.test/v2", 30.0)

        assert mock_openai_cls.call_count == 2  # 配置变化后重建客户端
        assert len(backend._sync_clients) == 1  # 旧配置客户端被清掉
        assert ("sk-new", "https://api.test/v2", 30.0) in backend._sync_clients

    @pytest.mark.asyncio
    async def test_async_client_invalidates_on_config_change(self):
        backend = _make_backend()

        with (
            patch("apps.core.llm.backends.openai_compatible.httpx.AsyncHTTPTransport"),
            patch("apps.core.llm.backends.openai_compatible.httpx.AsyncClient"),
            patch("apps.core.llm.backends.openai_compatible.openai.AsyncOpenAI") as mock_openai_cls,
        ):
            await backend._build_async_client("sk-test", "https://api.test/v1", 30.0)
            await backend._build_async_client("sk-test", "https://api.test/v1", 30.0)  # 同配置命中缓存，不重建

            backend._config = _make_config_with_key("sk-new", "https://api.test/v2")

            await backend._build_async_client("sk-new", "https://api.test/v2", 30.0)

        assert mock_openai_cls.call_count == 2  # 缓存命中后仅配置变化触发一次重建
        assert len(backend._async_clients) == 1
        assert any(k[1] == "sk-new" and k[2] == "https://api.test/v2" for k in backend._async_clients)
