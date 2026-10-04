"""sync→async 桥接统一工具（偶发调用场景的一次性 loop 桥）。

历史上仓库里 sync 上下文调用协程有四种写法并存（语义各异）：

a) 一次性线程 + ``pool.submit(asyncio.run, coro).result(timeout=...)``
   （原 workbench batch_runner）：为「Django-Q worker 线程内偶发跑一个协程」设计；
b) 常驻 daemon 线程 loop + ``run_coroutine_threadsafe``（enterprise_data
   McpToolClient）：为高频 MCP 调用复用 TCP/HTTP 连接设计；
c) 模块级单 worker ``ThreadPoolExecutor`` 跑 **sync 函数**（legal_research
   task_lifecycle 的 ORM 兜底）：本质是 sync 函数排队，不是协程桥；
d) 线程内裸 ``asyncio.run``（oa_filing script_executor / 多处散点）。

本模块收敛 a/d 两类「偶发调用」：统一入口 :func:`run_coro_sync`，语义为
一次性事件循环 + 超时 + Django 连接清理。

刻意不收编的两类：

- b 类（MCP 常驻 loop）：常驻 loop 有显式生命周期管理（进程级单例、
  ``shutdown_persistent_loop``、按调用超时 future），复用连接池是其存在意义，
  一次性 loop 每次重建连接反而退化——保留独立实现，见
  ``apps/enterprise_data/services/clients/mcp_tool_client.py``。
- c 类（task_lifecycle 单 worker 执行器）：排队的是 sync ORM 函数而非协程，
  与协程桥不是同一问题域，见
  ``apps/legal_research/services/executor_components/task_lifecycle.py``。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.db import close_old_connections

logger = logging.getLogger(__name__)

_DEFAULT_THREAD_NAME_PREFIX = "coro-bridge"


def run_coro_sync[T](
    coro: Coroutine[Any, Any, T],
    *,
    timeout: float | None = None,
    thread_name_prefix: str = _DEFAULT_THREAD_NAME_PREFIX,
) -> T:
    """在 sync 上下文中运行协程并返回其结果（偶发调用场景的统一桥）。

    Args:
        coro: 待运行的协程对象（调用方创建，本函数负责消费）。
        timeout: 秒；None 表示不设超时。到期抛 ``TimeoutError``。
        thread_name_prefix: 嵌套场景（当前线程已有运行中 loop）下单次性
            线程的名称前缀，便于排查。

    行为：

    - 当前线程**无**运行中事件循环：``asyncio.run`` 一次性 loop，超时经
      ``wait_for`` 协作取消（协程的 finally 清理有机会执行），退出前
      ``close_old_connections()`` 清理协程内 async ORM 打开的连接。
    - 当前线程**已有**运行中事件循环（如在协程里误用或嵌套桥接）：
      退到一次性线程执行（同线程跑第二个 loop 是未定义行为）。线程路径用
      ``future.result(timeout)`` 做硬超时，超时后 ``shutdown(wait=False,
      cancel_futures=True)`` 丢弃线程不等待其自然结束——否则 wait=True 会把
      超时变成形式超时（workbench batch 旧实现的教训）。

    Raises:
        TimeoutError: 超时到期（wait_for 取消 / future.result 超时）。
        BaseException: 协程内异常原样透传。
    """
    if _has_running_loop():
        return _run_in_oneshot_thread(
            coro,
            timeout=timeout,
            thread_name_prefix=thread_name_prefix,
        )
    try:
        if timeout is not None:
            return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
        return asyncio.run(coro)
    finally:
        close_old_connections()


def _has_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _run_in_oneshot_thread[T](
    coro: Coroutine[Any, Any, T],
    *,
    timeout: float | None,
    thread_name_prefix: str,
) -> T:
    # 不用 with：超时后 with 退出会 shutdown(wait=True) 阻塞到线程自然结束，
    # 使 future.result(timeout=...) 沦为形式超时，这里改为直接丢弃未完成任务。
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_name_prefix)
    try:
        future = pool.submit(_run_coro_and_close_connections, coro)
    except BaseException:
        coro.close()  # submit 失败时协程从未启动，显式关闭避免 never-awaited 告警
        raise
    try:
        return future.result(timeout=timeout)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _run_coro_and_close_connections[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    finally:
        close_old_connections()
