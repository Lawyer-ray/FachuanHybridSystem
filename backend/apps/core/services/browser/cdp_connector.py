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
    import asyncio

    from .chrome_process import is_cdp_ready, launch_chrome

    chrome_process = None
    # S30-32（2026-11-23 二轮审计）：原实现直接在 async 函数里调同步的
    # is_cdp_ready() / launch_chrome()（httpx 同步探测 timeout=2s + subprocess.Popen +
    # launch_chrome 内部 15×(sleep 1s + 探测 2s)），最坏 15~45s 把整个事件循环卡停，
    # 同进程的其它协程（SSE / 其它视图）全部停摆。→ 现在用 asyncio.to_thread 移到线程池，
    # chrome_process 里的同步实现保持不变（CLI 复用）。
    if not await asyncio.to_thread(is_cdp_ready, port):
        logger.info("CDP 端口 %d 未就绪，自动启动 Chrome...", port)
        chrome_process = await asyncio.to_thread(launch_chrome, port=port)

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
            logger.debug("CDP 关闭浏览器失败（已忽略）", exc_info=True)
        try:
            # S30-31（2026-11-23 二轮审计）：原实现写 ``await pw.__aexit__(...)``，但
            # async_playwright().__aenter__() 返回的是 Playwright 实例（基类 AsyncBase），
            # 它上面没有 __aexit__，驱动清理函数挂在 ``pw.stop`` 上——每次退出都
            # AttributeError 被 debug 吞掉，playwright driver（node）进程因此永不回收。
            # → 现在调公开 API ``pw.stop()``。
            await pw.stop()
        except Exception:
            logger.warning("CDP 退出 Playwright 失败（driver 可能未回收）", exc_info=True)
        # 清理自动启动的 Chrome 进程（同步实现含 process.wait(timeout=5)，同样不能卡事件循环）
        if chrome_process is not None:
            from .chrome_process import kill_chrome

            await asyncio.to_thread(kill_chrome, chrome_process)
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
