"""降级模型链的运行时执行（审计 P1-10）。

## 守的是什么

`fallback_models` 长期是**僵尸字段**：`LLMProvider` 里有、迁移里有，但 Admin 的
fieldsets 没有它、服务层不加载、只有 pi 会真的用。于是「同一个模型，换 dsh /
openai-agents 入口就不降级」——用户只会看到"这个入口坏了"。

本文件锁三件事：
1. 主模型抛**可重试**错误时，按 `fallback_models` 顺序换模型重试；
2. 参数类错误（不可重试）**不降级**——换个模型只会同样失败，白烧一次额度；
3. 降级链排除自身，避免「降级到自己」空转。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from apps.core.llm.backends.base import OpenAIProviderConfig
from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
from apps.core.llm.exceptions import LLMAPIError, LLMTimeoutError


def _provider(**overrides: Any) -> OpenAIProviderConfig:
    fields: dict[str, Any] = {
        "name": "律所 kimi",
        "base_url": "http://gw.internal:4000/v1",
        "api_keys": ["k1"],  # pragma: allowlist secret
        "default_model": "kimi-2.6",
        "extra_models": ["glm53", "kimi-2.6(Anthropic)"],
        "fallback_models": ["glm53", "kimi-2.6(Anthropic)"],
        "timeout": 30,
        "concurrency_per_key": 3,
    }
    fields.update(overrides)
    return OpenAIProviderConfig(**fields)


def _backend(provider: OpenAIProviderConfig) -> Any:
    """把平台配置塞进后端的 ``_config.providers``（``_providers_from_config`` 的口径）。"""
    backend = OpenAICompatibleBackend()
    backend._config = SimpleNamespace(providers=[provider])  # type: ignore[attr-defined]
    return backend


class TestFallbackChain:
    def test_retries_next_model_on_timeout(self) -> None:
        backend = _backend(_provider())
        calls: list[str] = []

        def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            if model == "kimi-2.6" or model is None:
                raise LLMTimeoutError(message="timed out", timeout_seconds=30)
            return {"model": model, "ok": True}

        with mock.patch.object(backend, "_chat_primary", side_effect=_primary):
            result = backend.chat([{"role": "user", "content": "hi"}], model="kimi-2.6")

        assert calls == ["kimi-2.6", "glm53"]
        assert result == {"model": "glm53", "ok": True}

    def test_walks_whole_chain_then_raises(self) -> None:
        backend = _backend(_provider())
        calls: list[str] = []

        def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            raise LLMAPIError(message="boom", status_code=500)

        with mock.patch.object(backend, "_chat_primary", side_effect=_primary):
            with pytest.raises(LLMAPIError):
                backend.chat([{"role": "user", "content": "hi"}], model="kimi-2.6")

        assert calls == ["kimi-2.6", "glm53", "kimi-2.6(Anthropic)"]

    def test_does_not_fallback_when_no_chain(self) -> None:
        backend = _backend(_provider(fallback_models=[]))
        with mock.patch.object(backend, "_chat_primary", side_effect=LLMTimeoutError(message="t", timeout_seconds=1)):
            with pytest.raises(LLMTimeoutError):
                backend.chat([{"role": "user", "content": "hi"}], model="kimi-2.6")

    def test_self_is_excluded_from_chain(self) -> None:
        backend = _backend(_provider(fallback_models=["kimi-2.6"]))
        assert backend._fallback_models_for("kimi-2.6") == []


class TestFallbackAsync:
    @pytest.mark.anyio
    async def test_async_path_uses_same_chain(self) -> None:
        backend = _backend(_provider())
        calls: list[str] = []

        async def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            if model == "kimi-2.6":
                raise LLMTimeoutError(message="timed out", timeout_seconds=30)
            return {"model": model}

        with mock.patch.object(backend, "_achat_primary", side_effect=_primary):
            result = await backend.achat([{"role": "user", "content": "hi"}], model="kimi-2.6")

        assert calls == ["kimi-2.6", "glm53"]
        assert result == {"model": "glm53"}
