"""run_startup_db_sync：把 AppConfig.ready() 里的 sync ORM 摆渡出事件循环线程。

## 为什么要有这个测试

ASGI（uvicorn）进程里 ``get_asgi_application()`` 在事件循环线程构造，
``AppConfig.ready()`` 随之在该线程执行。此时 sync ORM 会抛
``SynchronousOnlyOperation: You cannot call this from an async context``：

- ``apps/agent`` 把异常冒成 warning（日志可见）；
- ``apps/core`` / ``apps/pdf_splitting`` 吞成 debug——文件清理、看门狗、
  行为推断三条定时任务在 ASGI 部署下**静默不注册**。

这个测试锁死「有事件循环时必须在别的线程执行」这条契约，并覆盖
thread-sensitive 嵌套（最容易踩死的场景）。
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from asgiref.sync import sync_to_async

from apps.core.utils.startup_db import run_startup_db_sync


def test_sync_context_runs_inline() -> None:
    """无事件循环（manage.py / wsgi / worker）：就地执行，不开线程。"""
    caller = threading.get_ident()

    assert run_startup_db_sync(threading.get_ident) == caller


def test_async_context_runs_off_loop_thread() -> None:
    """有事件循环：必须换线程执行，否则 sync ORM 会抛 SynchronousOnlyOperation。"""

    async def _main() -> tuple[int, int]:
        loop_thread = threading.get_ident()
        return loop_thread, run_startup_db_sync(threading.get_ident)

    loop_thread, work_thread = asyncio.run(_main())
    assert work_thread != loop_thread


def test_async_context_propagates_value_and_repeatable() -> None:
    """返回值透传；同一循环内可反复调用（不能有 asgiref 的死锁/重入问题）。"""

    async def _main() -> list[int]:
        return [run_startup_db_sync(lambda: i) for i in range(3)]

    assert asyncio.run(_main()) == [0, 1, 2]


def test_async_context_reraises_original_exception() -> None:
    """异常原样上抛（含类型），否则 ready() 的失败会被误判为成功。"""

    def _boom() -> None:
        raise ValueError("boom")

    async def _main() -> None:
        run_startup_db_sync(_boom)

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(_main())


def test_callable_from_thread_sensitive_worker() -> None:
    """在 thread-sensitive 线程里再调用也不能自锁。

    这正是 ``async_to_sync(sync_to_async(..., thread_sensitive=True))`` 会死锁
    的场景；独立线程方案不受影响。
    """

    async def _main() -> int:
        return await sync_to_async(run_startup_db_sync, thread_sensitive=True)(lambda: 42)

    assert asyncio.run(_main()) == 42


def test_concurrent_calls_do_not_serialize_into_deadlock() -> None:
    """并发的 ready() 级调用各自跑完（每个调用一个一次性线程，互不争锁）。"""

    async def _main() -> list[int]:
        return list(await asyncio.gather(*(asyncio.to_thread(run_startup_db_sync, lambda: 7) for _ in range(4))))

    assert asyncio.run(_main()) == [7, 7, 7, 7]
