"""Key 池的失败分类策略（对齐 LiteLLM 的状态码白名单）。

## 守的是什么

旧实现是二值 ``release(success=False)``：任何异常都让 ``(Key, 模型)`` 冷却 30 秒。
后果是**自伤**——一次用户传的超长 prompt 触发 400，``for _ in range(len(pool.keys))``
会把这个坏请求在每把 Key 上重放一遍，于是整池一起冷却；下一个正常用户拿到
「该平台全部 API Key 均不可用」（2026-11 审计 P0-4）。

LiteLLM 的答案（``router_utils/cooldown_handlers.py`` ``_is_cooldown_required``）是
**状态码白名单**：只有 429/401/402/408/404 与 5xx 才冷却，其余 4XX 一律不冷却，
因为「客户端错不该怪 deployment」。本文件把那条口径钉死，并按我们的语义补两点：

- 403 在我们这里是「这把 Key 没有该模型权限」→ 必须冷却；
- 冷却时长可被网关的 ``retry-after`` 覆盖（实测 429 带 60，比写死的 30 长）。
"""

from __future__ import annotations

import time
from collections import deque

import pytest

from apps.core.llm.key_pool import KeyPool, cooldown_hint, is_key_fault


class _StatusError(Exception):
    """模拟 ``openai.APIStatusError``：状态码挂在 ``.status_code`` 上。"""

    def __init__(self, status: int) -> None:
        super().__init__(f"status {status}")
        self.status_code = status


class _ResponseError(Exception):
    """模拟带响应对象的错误：状态码与 ``retry-after`` 都在 ``.response`` 上。"""

    def __init__(self, status: int, retry_after: str | None = None) -> None:
        super().__init__(f"status {status}")
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        self.response = type("_Resp", (), {"status_code": status, "headers": headers})()


class APITimeoutError(Exception):  # 类名与 openai SDK 对齐（按名识别）
    """按类名识别的传输层异常（不依赖 openai 包）。"""


class TestKeyFaultClassification:
    @pytest.mark.parametrize("status", [401, 402, 403, 404, 408, 429])
    def test_key_and_gateway_status_are_key_faults(self, status: int) -> None:
        assert is_key_fault(_StatusError(status)) is True

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_5xx_is_key_fault(self, status: int) -> None:
        assert is_key_fault(_StatusError(status)) is True

    @pytest.mark.parametrize("status", [400, 413, 415, 422])
    def test_client_side_4xx_is_not_key_fault(self, status: int) -> None:
        """参数错 / 请求体过大 / 不支持的媒体类型：换 Key 重放没有意义。"""
        assert is_key_fault(_StatusError(status)) is False

    def test_transport_errors_are_key_fault(self) -> None:
        assert is_key_fault(APITimeoutError()) is True

    def test_plain_exception_is_not_key_fault(self) -> None:
        assert is_key_fault(TypeError("bad payload")) is False
        assert is_key_fault(ValueError("cannot parse")) is False

    def test_status_found_through_cause_chain(self) -> None:
        try:
            try:
                raise _ResponseError(429)
            except Exception as inner:
                raise RuntimeError("wrapped") from inner
        except RuntimeError as outer:
            assert is_key_fault(outer) is True


class TestCooldownHint:
    def test_reads_retry_after(self) -> None:
        assert cooldown_hint(_ResponseError(429, "60")) == 60.0

    def test_clamps_to_sane_range(self) -> None:
        assert cooldown_hint(_ResponseError(429, "9999")) == 300.0
        assert cooldown_hint(_ResponseError(429, "0")) == 5.0

    def test_missing_or_unparsable_returns_none(self) -> None:
        assert cooldown_hint(None) is None
        assert cooldown_hint(_StatusError(429)) is None
        # HTTP-date 形式不解析：宁可回落默认冷却，也不要猜错时间
        assert cooldown_hint(_ResponseError(429, "Wed, 21 Oct 2026 07:28:00 GMT")) is None


