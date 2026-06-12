"""浏览器生命周期管理：通过 CloakBrowser 统一启动。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger("apps.express_query")

# 模块级缓存：复用 BrowserContext 跨多次快递查询
_context: BrowserContext | None = None
_context_manager: object | None = None


@asynccontextmanager
async def _get_browser_context() -> AsyncIterator[tuple[Page, BrowserContext]]:  # pragma: no cover
    """通过 CloakBrowser 获取浏览器上下文（自动管理生命周期）。"""
    from apps.core.services.browser import create_browser_async

    async with create_browser_async("default") as (page, context):
        yield page, context


async def close_browser() -> None:  # pragma: no cover
    """关闭缓存的浏览器上下文。"""
    global _context, _context_manager
    if _context is not None:
        try:
            await _context.close()
        except Exception:
            pass
        _context = None
    if _context_manager is not None:
        try:
            _context_manager.__aexit__(None, None, None)  # type: ignore[union-attr]
        except Exception:
            pass
        _context_manager = None
    logger.info("Browser closed")


async def disconnect_playwright() -> None:  # pragma: no cover
    """断开浏览器连接（兼容旧接口）。"""
    await close_browser()


async def ensure_browser() -> BrowserContext:  # pragma: no cover
    """
    获取可用的浏览器上下文。

    策略：通过 CloakBrowser 统一启动，自动管理反检测。
    """
    global _context

    # 复用现有上下文
    if _context is not None:
        try:
            page = await _context.new_page()
            await page.evaluate("1+1")
            await page.close()
            return _context
        except Exception:
            _context = None

    # 通过 CloakBrowser 启动新浏览器
    from apps.core.services.browser import create_browser_async

    cm = create_browser_async("default")
    page, context = await cm.__aenter__()
    _context = context

    # 保存 context_manager 以便后续清理
    global _context_manager
    _context_manager = cm

    logger.info("Browser launched via CloakBrowser")
    return _context
