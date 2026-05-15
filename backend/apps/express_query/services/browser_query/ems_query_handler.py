"""EMS 查询流程。"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final

from .browser_utils import click_first, fill_first

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("apps.express_query")

EMS_HOME_URL: Final[str] = "https://www.11183.com.cn/"
EMS_QUERY_URL: Final[str] = "https://www.11183.com.cn/?to=%2Fquery_express_delivery"


async def query_ems(page: Page, tracking_number: str) -> None:
    """
    EMS 查询主流程：
    1. 用 ?to= 进入（未登录时自动弹登录框）
    2. 检测登录状态：未登录→处理协议+等待扫码；已登录→跳过
    3. 导航到干净的 query_express_delivery 页面（不含 ?to=）
    4. 输入单号搜索 + 打开详情
    """
    from .ems_auth_handler import ems_handle_agreement_and_wait, ems_click_login_button, is_ems_dialog_visible

    context = page.context
    _clean_query_url: str = "https://www.11183.com.cn/query_express_delivery"

    # ===== 阶段1: 进入页面（?to= 触发登录弹窗）=====
    await page.goto(EMS_QUERY_URL, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        logger.info("EMS networkidle timeout, continuing")
    await asyncio.sleep(2)

    # ===== 阶段2: 检测并处理登录状态 =====
    dialog_showing = await is_ems_dialog_visible(page)
    if dialog_showing:
        logger.info("EMS login dialog auto-showed (via ?to=), no button click needed")
    else:
        logger.info("Login dialog not visible, clicking 登录/注册...")
        clicked = await ems_click_login_button(page)
        if clicked:
            await asyncio.sleep(1.5)
            if not await is_ems_dialog_visible(page):
                logger.info("Dialog still not showing, re-clicking...")
                await ems_click_login_button(page)
                await asyncio.sleep(1)
        else:
            logger.warning("Failed to click login button")

    # ===== 阶段3: 判断是否已登录，否则处理协议 + 等待扫码 =====
    if not await is_ems_dialog_visible(page):
        body_text = ""
        try:
            body_text = (await page.locator("body").text_content()) or ""
        except Exception:
            pass
        _logged_in_keywords = ("退出", "我的EMS", "个人中心", "我的快递")
        if any(kw in body_text for kw in _logged_in_keywords):
            logger.info("EMS user already logged in, skipping login flow")
        else:
            logger.info("Starting EMS agreement handling + login wait...")
            await ems_handle_agreement_and_wait(context, page, timeout_seconds=300)
    else:
        logger.info("Starting EMS agreement handling + login wait...")
        await ems_handle_agreement_and_wait(context, page, timeout_seconds=300)

    # ===== 阶段4: 导航到干净查询页（不含 ?to=）再操作 =====
    current_url_lower = page.url.lower()
    if (
        "personal_center" in current_url_lower
        or "query_express_delivery" not in current_url_lower
        or "?to=" in page.url
    ):
        logger.info("Navigating to clean query page: %s", _clean_query_url)
        await page.goto(_clean_query_url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2)

    await _dismiss_ems_overlays(page)

    await fill_first(
        page,
        [
            "input[placeholder*='邮件号']",
            "input[placeholder*='搜索']",
            "input[type='search']",
            "input[type='text']",
        ],
        tracking_number,
    )

    if not await click_first(
        page,
        [
            "button:has-text('搜索')",
            "button:has-text('查询')",
            "button:has-text('查件')",
        ],
    ):
        await page.keyboard.press("Enter")
    await asyncio.sleep(3)

    await _open_ems_waybill_detail(page, tracking_number)


async def _dismiss_ems_overlays(page: Page) -> None:
    close_selectors = [
        "button:has-text('知道了')",
        "button:has-text('我知道了')",
        "button:has-text('同意')",
        "button:has-text('关闭')",
        "button:has-text('跳过')",
        "button:has-text('稍后')",
        "button:has-text('确定')",
        "span:has-text('关闭')",
        "span:has-text('知道了')",
        ".close-btn",
        ".icon-close",
        "[class*='dialog'] [role='button']",
        "[class*='popup'] [role='button']",
        "[class*='mask'] [class*='close']",
    ]

    logger.info("  Dismissing EMS popups...")
    for _ in range(8):
        closed_any = False

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
        except Exception:
            pass

        for selector in close_selectors:
            if await click_first(page, [selector]):
                logger.info("  Clicked popup control: %s", selector)
                closed_any = True

        try:
            clicked = await page.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('body *'));
                    for (const element of elements) {
                        const htmlElement = element;
                        const style = window.getComputedStyle(htmlElement);
                        const rect = htmlElement.getBoundingClientRect();
                        // 提高阈值：只关闭真正的大弹窗，避免误点卡片/内容区
                        if (
                            style.position === 'fixed' &&
                            Number(style.zIndex || '0') >= 100 &&
                            rect.width >= 300 &&
                            rect.height >= 200
                        ) {
                            const x = rect.right - 18;
                            const y = rect.top + 18;
                            const target = document.elementFromPoint(x, y);
                            if (target instanceof HTMLElement) {
                                target.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""")
            if clicked:
                logger.info("  Clicked popup corner")
                await asyncio.sleep(0.5)
                closed_any = True
        except Exception:
            pass

        try:
            await page.evaluate("""() => {
                    document.querySelectorAll('[class*="mask"], [class*="overlay"], [class*="modal-bg"]').forEach((element) => {
                        element.style.pointerEvents = 'none';
                    });
                    document.querySelectorAll('button, a, input, textarea, [role="button"]').forEach((element) => {
                        element.style.pointerEvents = 'auto';
                    });
                }""")
        except Exception:
            pass

        if not closed_any:
            break


