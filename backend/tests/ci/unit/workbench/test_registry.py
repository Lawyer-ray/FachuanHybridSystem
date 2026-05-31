"""Unit tests for TaskRegistry."""

from __future__ import annotations

import asyncio

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
        loop.close()

    def test_unregister_nonexistent_no_error(self, registry) -> None:
        registry.unregister("nonexistent")  # Should not raise

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
