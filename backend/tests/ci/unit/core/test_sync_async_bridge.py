"""apps.core.infrastructure.sync_async_bridge 单元测试。

覆盖四类契约：正常返回 / 超时抛 TimeoutError / 协程异常透传 / loop 与连接清理。
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from apps.core.infrastructure.sync_async_bridge import run_coro_sync


def _run_in_loop(coro):
    """在测试线程跑一个显式 loop（用于复现「当前线程已有运行中 loop」的嵌套场景）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestRunCoroSyncBasic:
    def test_returns_coroutine_result(self):
        async def _coro() -> int:
            await asyncio.sleep(0)
            return 42

        assert run_coro_sync(_coro()) == 42

    def test_timeout_raises_timeout_error(self):
        async def _coro() -> None:
            await asyncio.sleep(30)

        with pytest.raises(TimeoutError):
            run_coro_sync(_coro(), timeout=0.05)

    def test_timeout_is_cooperative_cleanup_runs(self):
        """wait_for 超时会协作取消：协程内 finally 有机会执行。"""

        cleaned = []

        async def _coro() -> None:
            try:
                await asyncio.sleep(30)
            finally:
                cleaned.append(True)

        with pytest.raises(TimeoutError):
            run_coro_sync(_coro(), timeout=0.05)
        assert cleaned == [True]

    def test_coroutine_exception_propagates(self):
        async def _coro() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_coro_sync(_coro())

    def test_no_timeout_by_default(self):
        async def _coro() -> str:
            await asyncio.sleep(0.01)
            return "ok"

        assert run_coro_sync(_coro()) == "ok"


class TestRunCoroSyncLoopCleanup:
    def test_no_running_loop_left_in_current_thread(self):
        seen: dict[str, object] = {}

        async def _coro() -> None:
            # 桥内应有运行中 loop（协程能拿到 current_task）
            seen["task"] = asyncio.current_task()

        run_coro_sync(_coro())
        assert seen["task"] is not None
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()

    def test_close_old_connections_called_on_success(self):
        async def _coro() -> None:
            return None

        with patch("apps.core.infrastructure.sync_async_bridge.close_old_connections") as mock_close:
            run_coro_sync(_coro())
        mock_close.assert_called_once_with()

    def test_close_old_connections_called_on_timeout(self):
        async def _coro() -> None:
            await asyncio.sleep(30)

        with patch("apps.core.infrastructure.sync_async_bridge.close_old_connections") as mock_close:
            with pytest.raises(TimeoutError):
                run_coro_sync(_coro(), timeout=0.05)
        mock_close.assert_called_once_with()

    def test_close_old_connections_called_on_exception(self):
        async def _coro() -> None:
            raise RuntimeError("kaput")

        with patch("apps.core.infrastructure.sync_async_bridge.close_old_connections") as mock_close:
            with pytest.raises(RuntimeError):
                run_coro_sync(_coro())
        mock_close.assert_called_once_with()


class TestRunCoroSyncNestedLoop:
    """当前线程已有运行中 loop 时应退到一次性线程（同线程跑第二个 loop 是未定义行为）。"""

    def test_delegates_to_thread_when_loop_running(self):
        seen: dict[str, object] = {}

        async def _inner() -> str:
            seen["inner_loop"] = asyncio.get_running_loop()
            return "nested-ok"

        async def _outer() -> None:
            seen["outer_loop"] = asyncio.get_running_loop()
            # 协程体内同步调用：此刻 outer loop 正在当前线程运行 → 走线程路径
            seen["value"] = run_coro_sync(_inner())

        _run_in_loop(_outer())
        assert seen["value"] == "nested-ok"
        assert seen["inner_loop"] is not seen["outer_loop"]

    def test_thread_path_timeout_raises_timeout_error(self):
        # sleep 用短时长：线程路径超时会丢弃线程不等待其结束，
        # 但解释器退出前仍会 join 非守护线程，30s 会让测试进程挂住。
        async def _inner() -> None:
            await asyncio.sleep(0.3)

        async def _outer() -> None:
            run_coro_sync(_inner(), timeout=0.05)

        with pytest.raises(TimeoutError):
            _run_in_loop(_outer())

    def test_thread_path_passes_exception_through(self):
        async def _inner() -> None:
            raise KeyError("from-thread")

        async def _outer() -> None:
            run_coro_sync(_inner())

        with pytest.raises(KeyError, match="from-thread"):
            _run_in_loop(_outer())
