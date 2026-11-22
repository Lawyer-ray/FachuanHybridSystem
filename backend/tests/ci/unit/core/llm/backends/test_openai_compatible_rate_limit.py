"""服务通道（``OpenAICompatibleBackend``）的 429 与降级判定。

业务口径：**遇到 429 只重试、用别的 Key 轮询，不换模型**。本文件锁的是：

1. 429 在**同一模型**上换下一把 Key 重试，成功即返回，降级链一个都不碰；
2. 所有 Key 都 429（或全在 429 冷却中、一次没发出去）→ 报可读的限流错误
   （``status_code=429``），**不换模型**。修复前「全部冷却」抛的是无状态码错误，
   被 ``is_retryable`` 当成可重试，悄悄换成了备选模型；
3. 内层已映射的 ``LLMAPIError(400)`` 不能被二次映射丢掉状态码——否则 400 变成
   「可重试」，同一个坏请求会把降级链上每个模型各打一遍；
4. 降级循环里的备选模型同样按 ``is_retryable`` 判定：遇到 400 立即停，不把整条链打完；
5. ``LLMBackendUnavailableError`` 不重试（判定收进 ``gateway_profile.is_retryable``）；
6. **只有一把 Key** 时遇 429：按 ``retry-after`` 等一次（≤10 秒）再试，仍不换模型；
   网关要求等得更久就不等，直接报限流。

全部离线：``_chat_sync_once`` / ``_chat_async_once`` / ``_chat_primary`` 用 mock 顶掉。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from apps.core.llm.backends.base import BackendConfig, LLMResponse, OpenAIProviderConfig
from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
from apps.core.llm.exceptions import LLMAPIError, LLMBackendUnavailableError
from apps.core.llm.key_pool import KeyPool, reset_shared_pools

_MESSAGES = [{"role": "user", "content": "hi"}]


class _ResponseError(Exception):
    """模拟 SDK 的状态错误（状态码与 ``retry-after`` 挂在 ``.response`` 上）。"""

    def __init__(self, status: int, retry_after: str | None = None) -> None:
        super().__init__(f"status {status}")
        headers = {"retry-after": retry_after} if retry_after else {}
        self.response = type("Resp", (), {"status_code": status, "headers": headers})()


def _mapped(status: int, retry_after: str | None = None) -> LLMAPIError:
    """与 ``_chat_sync_once`` 抛出的形状一致：已映射的 ``LLMAPIError`` ``from`` SDK 异常。"""
    try:
        try:
            raise _ResponseError(status, retry_after)
        except _ResponseError as inner:
            raise LLMAPIError(message=f"LLM API 调用错误: {inner}", status_code=status) from inner
    except LLMAPIError as outer:
        return outer


def _response(model: str) -> LLMResponse:
    return LLMResponse(
        content="ok", model=model, prompt_tokens=1, completion_tokens=1, total_tokens=2, duration_ms=1.0
    )


@pytest.fixture(autouse=True)
def _isolated_pools(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Key 池是进程级共享状态；跨进程健康表走 Django cache——两者都隔离掉。"""
    reset_shared_pools()
    monkeypatch.setattr(KeyPool, "_shared_cooling", lambda self: {})
    monkeypatch.setattr(KeyPool, "_mark_shared", lambda self, *a, **kw: None)
    monkeypatch.setattr(KeyPool, "_clear_shared", lambda self, *a, **kw: None)
    yield
    reset_shared_pools()


def _backend(keys: list[str], fallback_models: list[str] | None = None, name: str = "律所网关") -> Any:
    provider = OpenAIProviderConfig(
        name=name,
        base_url="http://gw.internal:4000/v1",
        api_keys=keys,
        default_model="kimi-2.6",
        extra_models=["glm53"],
        fallback_models=fallback_models if fallback_models is not None else ["glm53"],
    )
    config = BackendConfig(name="oai", enabled=True, priority=1, default_model="kimi-2.6", providers=[provider])
    return OpenAICompatibleBackend(config=config)


