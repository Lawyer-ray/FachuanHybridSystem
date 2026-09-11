"""openai_compatible 后端多平台 / 多 Key / 并发上限 / 失败切换测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.backends.base import BackendConfig, OpenAIProviderConfig
from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend, _KeyPool, _pick_provider
from apps.core.llm.exceptions import LLMAuthenticationError


def _provider(**kwargs: Any) -> OpenAIProviderConfig:
    defaults = {
        "name": "law",
        "base_url": "http://law/v1",
        "api_keys": ["k1", "k2"],  # pragma: allowlist secret
        "default_model": "kimi26",
        "extra_models": [],
        "concurrency_per_key": 0,
    }
    defaults.update(kwargs)
    return OpenAIProviderConfig(**defaults)


def _cfg(providers: list[OpenAIProviderConfig], **kwargs: Any) -> BackendConfig:
    defaults = {
        "name": "oai",
        "enabled": True,
        "priority": 1,
        "default_model": "kimi26",
        "api_key": "",
        "base_url": "",
    }
    defaults.update(kwargs)
    defaults["providers"] = providers
    return BackendConfig(**defaults)


def _mock_response(content: str = "OK") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    return response


# ── 平台路由 ─────────────────────────────────────────────────────


class TestPickProvider:
    def test_match_model_to_platform(self) -> None:
        providers = [
            _provider(name="xiaomi", base_url="http://xm/v1", default_model="mimo-v1"),
            _provider(name="law", base_url="http://law/v1", default_model="kimi26", priority=1),
        ]
        assert _pick_provider(providers, "mimo-v1").name == "xiaomi"
        assert _pick_provider(providers, "kimi26").name == "law"

    def test_unmatched_model_uses_highest_priority(self) -> None:
        providers = [
            _provider(name="xiaomi", base_url="http://xm/v1", default_model="mimo-v1", priority=5),
            _provider(name="law", base_url="http://law/v1", default_model="kimi26", priority=1),
        ]
        assert _pick_provider(providers, "unknown-model").name == "law"

    def test_disabled_platform_excluded(self) -> None:
        providers = [_provider(name="off", base_url="http://x/v1", default_model="m", enabled=False)]
        assert _pick_provider(providers, "m") is None

    def test_resolve_provider_from_config(self) -> None:
        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))
        provider = backend._resolve_provider("kimi26")
        assert provider is not None
        assert provider.name == "law"
        assert provider.base_url == "http://law/v1"


# ── Key 槽位管理 ─────────────────────────────────────────────────


class TestKeyPool:
    def test_round_robin(self) -> None:
        pool = _KeyPool(["k1", "k2", "k3"])  # pragma: allowlist secret
        assert pool.acquire() == 0
        assert pool.acquire() == 1
        assert pool.acquire() == 2
        assert pool.acquire() == 0

    def test_concurrency_limit_graceful_overflow(self) -> None:
        pool = _KeyPool(["k1", "k2"], concurrency_per_key=1)  # pragma: allowlist secret
        assert pool.acquire() == 0
        assert pool.acquire() == 1
        # 全部处于并发上限：超限保底仍分配，保证请求可用
        assert pool.acquire() is not None
        pool.release(0, success=True)
        pool.release(1, success=True)

    def test_failed_key_enters_cooldown(self) -> None:
        pool = _KeyPool(["k1", "k2"])  # pragma: allowlist secret
        assert pool.acquire() == 0
        pool.release(0, success=False)
        assert pool.acquire() == 1  # k1 冷却中，跳过
        pool.release(1, success=True)


# ── 多 Key 调用（sync） ──────────────────────────────────────────


class TestChatWithProviders:
    def test_chat_uses_provider_endpoint(self) -> None:
        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = _mock_response("Hello")
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "Hi"}], model="kimi26")
            assert result.content == "Hello"
            assert mock_build.call_args.kwargs["api_key"] in ("k1", "k2")
            assert mock_build.call_args.kwargs["base_url"] == "http://law/v1"

    def test_chat_rotates_key_on_failure(self) -> None:
        import openai

        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))
        keys_used: list[str] = []

        def fake_build(api_key: str, base_url: str, timeout_seconds: float) -> MagicMock:
            keys_used.append(api_key)
            mock_client = MagicMock()
            if len(keys_used) == 1:
                mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
                    message="bad key",
                    response=MagicMock(status_code=401, headers={}),
                    body=None,
                )
            else:
                mock_client.chat.completions.create.return_value = _mock_response("OK")
            return mock_client

        with patch.object(backend, "_build_sync_client", side_effect=fake_build):
            result = backend.chat([{"role": "user", "content": "Hi"}], model="kimi26")
            assert result.content == "OK"
            assert keys_used == ["k1", "k2"]  # 第一个 Key 失败后切换到第二个

    def test_chat_all_keys_fail_raises(self) -> None:
        import openai

        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))

        def fake_build(api_key: str, base_url: str, timeout_seconds: float) -> MagicMock:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
                message="bad key",
                response=MagicMock(status_code=401, headers={}),
                body=None,
            )
            return mock_client

        with patch.object(backend, "_build_sync_client", side_effect=fake_build):
            with pytest.raises(LLMAuthenticationError):
                backend.chat([{"role": "user", "content": "Hi"}], model="kimi26")

    def test_provider_without_keys_falls_back_to_legacy_single_call(self) -> None:
        backend = OpenAICompatibleBackend(config=_cfg([_provider(api_keys=[])]))

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = _mock_response("NoAuth")
            mock_build.return_value = mock_client

            result = backend.chat([{"role": "user", "content": "Hi"}], model="kimi26")
            assert result.content == "NoAuth"
            assert mock_build.call_args.kwargs["base_url"] == "http://law/v1"
            assert mock_build.call_args.kwargs["api_key"] == ""  # 本地 vLLM 无需鉴权


# ── 多 Key 调用（async） ─────────────────────────────────────────


class TestAchatWithProviders:
    @pytest.mark.asyncio
    async def test_achat_rotates_key_on_failure(self) -> None:
        import openai

        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))
        keys_used: list[str] = []

        async def fake_build(api_key: str, base_url: str, timeout_seconds: float) -> AsyncMock:
            keys_used.append(api_key)
            mock_client = AsyncMock()
            if len(keys_used) == 1:
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=openai.AuthenticationError(
                        message="bad key",
                        response=MagicMock(status_code=401, headers={}),
                        body=None,
                    )
                )
            else:
                mock_client.chat.completions.create = AsyncMock(return_value=_mock_response("OK"))
            return mock_client

        with patch.object(backend, "_build_async_client", side_effect=fake_build):
            result = await backend.achat([{"role": "user", "content": "Hi"}], model="kimi26")
            assert result.content == "OK"
            assert keys_used == ["k1", "k2"]


# ── 向量化（provider 路由） ──────────────────────────────────────


class TestEmbedWithProviders:
    def test_embed_uses_provider_embedding_model_and_key(self) -> None:
        backend = OpenAICompatibleBackend(config=_cfg([_provider(embedding_model="embed-v3")]))

        mock_response = MagicMock()
        item = MagicMock()
        item.embedding = [0.1, 0.2]
        mock_response.data = [item]

        with patch.object(backend, "_build_sync_client") as mock_build:
            mock_client = MagicMock()
            mock_client.embeddings.create.return_value = mock_response
            mock_build.return_value = mock_client

            vectors = backend.embed_texts(["文本"])
            assert vectors == [[0.1, 0.2]]
            assert mock_build.call_args.kwargs["api_key"] in ("k1", "k2")
            assert mock_build.call_args.kwargs["base_url"] == "http://law/v1"
            assert mock_client.embeddings.create.call_args.kwargs["model"] == "embed-v3"

    def test_embed_without_embedding_model_raises(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        # 平台未配置向量模型：不再回退默认模型，直接报错
        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))
        with pytest.raises(LLMAPIError, match="未配置向量模型"):
            backend.embed_texts(["文本"])

    @pytest.mark.asyncio
    async def test_aembed_without_embedding_model_raises(self) -> None:
        from apps.core.llm.exceptions import LLMAPIError

        backend = OpenAICompatibleBackend(config=_cfg([_provider()]))
        with pytest.raises(LLMAPIError, match="未配置向量模型"):
            await backend.aembed_texts(["文本"])
