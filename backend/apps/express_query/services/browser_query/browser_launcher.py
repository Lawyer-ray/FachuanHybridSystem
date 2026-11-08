"""浏览器生命周期管理：通过 CloakBrowser 统一启动。

快递查询需要保持 EMS / 顺丰的登录态，因此这里采用两层持久化：

1. **落盘持久化**：``express`` profile 配置了 ``user_data_dir``，Cookie 写入磁盘，
   进程重启后仍能恢复登录态（不依赖内存缓存）。
2. **进程内复用**：模块级缓存浏览器上下文，同一 worker 进程内的连续任务复用同一窗口，
   避免每次查询都重新启动浏览器、重新走登录检测。

注意：``close_browser()`` 只关闭窗口、不清除 ``user_data_dir``，
所以关闭后下次启动依然是已登录状态。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger("apps.express_query")

#: 快递查询统一使用的 profile（持久化 user_data_dir + 有头模式）
EXPRESS_PROFILE: str = "express"

# 模块级缓存：复用 BrowserContext 跨多次快递查询（保留登录态）
_context: BrowserContext | None = None
_context_manager: object | None = None
# 记录上下文所属的事件循环：Django-Q 任务用 asyncio.run() 每次新建循环，
# 旧循环销毁后上下文不可再用，必须检测并重建。
_context_loop: asyncio.AbstractEventLoop | None = None


@asynccontextmanager
async def _get_browser_context() -> AsyncIterator[tuple[Page, BrowserContext]]:  # pragma: no cover
    """通过 CloakBrowser 获取浏览器上下文（自动管理生命周期）。"""
    from apps.core.services.browser import create_browser_async

    async with create_browser_async(EXPRESS_PROFILE) as (page, context):
        yield page, context


async def close_browser() -> None:  # pragma: no cover
    """关闭缓存的浏览器上下文（保留 user_data_dir 中的登录态）。"""
    global _context, _context_manager, _context_loop
    if _context is not None:
        try:
            await _context.close()
        except Exception:
            logger.debug("关闭浏览器上下文失败（已忽略）", exc_info=True)
            pass
        _context = None
    if _context_manager is not None:
        try:
            await _context_manager.__aexit__(None, None, None)  # type: ignore[attr-defined]
        except Exception:
            logger.debug("退出浏览器上下文管理器失败（已忽略）", exc_info=True)
            pass
        _context_manager = None
    _context_loop = None
    logger.info("Browser closed (login state kept in user_data_dir)")


async def disconnect_playwright() -> None:  # pragma: no cover
    """断开浏览器连接（兼容旧接口）。"""
    await close_browser()


async def ensure_browser() -> BrowserContext:  # pragma: no cover
    """
    获取可用的浏览器上下文。

    策略：通过 CloakBrowser 统一启动 ``express`` profile（持久化登录态），
    并优先复用进程内已存在的上下文。
    """
    global _context, _context_manager, _context_loop

    current_loop = asyncio.get_running_loop()

    # 跨事件循环的缓存不可用：asyncio.run() 每次新建并销毁循环，
    # 旧循环上的上下文已死，直接丢弃（Cookie 已落盘，重建后仍是登录态）。
    if _context is not None and _context_loop is not current_loop:
        logger.info("Event loop changed, dropping cached browser context")
        _context = None
        _context_manager = None

    # 复用现有上下文（登录态在内存里，无需重新扫码）
    if _context is not None:
        try:
            probe = await _context.new_page()
            await probe.evaluate("1+1")
            await probe.close()
            return _context
        except Exception:
            logger.info("Cached browser context is stale, relaunching")
            try:
                await _context.close()
            except Exception:
                logger.debug("关闭失效上下文失败（已忽略）", exc_info=True)
            _context = None
            _context_manager = None

    # 通过 CloakBrowser 启动新浏览器（express profile 已是持久化 + 有头）
    from apps.core.services.browser import create_browser_async

    cm = create_browser_async(EXPRESS_PROFILE)
    page, context = await cm.__aenter__()
    try:
        await page.close()
    except Exception:
        logger.debug("关闭启动用临时页面失败（已忽略）", exc_info=True)

    _context = context
    _context_manager = cm
    _context_loop = current_loop

    logger.info("Browser launched via CloakBrowser (profile=%s, persistent)", EXPRESS_PROFILE)
    return _context
