"""Circuit breaker 与 LLM 回退策略可靠性集成的单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.llm.circuit_breaker import CircuitBreaker
from apps.core.llm.exceptions import LLMTimeoutError

# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_validation(self):
        with pytest.raises(ValueError):
            CircuitBreaker(fail_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreaker(fail_threshold=-1)

    def test_trip_after_threshold(self):
        brk = CircuitBreaker(fail_threshold=3, cooldown_seconds=30)
        assert brk.is_tripped("b1") is False
        brk.record_failure("b1")
        brk.record_failure("b1")
        assert brk.is_tripped("b1") is False  # 未达阈值
        brk.record_failure("b1")
        assert brk.is_tripped("b1") is True  # 达阈值短路
        assert brk.failure_counts()["b1"] == 0  # 触发后计数清零

    def test_success_resets_failures(self):
        brk = CircuitBreaker(fail_threshold=3)
        brk.record_failure("b1")
        brk.record_failure("b1")
        brk.record_success("b1")
        assert brk.failure_counts().get("b1", 0) == 0

    def test_cooldown_expiry_auto_resets(self, monkeypatch):
        brk = CircuitBreaker(fail_threshold=2, cooldown_seconds=30)
        current = [1000.0]
        monkeypatch.setattr("apps.core.llm.circuit_breaker.time.monotonic", lambda: current[0])
        brk.record_failure("b1")
        brk.record_failure("b1")
        assert brk.is_tripped("b1") is True
        current[0] += 31.0
        assert brk.is_tripped("b1") is False

    def test_cooldown_not_expired_stays_tripped(self, monkeypatch):
        brk = CircuitBreaker(fail_threshold=2, cooldown_seconds=30)
        current = [1000.0]
        monkeypatch.setattr("apps.core.llm.circuit_breaker.time.monotonic", lambda: current[0])
        brk.record_failure("b1")
        brk.record_failure("b1")
        current[0] += 10.0
        assert brk.is_tripped("b1") is True

    def test_per_backend_isolation(self):
        brk = CircuitBreaker(fail_threshold=2)
        brk.record_failure("b1")
        brk.record_failure("b1")
        assert brk.is_tripped("b1") is True
        assert brk.is_tripped("b2") is False

    def test_reset(self):
        brk = CircuitBreaker(fail_threshold=2)
        brk.record_failure("b1")
        brk.record_failure("b1")
        brk.reset()
        assert brk.is_tripped("b1") is False
        assert brk.failure_counts() == {}


# ---------------------------------------------------------------------------
# LLMFallbackPolicy 可靠性集成（熔断跳过 + 退避重试）
# ---------------------------------------------------------------------------


class TestLLMReliability:
    def _make_backend(self, available=True, base_url="http://x", api_key="k", model="m"):
        b = MagicMock()
        b.is_available.return_value = available
        type(b).base_url = property(lambda self: base_url)
        type(b).api_key = property(lambda self: api_key)
        type(b).default_model = property(lambda self: model)
        return b

    def _make_router(self, backends):
        router = MagicMock()
        router.get_backends_by_priority.return_value = backends
        router.get_backend.side_effect = lambda name: dict(backends)[name]
        return router

    def test_tripped_backend_is_skipped(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = self._make_backend()
        b2 = self._make_backend()
        router = self._make_router([("b1", b1), ("b2", b2)])
        breaker = CircuitBreaker(fail_threshold=1)  # 一次失败即短路
        policy = LLMFallbackPolicy(router=router, breaker=breaker)

        def fail_op(backend):
            raise LLMTimeoutError(timeout_seconds=5)

        with pytest.raises(LLMTimeoutError):
            policy.execute(operation=fail_op, backend="b1", fallback=False)
        assert breaker.is_tripped("b1") is True
        # b1 已短路,再次执行应直接跳过 b1 走 b2
        result = policy.execute(operation=lambda b: "ok")
        assert result == "ok"

    def test_retry_with_exponential_backoff(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = self._make_backend()
        router = self._make_router([("b1", b1)])
        sleeps = []
        policy = LLMFallbackPolicy(
            router=router, max_retries=2, backoff_base=1.0, backoff_factor=2.0, sleep=sleeps.append
        )

        calls = 0

        def op(backend):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise LLMTimeoutError(timeout_seconds=1)
            return "ok"

        assert policy.execute(operation=op, backend="b1", fallback=False) == "ok"
        assert calls == 3  # 首次失败后退避重试 2 次,共 3 次调用
        assert sleeps == [1.0, 2.0]  # 指数退避:1s, 2s

    def test_retry_exhausted_raises_original(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = self._make_backend()
        router = self._make_router([("b1", b1)])
        policy = LLMFallbackPolicy(
            router=router,
            max_retries=1,
            backoff_base=0.0,
            sleep=lambda _s: None,
        )
        with pytest.raises(LLMTimeoutError):
            policy.execute(
                operation=lambda b: (_ for _ in ()).throw(LLMTimeoutError(timeout_seconds=1)),
                backend="b1",
                fallback=False,
            )

    def test_success_resets_breaker(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = self._make_backend()
        router = self._make_router([("b1", b1)])
        breaker = CircuitBreaker(fail_threshold=2)
        policy = LLMFallbackPolicy(router=router, breaker=breaker)

        for _ in range(2):
            with pytest.raises(LLMTimeoutError):
                policy.execute(
                    operation=lambda b: (_ for _ in ()).throw(LLMTimeoutError(timeout_seconds=1)),
                    backend="b1",
                    fallback=False,
                )
        assert breaker.is_tripped("b1") is True
        # 一次成功应清除失败计数并复位熔断
        assert policy.execute(operation=lambda b: "ok", backend="b1", fallback=False) == "ok"
        assert breaker.is_tripped("b1") is False
        assert breaker.failure_counts().get("b1", 0) == 0

    @pytest.mark.asyncio
    async def test_async_tripped_backend_is_skipped(self):
        from apps.core.llm.fallback_policy import LLMFallbackPolicy

        b1 = self._make_backend()
        b2 = self._make_backend()
        router = self._make_router([("b1", b1), ("b2", b2)])
        breaker = CircuitBreaker(fail_threshold=1)
        policy = LLMFallbackPolicy(router=router, breaker=breaker)

        async def fail_op(backend):
            raise LLMTimeoutError(timeout_seconds=1)

        with pytest.raises(LLMTimeoutError):
            await policy.execute_async(operation=fail_op, backend="b1", fallback=False)
        assert breaker.is_tripped("b1") is True

        async def ok_op(backend):
            return "ok"

        assert await policy.execute_async(operation=ok_op) == "ok"