class TestRateLimitRotatesKeysNotModels:
    def test_429_switches_to_next_key_on_same_model(self) -> None:
        backend = _backend(["k1", "k2"])  # pragma: allowlist secret
        calls: list[tuple[str, str]] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            calls.append((api_key, used_model))
            if api_key == "k1":
                raise _mapped(429, "60")
            return _response(used_model)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            result = backend.chat(_MESSAGES, model="kimi-2.6")

        assert result.model == "kimi-2.6"
        assert calls == [("k1", "kimi-2.6"), ("k2", "kimi-2.6")]

    def test_all_keys_429_raises_rate_limit_without_fallback(self) -> None:
        backend = _backend(["k1", "k2"])  # pragma: allowlist secret
        models: list[str] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            models.append(used_model)
            raise _mapped(429, "60")

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError) as exc_info:
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "LLM_RATE_LIMITED"
        assert "限流" in exc_info.value.message
        assert models == ["kimi-2.6", "kimi-2.6"], "限流不换模型：glm53 一次都不该被调"

    def test_pool_fully_cooling_on_429_raises_rate_limit_not_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """一次都没发出去（全池已在 429 冷却）：修复前抛无状态码错误 → 被当可重试 → 换模型。"""
        monkeypatch.setattr(KeyPool, "FAILS_BEFORE_COOLDOWN", 1)
        backend = _backend(["k1"])  # pragma: allowlist secret
        provider = backend._resolve_provider("kimi-2.6")
        pool = backend._key_pool(provider)
        idx = pool.acquire("kimi-2.6")
        assert idx is not None
        pool.release(idx, success=False, model="kimi-2.6", error=_mapped(429), cooldown_seconds=60.0)

        models: list[str] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            models.append(used_model)
            return _response(used_model)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError) as exc_info:
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert exc_info.value.status_code == 429
        assert models == [], "kimi-2.6 全在冷却、且不能降级到 glm53"

    def test_key_attempts_are_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(KeyPool, "MAX_KEY_ATTEMPTS", 2)
        backend = _backend([f"k{i}" for i in range(6)], fallback_models=[])
        tried: list[str] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            tried.append(api_key)
            raise _mapped(503)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError):
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert len(tried) == 2

    @pytest.mark.anyio
    async def test_async_path_rotates_keys_on_429(self) -> None:
        backend = _backend(["k1", "k2"])  # pragma: allowlist secret
        calls: list[tuple[str, str]] = []

        async def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            calls.append((api_key, used_model))
            if api_key == "k1":
                raise _mapped(429)
            return _response(used_model)

        with patch.object(backend, "_chat_async_once", side_effect=_once):
            result = await backend.achat(_MESSAGES, model="kimi-2.6")

        assert result.model == "kimi-2.6"
        assert calls == [("k1", "kimi-2.6"), ("k2", "kimi-2.6")]


class TestMappedErrorKeepsStatus:
    def test_400_is_not_remapped_into_retryable(self) -> None:
        """修复前：内层 ``LLMAPIError(400)`` 被二次映射成无状态码 → 可重试 → 降级到 glm53。"""
        backend = _backend(["k1", "k2"])  # pragma: allowlist secret
        calls: list[tuple[str, str]] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            calls.append((api_key, used_model))
            raise _mapped(400)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError) as exc_info:
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert exc_info.value.status_code == 400
        assert calls == [("k1", "kimi-2.6")], "400 不换 Key、不换模型"

    def test_raise_mapped_error_reraises_llm_errors_as_is(self) -> None:
        backend = _backend(["k1"])  # pragma: allowlist secret
        original = _mapped(422)
        with pytest.raises(LLMAPIError) as exc_info:
            backend._raise_mapped_error(original, 30.0, "http://test")
        assert exc_info.value is original


