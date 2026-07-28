"""顺丰查询全流程。

选择器已外置到 selectors_config.py，改版时只需更新配置。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final

from .browser_utils import click_first, fill_first, has_any_visible
from .selectors_config import get_sf_config

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("apps.express_query")

SF_HOME_URL: Final[str] = "https://www.sf-express.com/"
SF_QUERY_URL: Final[str] = "https://www.sf-express.com/chn/sc/waybill/list"


def _sf_selectors(key: str) -> list[str]:
    return list(get_sf_config().get("selectors", {}).get(key, []))


async def query_sf(page: Page, tracking_number: str) -> None:  # pragma: no cover
    cfg = get_sf_config()
    home_url = cfg.get("homeUrl", SF_HOME_URL)
    query_url = cfg.get("queryUrl", SF_QUERY_URL)
    login_timeout = cfg.get("timeouts", {}).get("login", 300)

    await page.goto(home_url, wait_until="networkidle")
    await asyncio.sleep(2)
    await _dismiss_sf_overlays(page)

    await click_first(page, _sf_selectors("loginButtons"))

    logger.info("SF page opened, please login in the browser")
    await _wait_for_sf_login(page, timeout_seconds=login_timeout)

    await page.goto(query_url, wait_until="networkidle")
    await asyncio.sleep(3)
    await _dismiss_sf_overlays(page)

    await fill_first(page, _sf_selectors("trackingInputs"), tracking_number)
    if not await click_first(page, _sf_selectors("submitButtons")):
        await page.keyboard.press("Enter")
    await asyncio.sleep(3)

    await _open_sf_waybill_detail(page, tracking_number)


async def _wait_for_sf_login(page: Page, *, timeout_seconds: int = 300) -> None:  # pragma: no cover
    """等待顺丰登录完成（带负守卫）。"""
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    login_selectors = _sf_selectors("loginButtons")
    logged_in_selectors = _sf_selectors("loggedInIndicators")

    while asyncio.get_running_loop().time() < deadline:
        # 负守卫
        if await has_any_visible(page, logged_in_selectors):
            return
        login_visible = await has_any_visible(page, login_selectors)
        if not login_visible:
            return
        await asyncio.sleep(2)


async def _dismiss_sf_overlays(page: Page) -> None:  # pragma: no cover
    close_selectors = _sf_selectors("dismissOverlayButtons")

    logger.info("  Dismissing SF overlays...")
    for _ in range(10):
        closed_any = False

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception:
            pass

        try:
            next_button = page.get_by_role("button", name="下一步")
            if await next_button.count() > 0 and await next_button.first.is_visible():
                await next_button.first.click(force=True, timeout=1500)
                logger.info("  Clicked guide button")
                await asyncio.sleep(0.8)
                closed_any = True
                continue
        except Exception:
            pass

        try:
            agree_button = page.get_by_role("button", name="同意")
            if await agree_button.count() > 0 and await agree_button.first.is_visible():
                await agree_button.first.click(force=True, timeout=1500)
                logger.info("  Clicked agree button")
                await asyncio.sleep(0.8)
                closed_any = True
        except Exception:
            pass

        for selector in close_selectors:
            if await click_first(page, [selector]):
                logger.info("  Clicked overlay control: %s", selector)
                await asyncio.sleep(0.5)
                closed_any = True

        try:
            overlay_boxes = await page.evaluate("""() => Array.from(document.querySelectorAll('body *'))
                .map((element) => {
                    const htmlElement = element;
                    const style = window.getComputedStyle(htmlElement);
                    const rect = htmlElement.getBoundingClientRect();
                    return {
                        position: style.position,
                        zIndex: Number(style.zIndex || '0'),
                        width: rect.width,
                        height: rect.height,
                        left: rect.left,
                        top: rect.top,
                        right: rect.right,
                    };
                })
                .filter((item) =>
                    item.position === 'fixed' &&
                    item.zIndex >= 10 &&
                    item.width >= 180 &&
                    item.height >= 80 &&
                    item.top >= 0
                )
                .slice(0, 6)""")
            for box in overlay_boxes:
                try:
                    await page.mouse.click(box["right"] - 18, box["top"] + 18)
                    logger.info("  Clicked overlay corner")
                    await asyncio.sleep(0.5)
                    closed_any = True
                except Exception:
                    pass
        except Exception:
            pass

        try:
            await page.evaluate("""() => {
                    document.querySelectorAll('.mask').forEach((element) => {
                        element.classList.remove('mask');
                        element.style.pointerEvents = 'auto';
                    });
                    document.querySelectorAll('[class*="mask"]').forEach((element) => {
                        element.style.pointerEvents = 'none';
                    });
                    document.querySelectorAll('input, button, a').forEach((element) => {
                        element.style.pointerEvents = 'auto';
                    });
                }""")
        except Exception:
            pass

        if not closed_any:
            break


async def _open_sf_waybill_detail(page: Page, tracking_number: str) -> None:  # pragma: no cover
    logger.info("Opening SF waybill detail: %s", tracking_number)

    detail_button_selectors = _sf_selectors("detailButtons")
    verification_selectors = _sf_selectors("verificationSelectors")
    expand_selectors = _sf_selectors("expandButtons")

    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        await _dismiss_sf_overlays(page)

        detail_opened = False
        for selector in detail_button_selectors:
            if await click_first(page, [selector]):
                logger.info("  Clicked expand detail: %s", selector)
                await asyncio.sleep(2)
                detail_opened = True
                break

        if not detail_opened:
            try:
                clicked = await page.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('body *'));
                    for (const element of elements) {
                        const text = (element.innerText || '').trim();
                        if (!text || !text.includes('展开详情')) {
                            continue;
                        }
                        let current = element;
                        while (current) {
                            if (
                                current.tagName === 'A' ||
                                current.tagName === 'BUTTON' ||
                                current.getAttribute('role') === 'button' ||
                                current.onclick ||
                                current.className?.toString().includes('item') ||
                                current.className?.toString().includes('card')
                            ) {
                                current.click();
                                return true;
                            }
                            current = current.parentElement;
                        }
                    }
                    return false;
                }""")
                if clicked:
                    logger.info("  Clicked expand detail via DOM search")
                    await asyncio.sleep(2)
                    detail_opened = True
            except Exception:
                pass

        if detail_opened:
            for selector in expand_selectors:
                if await click_first(page, [selector]):
                    await asyncio.sleep(1)

        for selector in verification_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    logger.info("  Detail confirmed: %s", selector)
                    return
            except Exception:
                pass

        await asyncio.sleep(1)

    raise RuntimeError("SF detail expansion failed: %s" % tracking_number)