async def _open_ems_waybill_detail(page: Page, tracking_number: str) -> None:
    """
    EMS 打开详情 + 展开全部轨迹。
    分两步：先进入详情页，再展开全部物流轨迹确保 PDF 内容完整。
    """
    logger.info("Opening EMS mail detail: %s", tracking_number)

    # ---- 阶段1：进入详情页 ----
    detail_button_selectors = [
        "button:has-text('查看详情')",
        "button:has-text('详情')",
        "button:has-text('物流详情')",
        "button:has-text('邮件详情')",
        "button:has-text('收寄详情')",
        "a:has-text('查看详情')",
        "a:has-text('详情')",
    ]
    detail_state_selectors = [
        "text=物流轨迹",
        "text=收寄详情",
        "text=收件人",
        "text=寄件人",
        "text=签收",
        "text=妥投",
    ]

    deadline = asyncio.get_running_loop().time() + 45
    detail_entered = False
    dismiss_count: int = 0

    while asyncio.get_running_loop().time() < deadline:
        if dismiss_count < 3:
            await _dismiss_ems_overlays(page)
            dismiss_count += 1

        # 尝试点击运单号文本
        try:
            await click_first(page, [f"text={tracking_number}"])
        except Exception:
            pass

        # DOM 搜索点击详情按钮
        try:
            clicked_detail_from_dom = await page.evaluate(
                """(trackingNumber) => {
                    const normalizedTarget = String(trackingNumber).replace(/\\s+/g, '');
                    const elements = Array.from(document.querySelectorAll('body *'));
                    for (const element of elements) {
                        const text = String(element.innerText || element.textContent || '').replace(/\\s+/g, '');
                        if (!text || !text.includes(normalizedTarget)) continue;

                        let container = element;
                        for (let depth = 0; depth < 6 && container; depth += 1) {
                            const detailNode = Array.from(container.querySelectorAll('button,a,span,div')).find((node) => {
                                const nodeText = String(node.innerText || node.textContent || '').trim();
                                return /\\u67e5\\u770b\\u8be6\\u60c5|\\u8be6\\u60c5|\\u7269\\u6d41\\u8be6\\u60c5|\\u90ae\\u4ef6\\u8be6\\u60c5|\\u6536\\u5bc4\\u8be6\\u60c5/.test(nodeText);
                            });
                            if (detailNode instanceof HTMLElement) {
                                detailNode.click();
                                return true;
                            }
                            container = container.parentElement;
                        }
                    }
                    return false;
                }""",
                tracking_number,
            )
            if clicked_detail_from_dom:
                detail_entered = True
                logger.info("  Triggered detail click via DOM")
                await asyncio.sleep(2)
        except Exception:
            pass

        if not detail_entered:
            for selector in detail_button_selectors:
                if await click_first(page, [selector]):
                    detail_entered = True
                    logger.info("  Clicked detail button: %s", selector)
                    await asyncio.sleep(2)
                    break

        # 检查是否已进入详情页
        if detail_entered:
            for selector in detail_state_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        logger.info("  EMS detail page confirmed: %s", selector)
                        break
                except Exception:
                    pass
            break

        await asyncio.sleep(1)

    if not detail_entered:
        raise RuntimeError("EMS detail failed: no click triggered for %s" % tracking_number)

    # ---- 阶段2：展开全部物流轨迹 ----
    # EMS 详情页默认只显示部分轨迹，需要点击"展开全部"等按钮才能显示完整轨迹
    await _ems_expand_all_tracking(page)