class TestFallbackLoopUsesIsRetryable:
    def _run(self, backend: Any, errors: dict[str, Exception]) -> list[str]:
        calls: list[str] = []

        def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            raise errors[model or ""]

        with patch.object(backend, "_chat_primary", side_effect=_primary):
            with pytest.raises(LLMAPIError):
                backend.chat(_MESSAGES, model="kimi-2.6")
        return calls

    def test_candidate_400_stops_the_chain(self) -> None:
        backend = _backend(["k1"], fallback_models=["glm53", "qwen3"])  # pragma: allowlist secret
        calls = self._run(
            backend,
            {
                "kimi-2.6": LLMAPIError(message="upstream", status_code=500),
                "glm53": LLMAPIError(message="bad request", status_code=400),
                "qwen3": LLMAPIError(message="never", status_code=500),
            },
        )
        assert calls == ["kimi-2.6", "glm53"], "备选模型 400 后不该继续打 qwen3"

    def test_candidate_429_stops_the_chain(self) -> None:
        backend = _backend(["k1"], fallback_models=["glm53", "qwen3"])  # pragma: allowlist secret
        calls = self._run(
            backend,
            {
                "kimi-2.6": LLMAPIError(message="upstream", status_code=502),
                "glm53": LLMAPIError(message="rate limited", status_code=429),
                "qwen3": LLMAPIError(message="never", status_code=500),
            },
        )
        assert calls == ["kimi-2.6", "glm53"]

    def test_backend_unavailable_does_not_fall_back(self) -> None:
        backend = _backend(["k1"], fallback_models=["glm53"])  # pragma: allowlist secret
        calls: list[str] = []

        def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            raise LLMBackendUnavailableError()

        with patch.object(backend, "_chat_primary", side_effect=_primary):
            with pytest.raises(LLMBackendUnavailableError):
                backend.chat(_MESSAGES, model="kimi-2.6")
        assert calls == ["kimi-2.6"]

    @pytest.mark.anyio
    async def test_async_candidate_400_stops_the_chain(self) -> None:
        backend = _backend(["k1"], fallback_models=["glm53", "qwen3"])  # pragma: allowlist secret
        calls: list[str] = []
        errors = {
            "kimi-2.6": LLMAPIError(message="upstream", status_code=500),
            "glm53": LLMAPIError(message="bad request", status_code=400),
            "qwen3": LLMAPIError(message="never", status_code=500),
        }

        async def _primary(messages: Any, model: str | None = None, *a: Any, **kw: Any) -> Any:
            calls.append(model or "")
            raise errors[model or ""]

        with patch.object(backend, "_achat_primary", side_effect=_primary):
            with pytest.raises(LLMAPIError) as exc_info:
                await backend.achat(_MESSAGES, model="kimi-2.6")
        assert exc_info.value.status_code == 400
        assert calls == ["kimi-2.6", "glm53"]


