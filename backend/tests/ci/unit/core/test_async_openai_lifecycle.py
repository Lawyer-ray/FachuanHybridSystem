"""Tests for AsyncClient lifecycle in openai_compatible backend.

Validates the P0 fix: AsyncClient.close() is called in finally blocks
for achat(), astream(), and aembed_texts().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAsyncClientCloseOnAchat:
    """Verify async_client.close() is called after achat(), even on error."""

    @pytest.mark.asyncio
    async def test_achat_closes_client_on_success(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
        from apps.core.llm.backends.base import BackendConfig

        config = BackendConfig(
            name="test", enabled=True, priority=1,
            default_model="gpt-4", base_url="https://api.test/v1",
            api_key="sk-test", timeout=30,
            embedding_model="text-embedding-ada-002",
        )
        backend = OpenAICompatibleBackend(config=config)
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="hello", reasoning_content=None))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(backend, '_build_async_client', return_value=mock_client):
            result = await backend.achat(messages=[{"role": "user", "content": "hi"}])

        mock_client.close.assert_awaited_once()
        assert result.content == "hello"

    @pytest.mark.asyncio
    async def test_achat_closes_client_on_error(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
        from apps.core.llm.backends.base import BackendConfig

        config = BackendConfig(
            name="test", enabled=True, priority=1,
            default_model="gpt-4", base_url="https://api.test/v1",
            api_key="sk-test", timeout=30,
            embedding_model="text-embedding-ada-002",
        )
        backend = OpenAICompatibleBackend(config=config)
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("network error")
        )

        with patch.object(backend, '_build_async_client', return_value=mock_client):
            with pytest.raises(Exception, match="network error"):
                await backend.achat(messages=[{"role": "user", "content": "hi"}])

        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_astream_closes_client_on_success(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
        from apps.core.llm.backends.base import BackendConfig

        config = BackendConfig(
            name="test", enabled=True, priority=1,
            default_model="gpt-4", base_url="https://api.test/v1",
            api_key="sk-test", timeout=30,
            embedding_model="text-embedding-ada-002",
        )
        backend = OpenAICompatibleBackend(config=config)
        mock_client = AsyncMock()

        async def fake_stream():
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=MagicMock(content="hello"))]
            chunk.usage = None
            yield chunk

        mock_client.chat.completions.create = AsyncMock(return_value=fake_stream())

        with patch.object(backend, '_build_async_client', return_value=mock_client):
            chunks = []
            async for c in backend.astream(messages=[{"role": "user", "content": "hi"}]):
                chunks.append(c)

        mock_client.close.assert_awaited_once()
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_astream_closes_client_on_error(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
        from apps.core.llm.backends.base import BackendConfig

        config = BackendConfig(
            name="test", enabled=True, priority=1,
            default_model="gpt-4", base_url="https://api.test/v1",
            api_key="sk-test", timeout=30,
            embedding_model="text-embedding-ada-002",
        )
        backend = OpenAICompatibleBackend(config=config)
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("stream error")
        )

        with patch.object(backend, '_build_async_client', return_value=mock_client):
            with pytest.raises(Exception, match="stream error"):
                async for _ in backend.astream(messages=[{"role": "user", "content": "hi"}]):
                    pass

        mock_client.close.assert_awaited_once()
