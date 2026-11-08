"""浏览器生命周期管理：通过 CloakBrowser 统一启动。

快递查询需要保持 EMS / 顺丰的登录态，实现方式：

**Cookie 落盘持久化**：``express`` profile 配置了 ``user_data_dir``，
Cookie 写入磁盘，进程重启后仍能恢复登录态。

⚠️ 设计约束（踩过的坑，务必保留）：

- Django-Q 每个任务用 ``asyncio.run()``，**每次新建并销毁事件循环**。
  ``asyncio.run()`` 收尾会 ``_cancel_all_tasks`` + ``shutdown_asyncgens``——
  只要还有存活的 async generator 或永不结束的后台任务，收尾就会**永久阻塞**，
  表现为任务卡在「查询中」直到 600s 被 worker 杀掉。

- ``create_browser_async`` 是 ``@asynccontextmanager``（async generator）。
  **绝不能**跨 ``asyncio.run()`` 边界持有它：旧循环销毁后，其 ``__aexit__``
  会因底层 Playwright 连接已死而卡住，且 ``asyncio.wait_for`` 无法中断
  （Playwright 吞掉取消信号），反而把 generator 留在半开状态，
  导致下一次 ``Runner.close()`` 卡在 ``shutdown_asyncgens()``。

- 因此：浏览器必须在**同一个** ``asyncio.run()`` 内启动并关闭。
  进程内复用在跨循环场景下没有意义，已移除。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger("apps.express_query")

#: 快递查询统一使用的 profile（持久化 user_data_dir + 有头模式）
EXPRESS_PROFILE: str = "express"


async def notify_browser_closed() -> None:  # pragma: no cover
    """兼容旧接口：浏览器生命周期已由 ``query_and_save_pdf`` 自管理。

    保留此函数是为了不破坏 ``tasks.py`` 与 ``service.py`` 中的既有调用点；
    当前无需做任何清理，浏览器已在协程退出时关闭。
    """
    logger.debug("notify_browser_closed: browser lifetime is self-managed, nothing to do")


async def disconnect_playwright() -> None:  # pragma: no cover
    """兼容旧接口，语义同 ``notify_browser_closed``。"""
    await notify_browser_closed()


async def close_browser() -> None:  # pragma: no cover
    """兼容旧接口，语义同 ``notify_browser_closed``。"""
    await notify_browser_closed()