async def _ems_expand_all_tracking(page: Page) -> None:
    """
    在 EMS 详情页中反复点击"展开全部"类按钮，直到所有物流轨迹都展开。
    EMS 的展开按钮可能不是 <button>，需要用多种选择器尝试。
    """
    # 覆盖所有可能的展开按钮：button / span / div / a
    expand_selectors = [
        # "展开全部" — EMS 最常见的完整展开按钮
        "button:has-text('展开全部')",
        "span:has-text('展开全部')",
        "div:has-text('展开全部')",
        "a:has-text('展开全部')",
        # "展开全部轨迹"
        "button:has-text('展开全部轨迹')",
        "span:has-text('展开全部轨迹')",
        # "查看全部"/"全部轨迹"
        "button:has-text('查看全部')",
        "span:has-text('查看全部')",
        "button:has-text('全部轨迹')",
        "span:has-text('全部轨迹')",
        # "展开"/"查看更多"
        "button:has-text('展开')",
        "span:has-text('展开')",
        "button:has-text('查看更多')",
        "span:has-text('查看更多')",
    ]

    expanded_any = True
    max_rounds = 5  # 最多尝试 5 轮，防止死循环

    for round_num in range(max_rounds):
        if not expanded_any and round_num > 0:
            # 上一轮没有点到任何展开按钮，说明已经全部展开
            logger.info("  EMS tracking fully expanded (no more expand buttons)")
            break

        expanded_any = False

        for selector in expand_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                for idx in range(min(count, 3)):
                    target = locator.nth(idx)
                    try:
                        if await target.is_visible():
                            await target.scroll_into_view_if_needed()
                            await target.click(force=True, timeout=2000)
                            expanded_any = True
                            logger.info("  Clicked expand button: %s [#%d]", selector, idx)
                            await asyncio.sleep(1)
                    except Exception:
                        continue
            except Exception:
                continue

        # JS 兜底：在页面中搜索包含"展开全部"等文本的可点击元素
        try:
            js_clicked = await page.evaluate("""() => {
                const keywords = ['展开全部', '展开全部轨迹', '查看全部', '全部轨迹', '查看更多'];
                const clickables = Array.from(document.querySelectorAll(
                    'button, span, div, a, [role="button"]'
                ));
                for (const el of clickables) {
                    const t = (el.innerText || '').trim();
                    if (t.length > 20) continue;  // 避免匹配到大块内容
                    if (!keywords.some(kw => t.includes(kw))) continue;
                    if (el.getBoundingClientRect().width === 0) continue;
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
                return false;
            }""")
            if js_clicked:
                expanded_any = True
                logger.info("  Clicked expand button via JS DOM search")
                await asyncio.sleep(1)
        except Exception:
            pass

        await asyncio.sleep(1)

    # 滚动到底部确保所有轨迹内容加载
    try:
        await page.evaluate("""() => {
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        await asyncio.sleep(1)
    except Exception:
        pass

    logger.info("  EMS tracking expansion complete")
