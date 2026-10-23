"""进程池排队可见性与排队超时（P1-1）。

背景：池容量是「限流器」不是缓存池。容量 4 时第 5 个用户开始排队，
旧实现用裸 `asyncio.Semaphore` 无限等——用户盯着转圈、HTTP 连接挂着、
最后两头超时且查不到原因。这里补三件事：排队位置可见、排队超时、
结束时排队计数归零。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from apps.agent.pi import pool as pool_module
from apps.agent.pi.pool import PiProcessPool, PoolConfig, PoolQueueTimeoutError


class _StubSession:
    """不出真进程的会话桩；close 有微小延迟以模拟真实启动/关闭。"""

    def __init__(self, **kwargs: Any) -> None:
        self.closed = False

    async def start(self) -> None:
        await asyncio.sleep(0.05)

    async def close(self, *, abort_running: bool = False) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _stub_pool_internals(monkeypatch: pytest.MonkeyPatch) -> Any:
    """替掉配置渲染与真进程，保留 acquire 的并发/排队逻辑不动。"""
    monkeypatch.setattr(pool_module, "write_pi_config", lambda *a, **k: None)
    monkeypatch.setattr(pool_module, "PiRpcSession", _StubSession)
    monkeypatch.setattr(
        pool_module, "layout", lambda: (Path("/tmp/stub-work"), Path("/tmp/stub-config"), Path("/tmp/stub-sessions"))
    )
    yield


class TestPoolQueueVisibility:
    def test_saturated_false_when_idle(self) -> None:
        async def run() -> bool:
            return PiProcessPool(PoolConfig(size=2)).saturated

        assert asyncio.run(run()) is False

    def test_saturated_true_when_all_slots_taken(self) -> None:
        positions: list[int] = []

        async def run() -> bool:
            p = PiProcessPool(PoolConfig(size=1, queue_timeout=5, on_queued=positions.append))

            async def hold() -> None:
                async with p.acquire():
                    await asyncio.sleep(0.3)

            async def second() -> None:
                await asyncio.sleep(0.05)
                async with p.acquire():
                    return None

            await asyncio.gather(hold(), second())
            return True

        assert asyncio.run(run()) is True
        # 第二个请求在池满时登记了排队，位置从 1 开始
        assert positions == [1]

    def test_queue_position_increments(self) -> None:
        """三个请求抢一个位置：后两个的排队位置要递增（1、2）。"""
        positions: list[int] = []

        async def run() -> None:
            p = PiProcessPool(PoolConfig(size=1, queue_timeout=10, on_queued=positions.append))

            async def hold() -> None:
                async with p.acquire():
                    await asyncio.sleep(0.4)

            async def waiter() -> None:
                await asyncio.sleep(0.05)
                async with p.acquire():
                    await asyncio.sleep(0.01)

            await asyncio.gather(hold(), waiter(), waiter())

        asyncio.run(run())
        assert positions == [1, 2], f"排队位置不递增: {positions}"

    def test_waiting_returns_to_zero_after_all_done(self) -> None:
        """并发结束后排队计数必须归零，否则前端会一直显示「排队中」。"""

        async def run() -> int:
            p = PiProcessPool(PoolConfig(size=1, queue_timeout=10))

            async def hold() -> None:
                async with p.acquire():
                    await asyncio.sleep(0.2)

            async def waiter() -> None:
                await asyncio.sleep(0.05)
                async with p.acquire():
                    await asyncio.sleep(0.01)

            await asyncio.gather(hold(), waiter())
            return p.waiting

        assert asyncio.run(run()) == 0

    def test_no_queue_announced_when_pool_free(self) -> None:
        """池没满时不该虚报排队。"""
        positions: list[int] = []

        async def run() -> None:
            p = PiProcessPool(PoolConfig(size=4, queue_timeout=5, on_queued=positions.append))
            async with p.acquire():
                await asyncio.sleep(0.01)

        asyncio.run(run())
        assert positions == []


class TestPoolQueueTimeout:
    def test_timeout_raises_readable_error(self) -> None:
        """排队超时必须抛可读异常，不能永久挂死。"""

        async def run() -> None:
            p = PiProcessPool(PoolConfig(size=1, queue_timeout=0.15))

            async def hold() -> None:
                async with p.acquire():
                    await asyncio.sleep(0.6)

            async def waiter() -> None:
                await asyncio.sleep(0.03)
                async with p.acquire():
                    return None

            await asyncio.gather(hold(), waiter())

        with pytest.raises(PoolQueueTimeoutError) as excinfo:
            asyncio.run(run())
        assert "排队超过" in str(excinfo.value)

    def test_zero_timeout_disables_limit(self) -> None:
        """queue_timeout=0 表示不限（内部批量场景）。"""

        async def run() -> bool:
            p = PiProcessPool(PoolConfig(size=1, queue_timeout=0))

            async def hold() -> None:
                async with p.acquire():
                    await asyncio.sleep(0.3)

            async def waiter() -> None:
                await asyncio.sleep(0.03)
                async with p.acquire():
                    return None

            await asyncio.gather(hold(), waiter())
            return True

        assert asyncio.run(run()) is True

    def test_timeout_does_not_leak_slot(self) -> None:
        """超时的请求不能占着信号量，否则池会被逐渐饿死。"""

        async def run() -> int:
            p = PiProcessPool(PoolConfig(size=1, queue_timeout=0.1))

            async def hold() -> None:
                async with p.acquire():
                    await asyncio.sleep(0.5)

            async def waiter() -> None:
                await asyncio.sleep(0.03)
                try:
                    async with p.acquire():
                        return None
                except PoolQueueTimeoutError:
                    return None

            await asyncio.gather(hold(), waiter())
            # 全部结束后池应可用
            async with p.acquire():
                return p.waiting

        assert asyncio.run(run()) == 0


class TestChatServiceQueueEvents:
    """chat_service 要把排队状态与排队超时翻译成前端能懂的事件。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_emits_queued_activity_when_pool_saturated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.agent.models import AgentSession
        from apps.agent.services import chat_service
        from apps.agent.services.event_bus import EventBus

        class _Pool:
            waiting = 2
            saturated = True

            def acquire(self, **kwargs: Any) -> Any:
                class _A:
                    async def __aenter__(self) -> Any:
                        class _S:
                            async def prompt(self, m: str) -> None:
                                return None

                        return _S()

                    async def __aexit__(self, *exc: object) -> bool:
                        return False

                return _A()

        async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
            yield {"type": "delta", "content": "答"}
            yield {"type": "done"}

        async def fake_pool() -> Any:
            return _Pool()

        async def fake_model() -> str | None:
            return None

        monkeypatch.setattr(chat_service, "get_pool", fake_pool)
        monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
        monkeypatch.setattr(chat_service, "stream_events", fake_stream)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

        from asgiref.sync import sync_to_async

        session = await sync_to_async(AgentSession.objects.create)(title="t")
        events = [e async for e in chat_service.stream_chat(session=session, user_message="q", user_id=None)]

        queued = [e for e in events if e.get("status") == "queued"]
        assert len(queued) == 1
        assert queued[0]["position"] == 3  # waiting 2 人 + 自己

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_queue_timeout_becomes_friendly_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """排队超时给「请稍后重试」，不是堆栈也不是英文异常。"""
        from apps.agent.models import AgentSession
        from apps.agent.services import chat_service
        from apps.agent.services.event_bus import EventBus

        class _Pool:
            waiting = 0
            saturated = False

            def acquire(self, **kwargs: Any) -> Any:
                raise PoolQueueTimeoutError("agent 执行位已满，排队超过 60 秒（容量 4）")

        async def fake_pool() -> Any:
            return _Pool()

        async def fake_model() -> str | None:
            return None

        monkeypatch.setattr(chat_service, "get_pool", fake_pool)
        monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

        from asgiref.sync import sync_to_async

        session = await sync_to_async(AgentSession.objects.create)(title="t")
        events = [e async for e in chat_service.stream_chat(session=session, user_message="q", user_id=None)]

        errors = [e for e in events if e.get("type") == "error"]
        assert errors, "排队超时没有产出 error 事件"
        assert "稍后重试" in errors[0]["message"]
