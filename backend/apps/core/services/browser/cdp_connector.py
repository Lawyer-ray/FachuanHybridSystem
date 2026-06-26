"""Playwright CDP 直连模式。

通过 Playwright 原生 connect_over_cdp() 连接已运行的 Chrome 实例，
不使用 CloakBrowser，避免 GSXT 等网站检测自动化浏览器特征。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from .profiles import BrowserProfile

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

logger = logging.getLogger("apps.core")


@asynccontextmanager
async def connect_cdp_browser(  # pragma: no cover
    profile: BrowserProfile,
    *,
    auto_launch: bool = True,
) -> AsyncIterator[tuple[Browser, BrowserContext]]:
    """通过 Playwright 原生 CDP 连接已运行的 Chrome 实例。

    Args:
        profile: 浏览器配置档案（必须设置 cdp_url）
        auto_launch: 保留参数（兼容接口）

    Yields:
        (browser, context) 元组
    """
    from playwright.async_api import async_playwright

    if not profile.cdp_url:
        raise ValueError("CDP 模式需要设置 profile.cdp_url")

    # 从 cdp_url 中提取端口
    import re
    port_match = re.search(r":(\d+)$", profile.cdp_url)
    port = int(port_match.group(1)) if port_match else 9222

    # 如果 CDP 端口未就绪，自动启动 Chrome
    from .chrome_process import is_cdp_ready, launch_chrome
    chrome_process = None
    if not is_cdp_ready(port):
        logger.info("CDP 端口 %d 未就绪，自动启动 Chrome...", port)
        chrome_process = launch_chrome(port=port)

    pw = await async_playwright().__aenter__()
    browser: Browser | None = None
    context: BrowserContext | None = None

    try:
        browser = await pw.chromium.connect_over_cdp(profile.cdp_url)
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
        else:
            context = await browser.new_context()

        context.set_default_timeout(profile.timeout)
        context.set_default_navigation_timeout(profile.navigation_timeout)

        logger.info("Playwright CDP 已连接 (profile=%s, cdp_url=%s)", profile.name, profile.cdp_url)
        yield browser, context

    except Exception:
        logger.exception("Playwright CDP 连接失败 (profile=%s)", profile.name)
        raise
    finally:
        try:
            if browser:
                await browser.close()
        except Exception:
            pass
        try:
            await pw.__aexit__(None, None, None)
        except Exception:
            pass
        # 清理自动启动的 Chrome 进程
        if chrome_process is not None:
            from .chrome_process import kill_chrome
            kill_chrome(chrome_process)
        logger.debug("Playwright CDP 已断开")


@asynccontextmanager
async def connect_cdp_page(  # pragma: no cover
    profile: BrowserProfile,
    *,
    auto_launch: bool = True,
) -> AsyncIterator[tuple[Page, BrowserContext]]:
    """通过 Playwright CDP 连接并返回 (page, context)。"""
    async with connect_cdp_browser(profile, auto_launch=auto_launch) as (browser, context):
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()

        # dialog 处理
        page.on("dialog", lambda d: d.accept())

        yield page, context
