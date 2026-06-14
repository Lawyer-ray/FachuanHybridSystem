"""补充覆盖测试: core/llm/backends/openai_compatible.py (35 missing)

覆盖: achat, astream, embed_texts, is_available, _normalize_messages,
_extract_usage, _extract_content 等分支。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMUsage
from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError


def _cfg(**kwargs: object) -> BackendConfig:
    defaults: dict[str, object] = {
        "name": "oai",
        "enabled": True,
        "priority": 1,
        "default_model": "gpt-4o",
    }
    defaults.update(kwargs)
    return BackendConfig(**defaults)  # type: ignore[arg-type]


# ── _normalize_messages ───────────────────────────────────────────


class TestNormalizeMessages:
    def test_normalizes_valid_roles(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        result = backend._normalize_messages(msgs)
        assert result == msgs

    def test_replaces_unknown_role_with_user(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msgs = [{"role": "tool", "content": "data"}]
        result = backend._normalize_messages(msgs)
        assert result[0]["role"] == "user"

    def test_missing_role_defaults_to_user(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msgs = [{"content": "no role"}]
        result = backend._normalize_messages(msgs)
        assert result[0]["role"] == "user"

    def test_missing_content_defaults_to_empty(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msgs = [{"role": "user"}]
        result = backend._normalize_messages(msgs)
        assert result[0]["content"] == ""


# ── _extract_usage ────────────────────────────────────────────────


class TestExtractUsage:
    def test_none_usage(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        result = backend._extract_usage(None)
        assert result == LLMUsage()

    def test_valid_usage(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 20
        usage.total_tokens = 30
        result = backend._extract_usage(usage)
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20
        assert result.total_tokens == 30

    def test_none_token_values(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        usage = MagicMock()
        usage.prompt_tokens = None
        usage.completion_tokens = None
        usage.total_tokens = None
        result = backend._extract_usage(usage)
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0


# ── _extract_content ──────────────────────────────────────────────


class TestExtractContent:
    def test_no_choices(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        resp = MagicMock()
        resp.choices = None
        assert backend._extract_content(resp) == ""

    def test_empty_choices(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        resp = MagicMock()
        resp.choices = []
        assert backend._extract_content(resp) == ""

    def test_message_none(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        choice = MagicMock()
        choice.message = None
        resp = MagicMock()
        resp.choices = [choice]
        assert backend._extract_content(resp) == ""

    def test_content_is_none_fallback_to_reasoning(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msg = MagicMock()
        msg.content = None
        msg.reasoning_content = "I think..."
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        assert backend._extract_content(resp) == "I think..."

    def test_non_string_content_converted(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msg = MagicMock()
        msg.content = 123
        msg.reasoning_content = None
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        assert backend._extract_content(resp) == "123"

    def test_empty_content_no_reasoning(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend()
        msg = MagicMock()
        msg.content = ""
        msg.reasoning_content = ""
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        assert backend._extract_content(resp) == ""


# ── is_available ──────────────────────────────────────────────────


class TestIsAvailable:
    def test_disabled_config(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(enabled=False, api_key="sk-test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)
        assert backend.is_available() is False

    def test_missing_api_key(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key=None)
        backend = OpenAICompatibleBackend(config=config)
        with patch.object(type(backend), "api_key", new_callable=lambda: property(lambda self: "")):
            assert backend.is_available() is False

    def test_missing_model(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_model.return_value = ""
            config = _cfg(api_key="sk-test", default_model="")
            backend = OpenAICompatibleBackend(config=config)
            assert backend.is_available() is False

    @patch("apps.core.llm.backends.openai_compatible.LLMConfig")
    def test_all_configured(self, mock_cfg: MagicMock) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", default_model="gpt-4o", enabled=True)
        backend = OpenAICompatibleBackend(config=config)
        assert backend.is_available() is True


# ── embed_texts ───────────────────────────────────────────────────


class TestEmbedTexts:
    def test_empty_texts_returns_empty(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(config=_cfg())
        assert backend.embed_texts([]) == []

    def test_embed_success(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        item1 = MagicMock()
        item1.embedding = [0.1, 0.2]
        item2 = MagicMock()
        item2.embedding = [0.3, 0.4]
        mock_response.data = [item1, item2]

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = mock_response
            mock_build.return_value = mock_client

            result = backend.embed_texts(["hello", "world"], model="text-embedding-3-small")
            assert len(result) == 2
            assert result[0] == [0.1, 0.2]
            assert result[1] == [0.3, 0.4]

    def test_embed_error(self) -> None:
        import openai

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o", embedding_model="emb")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = openai.AuthenticationError(
                message="bad key", response=MagicMock(status_code=401, headers={}), body=None,
            )
            mock_build.return_value = mock_client
            with pytest.raises(LLMAuthenticationError):
                backend.embed_texts(["hello"])


# ── achat (async) ────────────────────────────────────────────────


class TestAchat:
    @pytest.mark.asyncio
    async def test_achat_success(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello async"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        mock_async_client = AsyncMock()
        mock_async_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(backend, "_build_async_client", new_callable=AsyncMock, return_value=mock_async_client):
            result = await backend.achat([{"role": "user", "content": "Hi"}])
            assert result.content == "Hello async"
            assert result.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_achat_error(self) -> None:
        import httpx

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_async_client = AsyncMock()
        mock_async_client.chat.completions.create = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )

        with patch.object(backend, "_build_async_client", new_callable=AsyncMock, return_value=mock_async_client):
            with pytest.raises(LLMTimeoutError):
                await backend.achat([{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_achat_no_config_uses_async_settings(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        with patch("apps.core.llm.backends.openai_compatible.LLMConfig") as mock_cfg:
            mock_cfg.get_openai_compatible_model_async = AsyncMock(return_value="async-model")
            mock_cfg.get_openai_compatible_timeout_async = AsyncMock(return_value=30)
            mock_cfg.get_openai_compatible_api_key_async = AsyncMock(return_value="sk-async")
            mock_cfg.get_openai_compatible_base_url_async = AsyncMock(return_value="http://async")

            backend = OpenAICompatibleBackend()

            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
            mock_response.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)

            mock_async_client = AsyncMock()
            mock_async_client.chat.completions.create = AsyncMock(return_value=mock_response)

            with patch.object(
                backend, "_build_async_client", new_callable=AsyncMock, return_value=mock_async_client
            ):
                result = await backend.achat([{"role": "user", "content": "test"}])
                assert result.model == "async-model"


# ── astream ───────────────────────────────────────────────────────


class TestAstream:
    @pytest.mark.asyncio
    async def test_astream_yields_chunks(self) -> None:
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content=" async"))]
        chunk2.usage = None

        final_chunk = MagicMock()
        final_chunk.choices = []
        final_chunk.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        async def _aiter():
            for c in [chunk1, chunk2, final_chunk]:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: _aiter()

        mock_async_client = AsyncMock()
        mock_async_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch.object(backend, "_build_async_client", new_callable=AsyncMock, return_value=mock_async_client):
            chunks = []
            async for chunk in backend.astream([{"role": "user", "content": "test"}]):
                chunks.append(chunk)

            content_chunks = [c for c in chunks if c.content]
            assert len(content_chunks) == 2
            assert content_chunks[0].content == "Hello"
            assert content_chunks[1].content == " async"

    @pytest.mark.asyncio
    async def test_astream_error(self) -> None:
        import httpx

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        mock_async_client = AsyncMock()
        mock_async_client.chat.completions.create = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )

        with patch.object(backend, "_build_async_client", new_callable=AsyncMock, return_value=mock_async_client):
            with pytest.raises(LLMNetworkError):
                async for _ in backend.astream([{"role": "user", "content": "test"}]):
                    pass


# ── stream error with httpx ───────────────────────────────────────


class TestStreamHttpxErrors:
    def test_stream_httpx_timeout_error(self) -> None:
        import httpx

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = httpx.TimeoutException("timeout")
            mock_build.return_value = mock_client
            with pytest.raises(LLMTimeoutError):
                list(backend.stream([{"role": "user", "content": "test"}]))

    def test_stream_httpx_connect_error(self) -> None:
        import httpx

        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        config = _cfg(api_key="sk-test", base_url="http://test", default_model="gpt-4o")
        backend = OpenAICompatibleBackend(config=config)

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = httpx.ConnectError("refused")
            mock_build.return_value = mock_client
            with pytest.raises(LLMNetworkError):
                list(backend.stream([{"role": "user", "content": "test"}]))
