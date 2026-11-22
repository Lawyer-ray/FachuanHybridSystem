"""Key 池的限流（429）口径：换 Key、按 ``retry-after`` 冷却、全池限流可识别。

业务口径是「遇到 429 只重试、用别的 Key 轮询，不换模型」。本文件锁 Key 池这一侧的三件事：

1. ``cooldown_hint`` **沿异常链**读 ``retry-after``：调用方拿到的是 ``_raise_mapped_error``
   包过一层的 ``LLMAPIError``，响应头在 ``__cause__`` 上。只看最外层会把网关给的 60 秒
   丢掉，退回写死的 30 秒；
2. ``attempt_budget``：一次请求在同一模型上最多换几把 Key（候选数与上限取小）；
3. ``rate_limited``：候选 Key 全部因 429 冷却时为真——调用方据此报 429，而不是抛一个
   无状态码的错误被降级链当成「可重试」悄悄换模型。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.core.llm.exceptions import LLMAPIError
from apps.core.llm.key_health import KeyHealth
from apps.core.llm.key_pool import KeyPool, cooldown_hint, is_rate_limited


class _ResponseError(Exception):
    """模拟 SDK 的状态错误：状态码与 ``retry-after`` 都挂在 ``.response`` 上。"""

    def __init__(self, status: int, retry_after: str | None = None) -> None:
        super().__init__(f"status {status}")
        headers = {"retry-after": retry_after} if retry_after else {}
        self.response = type("Resp", (), {"status_code": status, "headers": headers})()


def _mapped(status: int, retry_after: str | None = None) -> LLMAPIError:
    """``_raise_mapped_error`` 的形状：``LLMAPIError(status_code=...)`` ``from`` 原始 SDK 异常。"""
    try:
        try:
            raise _ResponseError(status, retry_after)
        except _ResponseError as inner:
            raise LLMAPIError(message=f"LLM API 调用错误: {inner}", status_code=status) from inner
    except LLMAPIError as outer:
        return outer


@pytest.fixture
def local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """只看进程内冷却：跨进程健康表走 Django cache，用例之间会互相污染。"""
    monkeypatch.setattr(KeyPool, "_shared_cooling", lambda self: {})
    monkeypatch.setattr(KeyPool, "_mark_shared", lambda self, *a, **kw: None)
    monkeypatch.setattr(KeyPool, "_clear_shared", lambda self, *a, **kw: None)
    monkeypatch.setattr(KeyPool, "FAILS_BEFORE_COOLDOWN", 1)


class TestCooldownHintThroughCause:
    def test_reads_retry_after_from_wrapped_error(self) -> None:
        """修复前：``LLMAPIError`` 自身没有 ``.response``，返回 ``None``（退回 30 秒默认冷却）。"""
        assert cooldown_hint(_mapped(429, "60")) == 60.0

    def test_wrapped_error_without_header_is_none(self) -> None:
        assert cooldown_hint(_mapped(429)) is None

    def test_is_rate_limited_follows_cause_chain(self) -> None:
        assert is_rate_limited(_mapped(429)) is True
        assert is_rate_limited(_mapped(503)) is False
        assert is_rate_limited(None) is False


class TestAttemptBudget:
    def test_budget_is_min_of_candidates_and_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(KeyPool, "MAX_KEY_ATTEMPTS", 3)
        assert KeyPool(["a"]).attempt_budget("m") == 1
        assert KeyPool(["a", "b"]).attempt_budget("m") == 2
        assert KeyPool([f"k{i}" for i in range(10)]).attempt_budget("m") == 3

    def test_budget_counts_only_keys_scoped_to_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(KeyPool, "MAX_KEY_ATTEMPTS", 10)
        pool = KeyPool(["a", "b", "c"], scopes={"a": ["glm53"], "b": ["glm53"]})
        # c 不限模型；a/b 只授权 glm53 → kimi 只有 c 一把可用
        assert pool.attempt_budget("kimi-2.6") == 1
        assert pool.attempt_budget("glm53") == 3


class TestRateLimitedPool:
    def _cool(self, pool: KeyPool, model: str, status: int) -> None:
        idx = pool.acquire(model)
        assert idx is not None
        error = _mapped(status, "60")
        pool.release(idx, success=False, model=model, error=error, cooldown_seconds=cooldown_hint(error))

    def test_all_keys_cooling_on_429_is_rate_limited(self, local_only: None) -> None:
        pool = KeyPool(["a", "b"])
        self._cool(pool, "m", 429)
        self._cool(pool, "m", 429)
        assert pool.acquire("m") is None
        assert pool.rate_limited("m") is True

    def test_one_key_still_free_is_not_rate_limited(self, local_only: None) -> None:
        pool = KeyPool(["a", "b"])
        self._cool(pool, "m", 429)
        assert pool.rate_limited("m") is False

    def test_cooling_for_other_reason_is_not_rate_limited(self, local_only: None) -> None:
        """一把 429、一把 503：那不是「被限流」，按原口径（可换模型）处理。"""
        pool = KeyPool(["a", "b"])
        self._cool(pool, "m", 429)
        self._cool(pool, "m", 503)
        assert pool.acquire("m") is None
        assert pool.rate_limited("m") is False

    def test_reason_carries_status(self, local_only: None) -> None:
        pool = KeyPool(["a"])
        self._cool(pool, "m", 429)
        rows = [row for row in pool.snapshot() if row["cooling"]]
        assert rows and rows[0]["reason"].startswith("HTTP 429")
        assert rows[0]["cooling_remaining"] > 30, "retry-after=60 应覆盖 30 秒默认冷却"

    def test_success_clears_rate_limit_state(self, local_only: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(KeyPool, "FAILS_BEFORE_COOLDOWN", 2)
        pool = KeyPool(["a"])
        idx = pool.acquire("m")
        assert idx is not None
        pool.release(idx, success=False, model="m", error=_mapped(429))
        pool.release(pool.acquire("m") or 0, success=True, model="m")
        assert pool.rate_limited("m") is False

    def test_key_cooled_by_other_process_on_429_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """只在别的进程冷却的 Key：靠共享原因里的 ``HTTP 429`` 标注认出限流。"""
        shared: dict[str, Any] = {"a": KeyHealth(remaining=30.0, reason="HTTP 429 · LLMAPIError（冷却 60s）")}
        monkeypatch.setattr(KeyPool, "_shared_cooling", lambda self: shared)
        pool = KeyPool(["a"])
        assert pool.rate_limited("m") is True
        shared["a"] = KeyHealth(remaining=30.0, reason="HTTP 401 · LLMAuthenticationError（冷却 600s）")
        assert pool.rate_limited("m") is False
