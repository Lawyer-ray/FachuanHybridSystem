"""Unit tests for TaskRegistry."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from apps.workbench.tasks.registry import TaskRegistry


@pytest.fixture
def registry() -> TaskRegistry:
    return TaskRegistry()


class TestTaskRegistry:
    def test_register_and_get(self, registry) -> None:
        loop = asyncio.new_event_loop()

        async def dummy() -> None:
            pass

        task = loop.create_task(dummy())
        registry.register("job-1", task)
        assert registry.get("job-1") is task
        task.cancel()
        # 关 loop 前把 cancel 跑完，否则任务以 pending 状态被销毁，
        # asyncio 会往共享 error.log 写 "Task was destroyed but it is pending"
        with contextlib.suppress(asyncio.CancelledError):
            loop.run_until_complete(task)
        loop.close()

    def test_get_nonexistent_returns_none(self, registry) -> None:
        assert registry.get("nonexistent") is None

    def test_unregister(self, registry) -> None:
        loop = asyncio.new_event_loop()

        async def dummy() -> None:
            pass

        task = loop.create_task(dummy())
        registry.register("job-2", task)
        registry.unregister("job-2")
        assert registry.get("job-2") is None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            loop.run_until_complete(task)
        loop.close()

    def test_unregister_nonexistent_no_error(self, registry) -> None:
        # 移除不存在的任务应静默 no-op（返回 None，不抛 KeyError）
        assert registry.unregister("nonexistent") is None
        assert registry._tasks.get("nonexistent") is None

    def test_cancel_running_task(self, registry) -> None:
        loop = asyncio.new_event_loop()

        async def long_running() -> None:
            await asyncio.sleep(100)

        task = loop.create_task(long_running())
        registry.register("job-3", task)
        result = registry.cancel("job-3")
        assert result is True
        # task.cancel() was called, but it needs an event loop tick to process
        assert task.cancelling() > 0
        with contextlib.suppress(asyncio.CancelledError):
            loop.run_until_complete(task)
        loop.close()

    def test_cancel_already_done_task(self, registry) -> None:
        loop = asyncio.new_event_loop()

        async def immediate() -> None:
            pass

        task = loop.create_task(immediate())
        loop.run_until_complete(task)
        registry.register("job-4", task)
        result = registry.cancel("job-4")
        assert result is False
        loop.close()

    def test_cancel_nonexistent_returns_false(self, registry) -> None:
        result = registry.cancel("nonexistent")
        assert result is False