class TestSingleKeyWaitsOnceOn429:
    """单 Key 平台没有别的 Key 可轮询：按 ``retry-after`` 等一次再试（业务方决定）。"""

    @pytest.fixture()
    def sleeps(self, monkeypatch: pytest.MonkeyPatch) -> list[float]:
        from apps.core.llm.backends import openai_compatible as oc_module

        recorded: list[float] = []
        monkeypatch.setattr(oc_module.time, "sleep", recorded.append)
        return recorded

    def test_waits_retry_after_then_succeeds_on_same_key_and_model(self, sleeps: list[float]) -> None:
        backend = _backend(["k1"])  # pragma: allowlist secret
        calls: list[tuple[str, str]] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            calls.append((api_key, used_model))
            if len(calls) == 1:
                raise _mapped(429, "3")
            return _response(used_model)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            result = backend.chat(_MESSAGES, model="kimi-2.6")

        assert result.model == "kimi-2.6"
        assert sleeps == [3.0]
        assert calls == [("k1", "kimi-2.6"), ("k1", "kimi-2.6")], "只等一次、不换模型"

    def test_waits_default_when_no_retry_after(self, sleeps: list[float]) -> None:
        from apps.core.llm.key_pool import RATE_LIMIT_WAIT_DEFAULT_SECONDS

        backend = _backend(["k1"])  # pragma: allowlist secret
        attempts: list[int] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            attempts.append(1)
            if len(attempts) == 1:
                raise _mapped(429)
            return _response(used_model)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            backend.chat(_MESSAGES, model="kimi-2.6")

        assert sleeps == [RATE_LIMIT_WAIT_DEFAULT_SECONDS]

    def test_still_429_after_one_wait_raises_rate_limit(self, sleeps: list[float]) -> None:
        backend = _backend(["k1"])  # pragma: allowlist secret
        models: list[str] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            models.append(used_model)
            raise _mapped(429, "1")

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError) as exc_info:
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert exc_info.value.status_code == 429
        assert sleeps == [1.0], "只等一次"
        assert models == ["kimi-2.6", "kimi-2.6"], "不换模型"

    def test_retry_after_too_long_does_not_wait(self, sleeps: list[float]) -> None:
        backend = _backend(["k1"])  # pragma: allowlist secret
        calls: list[str] = []

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            calls.append(used_model)
            raise _mapped(429, "60")

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError) as exc_info:
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert exc_info.value.status_code == 429
        assert sleeps == []
        assert calls == ["kimi-2.6"]

    def test_multi_key_platform_never_sleeps(self, sleeps: list[float]) -> None:
        backend = _backend(["k1", "k2"])  # pragma: allowlist secret

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            raise _mapped(429, "1")

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError):
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert sleeps == [], "多 Key 靠换 Key 轮询，不在请求线程里等"

    def test_non_429_does_not_wait(self, sleeps: list[float]) -> None:
        backend = _backend(["k1"], fallback_models=[])  # pragma: allowlist secret

        def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            raise _mapped(503)

        with patch.object(backend, "_chat_sync_once", side_effect=_once):
            with pytest.raises(LLMAPIError):
                backend.chat(_MESSAGES, model="kimi-2.6")

        assert sleeps == []

    @pytest.mark.anyio
    async def test_async_path_waits_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.core.llm.backends import openai_compatible as oc_module

        waited: list[float] = []

        async def _fake_sleep(seconds: float) -> None:
            waited.append(seconds)

        monkeypatch.setattr(oc_module.asyncio, "sleep", _fake_sleep)
        backend = _backend(["k1"])  # pragma: allowlist secret
        calls: list[str] = []

        async def _once(api_key: str, base_url: str, timeout: float, payload: dict[str, Any], used_model: str) -> Any:
            calls.append(used_model)
            if len(calls) == 1:
                raise _mapped(429, "2")
            return _response(used_model)

        with patch.object(backend, "_chat_async_once", side_effect=_once):
            result = await backend.achat(_MESSAGES, model="kimi-2.6")

        assert result.model == "kimi-2.6"
        assert waited == [2.0]
        assert calls == ["kimi-2.6", "kimi-2.6"]


class TestRateLimitWaitSeconds:
    def test_uses_raw_retry_after_within_cap(self) -> None:
        from apps.core.llm.key_pool import rate_limit_wait_seconds

        # 不走冷却口径的 [5, 300] 夹取：网关说等 1 秒就等 1 秒
        assert rate_limit_wait_seconds(_mapped(429, "1")) == 1.0

    def test_over_cap_returns_none(self) -> None:
        from apps.core.llm.key_pool import RATE_LIMIT_WAIT_MAX_SECONDS, rate_limit_wait_seconds

        assert rate_limit_wait_seconds(_mapped(429, str(RATE_LIMIT_WAIT_MAX_SECONDS + 1))) is None

    def test_not_rate_limited_returns_none(self) -> None:
        from apps.core.llm.key_pool import rate_limit_wait_seconds

        assert rate_limit_wait_seconds(_mapped(503, "1")) is None
        assert rate_limit_wait_seconds(None) is None
