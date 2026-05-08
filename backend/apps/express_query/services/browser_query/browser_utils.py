"""通用 Playwright 工具方法。"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page

logger = logging.getLogger("apps.express_query")


async def click_locator_if_visible(locator: Locator, description: str) -> bool:
    """点击 Locator 中第一个可见元素。"""
    try:
        count = await locator.count()
    except Exception:
        return False
    for index in range(min(count, 5)):
        target = locator.nth(index)
        try:
            if not await target.is_visible():
                continue
            await target.scroll_into_view_if_needed()
            await target.click(force=True, timeout=2000)
            logger.info("  Clicked %s", description)
            await asyncio.sleep(1)
            return True
        except Exception:
            continue
    return False


async def fill_first(page: Page, selectors: list[str], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count() == 0:
                continue
            first = locator.first
            await first.click(force=True)
            await first.fill("")
            await first.fill(value)
            return
        except Exception:
            continue
    raise RuntimeError("No input field found")


async def click_first(page: Page, selectors: list[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = await locator.count()
        except Exception:
            continue

        for index in range(min(count, 5)):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.scroll_into_view_if_needed()
                await candidate.click(force=True, timeout=2000)
                return True
            except Exception:
                continue
    return False


async def has_any_visible(page: Page, selectors: list[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = await locator.count()
        except Exception:
            continue
        for index in range(min(count, 3)):
            try:
                if await locator.nth(index).is_visible():
                    return True
            except Exception:
                continue
    return False