class TestPoolCooldownPolicy:
    """池层面的后果：不该冷却的绝不冷却，该冷却的要连续两次才冷却。"""

    @pytest.fixture()
    def pool(self, monkeypatch: pytest.MonkeyPatch) -> KeyPool:
        monkeypatch.setattr(KeyPool, "COOLDOWN_SECONDS", 30.0)
        monkeypatch.setattr(KeyPool, "FAILS_BEFORE_COOLDOWN", 2)
        # 单 Key 池：多 Key 会在 acquire 时轮转到另一把，测「同一把连续失败」就会失焦
        return KeyPool(["sk-a"], concurrency_per_key=3)

    def test_non_key_fault_does_not_cool(self, pool: KeyPool) -> None:
        idx = pool.acquire("kimi-2.6")
        assert idx is not None
        pool.release(idx, success=False, model="kimi-2.6", error=_StatusError(400))

        assert pool.is_cooling(idx, "kimi-2.6") is False
        # 该 Key 仍可被选中
        assert pool.acquire("kimi-2.6") is not None

    def test_key_fault_needs_repeated_failures(self, pool: KeyPool) -> None:
        idx = pool.acquire("kimi-2.6")
        assert idx is not None
        pool.release(idx, success=False, model="kimi-2.6", error=_StatusError(502))
        assert pool.is_cooling(idx, "kimi-2.6") is False, "第一次失败只计数，不该冷却"

        got = pool.acquire("kimi-2.6")
        assert got is not None
        pool.release(got, success=False, model="kimi-2.6", error=_StatusError(502))
        assert pool.is_cooling(got, "kimi-2.6") is True, "连续两次才冷却"

    def test_success_resets_failure_counter(self, pool: KeyPool) -> None:
        first = pool.acquire("kimi-2.6")
        assert first is not None
        pool.release(first, success=False, model="kimi-2.6", error=_StatusError(503))
        pool.release(pool.acquire("kimi-2.6") or 0, success=True, model="kimi-2.6")

        again = pool.acquire("kimi-2.6")
        assert again is not None
        pool.release(again, success=False, model="kimi-2.6", error=_StatusError(503))
        assert pool.is_cooling(again, "kimi-2.6") is False, "成功后计数清零，本次只是第 1 次"

    def test_retry_after_overrides_cooldown(self, pool: KeyPool) -> None:
        for _ in range(2):
            idx = pool.acquire("kimi-2.6")
            assert idx is not None
            error = _ResponseError(429, "120")
            pool.release(idx, success=False, model="kimi-2.6", error=error, cooldown_seconds=cooldown_hint(error))

        rows = [row for row in pool.snapshot() if row["cooling"]]
        assert rows, "应按 retry-after 进入更长的冷却"
        assert rows[0]["cooling_remaining"] > 60, rows
        assert "429" in rows[0]["reason"] or "Response" in rows[0]["reason"]

    def test_snapshot_has_no_key_plaintext(self, pool: KeyPool) -> None:
        idx = pool.acquire("kimi-2.6")
        assert idx is not None
        pool.release(idx, success=False, model="kimi-2.6", error=_StatusError(429))

        dumped = repr(pool.snapshot())
        assert "sk-a" not in dumped
        assert pool.snapshot()[0]["index"] == 1  # 下标从 1 开始，便于运维对话

    def test_non_key_fault_is_not_counted_as_fail(self, pool: KeyPool) -> None:
        for _ in range(5):
            idx = pool.acquire("kimi-2.6")
            assert idx is not None
            pool.release(idx, success=False, model="kimi-2.6", error=_StatusError(422))
        assert pool.is_cooling(idx, "kimi-2.6") is False


class TestRateLimits:
    """rpm/tpm：**滑动窗口**统计 + 默认只观测不拒绝。

    为什么默认不拒绝：额度没有探测手段（网关的 ``x-ratelimit-*`` 头我们没解析），
    填错就拒绝会误伤正常律师。先跑一周看真实分布，再开 ``FACHUAN_KEY_RATE_LIMIT_ENFORCE=1``。

    为什么是滑动窗口而不是分钟桶（LiteLLM 用分钟桶）：固定窗口在 12:00:59 与
    12:01:01 的瞬时速率可以翻倍——它敢那么写是因为还有单请求 token 预检兜底。
    """

    @pytest.fixture()
    def pool(self, monkeypatch: pytest.MonkeyPatch) -> KeyPool:
        monkeypatch.setattr(KeyPool, "COOLDOWN_SECONDS", 30.0)
        monkeypatch.setattr(KeyPool, "FAILS_BEFORE_COOLDOWN", 2)
        monkeypatch.setattr("apps.core.llm.key_pool.rate_limit_enforce", lambda: False)
        pool = KeyPool(["k1", "k2"], concurrency_per_key=5)
        pool.configure_limits(rpm=2, tpm=1000)
        return pool

    def test_observe_mode_counts_but_never_blocks(self, pool: KeyPool) -> None:
        for _ in range(10):
            idx = pool.acquire("m")
            assert idx is not None
            pool.release(idx, success=True, model="m")

        rows = {row["index"]: row for row in pool.rate_snapshot()}
        assert sum(row["requests_60s"] for row in rows.values()) > 2, "观察模式仍要计数"
        assert all(row["requests_60s"] <= 10 for row in rows.values())

    def test_enforce_mode_skips_over_rpm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("apps.core.llm.key_pool.rate_limit_enforce", lambda: True)
        pool = KeyPool(["k1", "k2"], concurrency_per_key=5)
        pool.configure_limits(rpm=1, tpm=0)
        # 只把 k1 的窗口占满（手工塞一条样本，避免 acquire 轮转把两把都填满）
        pool._window.setdefault(0, deque()).append((time.monotonic(), 0))

        idx = pool.acquire("m")

        assert idx == 1, "超 rpm 的 Key 应被跳过，改用另一把"

    def test_tokens_are_recorded_for_tpm(self, pool: KeyPool) -> None:
        idx = pool.acquire("m")
        assert idx is not None
        pool.release(idx, success=True, model="m", tokens=750)

        rows = {row["index"]: row for row in pool.rate_snapshot()}
        assert rows[idx + 1]["tokens_60s"] == 750

    def test_zero_limits_mean_unlimited(self) -> None:
        pool = KeyPool(["k1"], concurrency_per_key=3)
        pool.configure_limits(rpm=0, tpm=0)
        assert pool._over_limit(0, __import__("time").monotonic()) == ""
