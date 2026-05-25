"""CDP 连接模式。

通过 connect_over_cdp() 连接已有的 Chrome 实例，适用于需要复用会话或绕过反检测的场景。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from .chrome_process import is_cdp_ready, launch_chrome
from .profiles import BrowserProfile

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger("apps.core")


@asynccontextmanager
async def connect_cdp_browser(
    profile: BrowserProfile,
    *,
    auto_launch: bool = True,
) -> AsyncIterator[tuple[Browser, BrowserContext]]:
    """通过 CDP 连接 Chrome。

    Args:
        profile: 浏览器配置档案（必须有 cdp_url）
        auto_launch: 如果没有运行中的 Chrome，是否自动启动

    Yields:
        (browser, context) 元组
    """
    if not profile.cdp_url:
        raise ValueError("CDP 连接模式需要配置 cdp_url")

    from playwright.async_api import async_playwright

    cdp_url = profile.cdp_url

    # 确保 Chrome 在运行
    if not is_cdp_ready(_extract_port(cdp_url)):
        if auto_launch:
            logger.info("CDP 端点不可用，自动启动 Chrome")
            launch_chrome(port=_extract_port(cdp_url), user_data_dir=profile.user_data_dir)
        else:
            raise RuntimeError(f"CDP 端点不可用: {cdp_url}")

    async with async_playwright() as pw:
        logger.info("通过 CDP 连接 Chrome: %s", cdp_url)
        browser: Browser = await pw.chromium.connect_over_cdp(cdp_url)

        # 获取或创建 context
        contexts = list(browser.contexts)
        if contexts:
            context = contexts[0]
            logger.debug("复用已有 context")
        else:
            context_args = profile.to_context_args()
            context = await browser.new_context(**context_args)
            logger.debug("创建新 context")

        # 设置超时
        context.set_default_timeout(profile.timeout)
        context.set_default_navigation_timeout(profile.navigation_timeout)

        try:
            yield browser, context
        finally:
            # CDP 模式下不关闭 browser（它是外部进程），只关闭 context
            try:
                await context.close()
            except Exception:
                pass
            logger.debug("CDP context 已关闭")


@asynccontextmanager
async def connect_cdp_page(
    profile: BrowserProfile,
    *,
    auto_launch: bool = True,
) -> AsyncIterator[tuple[Page, BrowserContext]]:
    """通过 CDP 连接并返回 (page, context)。

    与 connect_cdp_browser 类似，但返回 Page 而非 Browser。
    """
    async with connect_cdp_browser(profile, auto_launch=auto_launch) as (browser, context):
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()
        yield page, context


def _extract_port(cdp_url: str) -> int:
    """从 CDP URL 中提取端口号。"""
    from urllib.parse import urlparse

    parsed = urlparse(cdp_url)
    return parsed.port or 9222
