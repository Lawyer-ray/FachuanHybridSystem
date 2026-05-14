"""浏览器生命周期管理：Chrome 启动、CDP 连接、关闭。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Final

from apps.core.services.browser.chrome_process import is_cdp_ready, kill_chrome, launch_chrome

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext

logger = logging.getLogger("apps.express_query")

_CDP_PORT: Final[int] = 9222
_CDP_URL: Final[str] = f"http://127.0.0.1:{_CDP_PORT}"

_browser_context: BrowserContext | None = None
_chrome_process: Any = None


async def close_browser() -> None:
    global _browser_context, _chrome_process
    if _browser_context is not None:
        try:
            await _browser_context.close()
        except Exception:
            pass
        _browser_context = None
    if _chrome_process is not None:
        kill_chrome(_chrome_process)
        _chrome_process = None
    logger.info("Browser closed")


async def disconnect_playwright() -> None:
    """
    在事件循环关闭前主动断开 Playwright CDP 连接。
    不终止 Chrome 进程，下次可重新 connect_over_cdp 复用。

    解决 asyncio.run() 销毁事件循环后，Playwright 的
    BaseSubprocessTransport.__del__ 触发 "Event loop is closed" 错误。
    """
    global _browser_context
    if _browser_context is not None:
        try:
            # 关闭 context 内所有 page，然后断开 CDP 连接
            browser = _browser_context.browser
            await _browser_context.close()
            if browser is not None:
                await browser.close()
        except Exception:
            pass
        _browser_context = None
    logger.info("Playwright disconnected (Chrome still running for reuse)")


async def ensure_browser() -> BrowserContext:
    """
    Get available browser context (auto-launch Chrome + CDP connect).

    Strategy:
    1. Reuse existing context in current process
    2. Try CDP connect to existing Chrome
    3. Auto-launch Chrome with debug port, then CDP connect

    SF and EMS share the same Chrome window.
    """
    from playwright.async_api import async_playwright

    global _browser_context, _chrome_process

    # Case 1: existing context is alive -> reuse
    if _browser_context is not None and _browser_context.pages:
        try:
            page = await _browser_context.new_page()
            await page.evaluate("1+1")
            await page.close()
            return _browser_context
        except Exception:
            _browser_context = None

    pw = await async_playwright().start()

    # Case 2: try CDP connect to existing Chrome
    browser = await _try_cdp_connect(pw, retries=3, delay=1)
    if browser is not None:
        ctx_list = list(browser.contexts)
        _browser_context = (
            ctx_list[0]
            if ctx_list
            else await browser.new_context(
                viewport={"width": 1440, "height": 900},
            )
        )
        logger.info("Connected to existing Chrome via CDP")
        return _browser_context

    # Case 3: auto-launch Chrome then connect
    # 先清理可能占用端口的旧 Chrome 进程
    kill_chrome(port=_CDP_PORT)
    _launch_chrome_via_util()
    await asyncio.sleep(2)

    browser = await _try_cdp_connect(pw, retries=10, delay=0.5)
    if browser is not None:
        ctx_list2 = list(browser.contexts)
        _browser_context = (
            ctx_list2[0]
            if ctx_list2
            else await browser.new_context(
                viewport={"width": 1440, "height": 900},
            )
        )
        logger.info("Connected to auto-launched Chrome")
        return _browser_context

    raise RuntimeError(
        f"Cannot connect via CDP ({_CDP_URL}) after launching Chrome. Check if Chrome is installed correctly."
    )


async def _try_cdp_connect(
    pw: Any,
    retries: int = 1,
    delay: float = 0,
) -> Browser | None:
    """Try connecting to Chrome via CDP. Returns Browser or None."""
    for attempt in range(retries):
        try:
            browser: Browser = await pw.chromium.connect_over_cdp(_CDP_URL)
            return browser
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    return None


def _launch_chrome_via_util() -> None:
    """Auto-launch Chrome with remote debugging port enabled."""
    global _chrome_process
    _chrome_process = launch_chrome(port=_CDP_PORT)
