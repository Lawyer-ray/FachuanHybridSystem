"""顺丰查询全流程。"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final

from .browser_utils import click_first, fill_first

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("apps.express_query")

SF_HOME_URL: Final[str] = "https://www.sf-express.com/"
SF_QUERY_URL: Final[str] = "https://www.sf-express.com/chn/sc/waybill/list"


async def query_sf(page: Page, tracking_number: str) -> None:
    await page.goto(SF_HOME_URL, wait_until="networkidle")
    await asyncio.sleep(2)
    await _dismiss_sf_overlays(page)

    await click_first(
        page,
        [
            "button:has-text('登录')",
            "a:has-text('登录')",
            ".login-btn",
        ],
    )

    logger.info("SF page opened, please login in the browser")
    await _wait_for_sf_login(page)

    await page.goto(SF_QUERY_URL, wait_until="networkidle")
    await asyncio.sleep(3)
    await _dismiss_sf_overlays(page)

    await fill_first(
        page,
        [
            "input[placeholder*='查询']",
            "input[type='text']",
        ],
        tracking_number,
    )
    if not await click_first(page, ["button:has-text('查')", "button.search-icon"]):
        await page.keyboard.press("Enter")
    await asyncio.sleep(3)

    await _open_sf_waybill_detail(page, tracking_number)


async def _wait_for_sf_login(page: Page) -> None:
    from .browser_utils import has_any_visible

    login_selectors = ["button:has-text('登录')", "a:has-text('登录')"]
    user_selectors = ["[class*='user']", "[class*='avatar']", "text=退出登录"]
    timeout_seconds = 300

    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while asyncio.get_running_loop().time() < deadline:
        login_visible = await has_any_visible(page, login_selectors)
        user_visible = await has_any_visible(page, user_selectors)
        if user_visible or not login_visible:
            return
        await asyncio.sleep(2)


async def _dismiss_sf_overlays(page: Page) -> None:
    close_selectors = [
        ".guide-close",
        ".driver-close-btn",
        "[class*='guide'] [class*='close']",
        "[class*='tour'] [class*='close']",
        "[class*='mask'] [class*='close']",
        "button[class*='skip']",
        "button:has-text('下一步')",
        "button:has-text('完成')",
        "button:has-text('跳过')",
        "button:has-text('知道了')",
        "button:has-text('我知道了')",
        "button:has-text('关闭')",
        "button:has-text('暂不')",
        "button:has-text('同意')",
        "span:has-text('下一步')",
        "span:has-text('完成')",
        "span:has-text('同意')",
        ".el-dialog__close",
        ".el-message-box__close",
    ]

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


async def _open_sf_waybill_detail(page: Page, tracking_number: str) -> None:
    logger.info("Opening SF waybill detail: %s", tracking_number)

    detail_button_selectors = [
        "button:has-text('展开详情')",
        "[role='button']:has-text('展开详情')",
        "span:has-text('展开详情')",
        "text=展开详情",
        "button:has-text('查看详情')",
    ]
    verification_selectors = [
        "text=收起详情",
        "text=物流轨迹",
        "text=签收时间",
        "text=签收详情",
        "text=收方",
        "text=寄方",
    ]

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
            expand_selectors = [
                "button:has-text('展开全部轨迹')",
                "span:has-text('展开全部轨迹')",
                "button:has-text('展开全部')",
                "span:has-text('展开全部')",
                "button:has-text('查看全部')",
                "span:has-text('查看全部')",
                "button:has-text('查看更多')",
                "span:has-text('查看更多')",
                "button:has-text('展开')",
                "span:has-text('展开')",
            ]
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
