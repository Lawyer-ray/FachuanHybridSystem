"""Boot-time DB sync utilities.

两个职责，都在 ``AppConfig.ready()`` 的启动同步路径上：

1. ``allow_startup_db()``：抑制 Django 6.1 的
   ``Accessing the database during app initialization is discouraged``
   RuntimeWarning。

Django 6.1 raises ``Accessing the database during app initialization is
discouraged`` for any DB query executed while the app registry is not yet ready.

Some boot-time routines are intentionally idempotent and *must* run on every
process start (e.g. django-q schedule registration, OAuth device-code poll
recovery). They cannot be moved out of ``AppConfig.ready()``, so they need the
DB connection during initialization. This context manager scopes the warning
suppression to exactly those call sites instead of silencing it globally.

2. ``run_startup_db_sync()``：把必须在事件循环线程外执行的 sync ORM 摆渡出去。

## 为什么需要第 2 个（2026-11-17 的真实故障）

ASGI 进程（uvicorn）里 ``get_asgi_application()`` 在事件循环线程构造，
``AppConfig.ready()`` 随之在**事件循环线程**里跑。此时任何 sync ORM 都会抛
``SynchronousOnlyOperation``：

    django.core.exceptions.SynchronousOnlyOperation:
    You cannot call this from an async context - use a thread or sync_to_async.

受害的不止一个 app，凡是「ready() 里查调度表」的都在劫难逃：

- ``apps/agent``：异常冒到 ``logger.warning("记忆定时任务注册失败")``，日志可见；
- ``apps/core`` / ``apps/pdf_splitting``：被 except 吞成 debug，于是
  「已注册定时任务」**从来没出现过**，行为推断、看门狗、文件清理三条定时
  任务在 ASGI 部署下静默不注册——比报错更糟。

## 为什么不用 ``allow_async_unsafe()``

``apps.core.infrastructure.async_context`` 里有临时放行 ``DJANGO_ALLOW_ASYNC_UNSAFE``
的开关，但它会让 sync ORM 直接在事件循环线程里阻塞执行（每个查询期间整个
ASGI 进程停摆），且其模块 docstring 明确写「新代码禁止使用」。启动期只有几次
查询，摆渡到一个工作线程的代价可以忽略，语义也正确。

## 为什么是独立线程 + join，而不是 ``sync_to_async``

这里是**同步函数**（``ready()`` 返回 ``None``，不能 ``await``），所以只能在
事件循环线程里「同步地等」。``async_to_sync`` 组合的两种写法都不成立：

- ``async_to_sync(sync_to_async(fn))()``：同线程嵌套会直接在
  ``AsyncToSync.__call__`` 里抛 ``RuntimeError: You cannot use AsyncToSync in
  the same thread as an async event loop``；``thread_sensitive=True`` 更糟，
  它会复用当前循环线程的 executor，等价于在事件循环线程里跑 sync ORM。
- ``asyncio.to_thread`` / ``sync_to_async``：都是 await 语义，拿不到返回值。

独立线程是唯一既正确又不会死锁的选择：它不在事件循环里（不触发
``SynchronousOnlyOperation``），也不占用 asgiref 的 thread-sensitive executor
（因此可以从 thread-sensitive 线程里再调用，不会自锁）。阻塞事件循环最长
等于一次查询的耗时，与 ``get_asgi_application()`` 本身同步构造的代价同量级。

无事件循环线程时（``manage.py``、wsgi、django-q worker、pytest）直接调用，
不引入任何线程开销。
"""

from __future__ import annotations

import asyncio
import threading
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager

_DJANGO_STARTUP_DB_MSG = "Accessing the database during app initialization is discouraged"


@contextmanager
def allow_startup_db() -> Iterator[None]:
    """Temporarily suppress the startup-DB RuntimeWarning for intentional boot syncs."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=_DJANGO_STARTUP_DB_MSG, category=RuntimeWarning)
        yield


def run_startup_db_sync[T](func: Callable[[], T]) -> T:
    """在**非事件循环线程**执行 ``func``，返回其结果（异常原样上抛）。

    用于 ``AppConfig.ready()`` 这类同步启动钩子：ASGI 部署下它们跑在事件循环
    线程里，直接调 sync ORM 会抛 ``SynchronousOnlyOperation``。

    - 无运行中的事件循环 → 就地调用（零开销，覆盖 manage.py / wsgi / worker /
      pytest）。
    - 有运行中的事件循环 → 起一个一次性线程跑完再 join。不占用 asgiref 的
      thread-sensitive executor，所以在上层已持有 thread-sensitive 线程时再调用
      也不会死锁。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return func()

    box: dict[str, object] = {}

    def _target() -> None:
        try:
            box["value"] = func()
        # BaseException：ready() 里漏出的 KeyboardInterrupt 也要带回主线程
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=_target, name="startup-db-sync", daemon=True)
    thread.start()
    thread.join()

    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("value")  # type: ignore[return-value]
