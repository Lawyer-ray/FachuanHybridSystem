"""EMS 登录/协议处理。"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final

from .browser_utils import click_first, click_locator_if_visible

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger("apps.express_query")

# EMS 协议相关 XPath（与 test_ems_full_flow.py 保持一致）
EMS_LOGIN_AGREE_CHECKBOX_XPATH: Final[str] = (
    "//*[@id='app']/div[1]/div/header/div[1]/div/div/div[3]/div/div[2]/div/div[2]/div[3]/div[1]/label/span/span"
)
EMS_AGREEMENT_MODAL_XPATH: Final[str] = "//*[@id='app']/div[2]"
EMS_AGREEMENT_LAST_CLAUSE_XPATH: Final[str] = "//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[1]/ul/li[5]/div/p"
EMS_AGREEMENT_ACCEPT_BUTTON_XPATH: Final[str] = "//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[2]/div[3]/button[2]"


async def is_ems_dialog_visible(page: Page) -> bool:
    """检测 EMS 登录弹窗是否正在显示。"""
    # 方法1: el-dialog.scan 容器可见
    try:
        dialog = page.locator(".el-dialog.scan")
        if await dialog.count() > 0 and await dialog.first.is_visible():
            return True
    except Exception:
        pass
    # 方法2: 可见的"扫码登录"文字
    try:
        qr = page.locator("text=扫码登录")
        if await qr.count() > 0 and await qr.first.is_visible():
            return True
    except Exception:
        pass
    # 方法3: 协议文字
    try:
        agree = page.locator("text=请阅读并同意服务协议")
        if await agree.count() > 0 and await agree.first.is_visible():
            return True
    except Exception:
        pass
    return False


async def ems_click_login_button(page: Page) -> bool:
    """点击 EMS 页面的「登录/注册」按钮。返回是否点击成功。"""
    selectors: list[str] = [
        "text=登录/注册",
        "a:text('登录/注册')",
        "div:text('登录/注册')",
        "span:text('登录/注册')",
    ]
    for selector in selectors:
        loc = page.locator(selector)
        try:
            count = await loc.count()
        except Exception:
            continue
        for i in range(min(count, 5)):
            target = loc.nth(i)
            try:
                if await target.is_visible():
                    await target.click(force=True, timeout=3000)
                    return True
            except Exception:
                continue
    # JS 兜底
    try:
        clicked = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('a, div, span, button'));
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if ((t === '登录/注册' || t === '登录') && el.getBoundingClientRect().width > 0) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        return bool(clicked)
    except Exception:
        return False


async def wait_for_ems_login(
    page: Page,
    *,
    timeout_seconds: int,
) -> None:
    from .browser_utils import has_any_visible

    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while asyncio.get_running_loop().time() < deadline:
        login_visible = await has_any_visible(
            page,
            ["text=扫码登录", ".el-dialog.scan"],
        )
        body = ""
        try:
            body = (await page.locator("body").text_content()) or ""
        except Exception:
            pass
        user_visible = any(kw in body for kw in ("退出", "我的EMS", "个人中心", "我的快递"))
        if user_visible or not login_visible:
            return
        await asyncio.sleep(2)


async def ems_handle_agreement_and_wait(
    context: BrowserContext, page: Page, timeout_seconds: int = 300
) -> None:
    """
    EMS 完整登录流程：
    - 检测弹窗可见性
    - 自动处理协议（勾选 checkbox → 同意 → 确认）
    - 等待用户扫码
    - 检测登录成功

    基于 ems_explore.py 验证通过的逻辑。
    """
    logger.info("EMS agreement + login wait (timeout=%ds)", timeout_seconds)
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    for attempt in range(20):
        # ---- 检测弹窗状态 ----
        dialog_visible = await is_ems_dialog_visible(page)

        # 检测二维码区域（说明可以扫码了）
        has_qr: bool = False
        try:
            qr_loc = page.locator("text=扫码登录")
            if await qr_loc.count() > 0 and await qr_loc.first.is_visible():
                has_qr = True
        except Exception:
            pass

        # 检测待处理的 checkbox
        has_checkbox: bool = False
        try:
            cb_loc = page.get_by_text("请阅读并同意", exact=False)
            if await cb_loc.count() > 0 and await cb_loc.first.is_visible():
                has_checkbox = True
        except Exception:
            pass

        logger.info(
            "EMS login round %d: dialog=%s, qr=%s, checkbox=%s",
            attempt + 1,
            dialog_visible,
            has_qr,
            has_checkbox,
        )

        # 二维码出现且无待处理 checkbox → 可以等扫码了
        if has_qr and not has_checkbox:
            logger.info("QR code visible, waiting for user scan...")
            break  # 跳出协议循环，进入等待扫码阶段

        # 弹窗不可见 → 尝试重新打开
        if not dialog_visible:
            reclicked = await ems_click_login_button(page)
            if reclicked:
                await asyncio.sleep(1.5)
            await asyncio.sleep(1)
            continue

        # ---- 尝试点击协议 checkbox ----
        cb_clicked = await _ems_try_agreement_checkbox(page)

        # 等待可能的协议页面弹出
        await asyncio.sleep(1.5)

        # 检测新标签页（排除当前 page）
        new_tab = None
        for p in context.pages:
            if p is not page and not p.is_closed():
                new_tab = p
                break

        if new_tab is not None:
            logger.info("New agreement tab detected: %s", new_tab.url)
            try:
                await _ems_accept_agreement_on_page(new_tab)
                if not new_tab.is_closed():
                    await new_tab.close()
                    logger.info("Agreement tab closed")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.info("Agreement tab handling failed: %s", e)

        if cb_clicked or has_qr or not dialog_visible:
            await asyncio.sleep(2)
        else:
            logger.info("No change detected, waiting...")
            await asyncio.sleep(2)

    # ===== 等待用户扫码登录 =====
    remaining_secs = max(int(deadline - asyncio.get_running_loop().time()), 0)
    logger.info("Waiting for QR code scan (max %ds)...", remaining_secs)

    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(3)

        still_dialog = await is_ems_dialog_visible(page)
        on_query = "query_express_delivery" in page.url.lower()
        body = ""
        try:
            body = (await page.locator("body").text_content()) or ""
        except Exception:
            pass

        has_logged_in_indicators = any(kw in body for kw in ("退出", "我的EMS", "个人中心", "我的快递"))

        # 弹窗关闭 + 在查询页 + 有内容 → 登录成功
        if not still_dialog and on_query and ("邮件号" in body or "物流" in body or "收件" in body):
            logger.info("Login success (dialog closed, on query page)")
            return

        # 跳到 personal_center → 也算成功
        if "personal_center" in page.url.lower():
            logger.info("Login success (redirected to personal_center)")
            return

        # 有已登录标志且弹窗不在了
        if not still_dialog and has_logged_in_indicators:
            logger.info("Login success (logged-in indicators found)")
            return

        remaining_secs = max(int(deadline - asyncio.get_running_loop().time()), 0)
        logger.info("Waiting for scan... (%ds remaining)", remaining_secs)

    raise TimeoutError("EMS login timed out after %ds" % timeout_seconds)


async def _ems_ensure_agreement_checked(page: Page) -> bool:
    """勾选"登录即代表您已同意"协议（仅精确 XPath，避免误点）。"""
    exact_checkbox = page.locator(f"xpath={EMS_LOGIN_AGREE_CHECKBOX_XPATH}")
    if await click_locator_if_visible(exact_checkbox, "agreement checkbox (exact XPath)"):
        return True

    # 只用精确文本匹配，不用模糊 class 选择器
    fallback_selectors = [
        "label:has-text('登录即代表您已同意')",
        "span:has-text('登录即代表您已同意')",
    ]
    for selector in fallback_selectors:
        if await click_first(page, [selector]):
            logger.info("  Agreement checked via text: %s", selector)
            return True

    # DOM 搜索也限定更精确的关键词
    try:
        clicked = await page.evaluate("""() => {
                const exactPattern = /\\u767b\\u5f55\\u5373\\u4ee3\\u8868\\u60a8\\u5df2\\u540c\\u610f/;
                const elements = Array.from(document.querySelectorAll('label, span'));
                for (const element of elements) {
                    const text = String(element.innerText || element.textContent || '').trim();
                    if (!text || !exactPattern.test(text)) continue;
                    const relatedInput =
                        element.querySelector('input[type="checkbox"]')
                        || element.closest('label')?.querySelector('input[type="checkbox"]')
                        || element.parentElement?.querySelector('input[type="checkbox"]');
                    if (relatedInput instanceof HTMLInputElement) {
                        if (!relatedInput.checked) relatedInput.click();
                        return true;
                    }
                    element.click();
                    return true;
                }
                return false;
            }""")
        if clicked:
            logger.info("  Agreement checked via DOM")
            await asyncio.sleep(0.6)
            return True
    except Exception:
        pass
    return False


async def _ems_scroll_agreement_and_accept(agreement_page: Page) -> bool:
    """尝试点击协议确认按钮，若不可点击则提示用户手动操作。"""
    accept_btn = agreement_page.locator(f"xpath={EMS_AGREEMENT_ACCEPT_BUTTON_XPATH}")
    if await click_locator_if_visible(accept_btn, "agreement accept button"):
        return True
    logger.info("  Please scroll to bottom and click '我已阅读并同意' manually")
    return True


async def _ems_open_last_agreement_and_accept(context: BrowserContext, page: Page) -> bool:
    """点击最后一个协议链接 → 滚动到底部 → 点击确认按钮。"""
    pages_before = len(context.pages)

    # 只用精确 XPath 触发，不用模糊选择器避免误点
    trigger_clicked = await click_locator_if_visible(
        page.locator(f"xpath={EMS_LOGIN_AGREE_CHECKBOX_XPATH}"),
        "agreement trigger (exact XPath)",
    )

    if not trigger_clicked:
        logger.info("  Agreement checkbox not found yet (login may still be loading)")
        return False

    # 判断是否打开了新页面（弹窗页）
    agreement_page: Page = page
    if len(context.pages) > pages_before:
        agreement_page = context.pages[-1]

    try:
        await agreement_page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass

    # 等待协议弹层出现
    modal_loc = agreement_page.locator(f"xpath={EMS_AGREEMENT_MODAL_XPATH}")
    try:
        if await modal_loc.count() > 0:
            await modal_loc.first.wait_for(timeout=4000)
            logger.info("  Agreement modal appeared")
    except Exception:
        pass

    # 点击最后一个条款滚动到底部
    last_clause = agreement_page.locator(f"xpath={EMS_AGREEMENT_LAST_CLAUSE_XPATH}")
    if await click_locator_if_visible(last_clause, "last clause"):
        await asyncio.sleep(0.6)

    accepted = await _ems_scroll_agreement_and_accept(agreement_page)

    # 如果是新开的页面，关闭它
    if agreement_page is not page:
        try:
            await agreement_page.close()
            logger.info("  Closed agreement page")
        except Exception:
            pass

    return accepted


async def _ems_try_agreement_checkbox(page: Page) -> bool:
    """尝试多种策略点击 EMS 协议 checkbox。返回是否点击成功。"""
    # 策略A: XPath 点击 span
    xpaths: list[str] = [
        "//label[contains(., '同意')]/span/span",
        "//label[contains(., '服务协议')]//span[@class]",
    ]
    for xp in xpaths:
        try:
            loc = page.locator(f"xpath={xp}")
            if await loc.count() > 0:
                await loc.first.click(force=True, timeout=2000)
                logger.info("Agreement clicked via XPath: %s", xp)
                await asyncio.sleep(2)
                return True
        except Exception as e:
            logger.info("XPath failed: %s", e)

    # 策略B: 文本定位整行
    try:
        text_loc = page.get_by_text("请阅读并同意", exact=False)
        if await text_loc.count() > 0:
            await text_loc.first.click(force=True, timeout=2000)
            logger.info("Agreement clicked via text")
            await asyncio.sleep(2)
            return True
    except Exception as e:
        logger.info("Text click failed: %s", e)

    # 策略C: JS 在弹窗内搜索
    try:
        js_res = await page.evaluate("""() => {
            const dialogs = document.querySelectorAll('.el-dialog');
            for (const d of dialogs) {
                if (d.getBoundingClientRect().width === 0) continue;
                const candidates = Array.from(d.querySelectorAll(
                    'label, span, div, [class*="check"], [class*="agree"]'
                )).filter(el => {
                    const t = el.innerText || '';
                    return (t.includes('同意') || t.includes('协议'))
                           && el.getBoundingClientRect().width > 0;
                });
                if (candidates.length > 0) { candidates[0].click(); return { ok: true }; }
            }
            const all = Array.from(document.querySelectorAll('*')).filter(el => {
                const t = el.innerText || '';
                return (t.includes('请阅读并同意') || t.includes('登录即代表'))
                       && el.getBoundingClientRect().width > 0 && el.children.length < 5;
            });
            all.sort((a, b) => a.innerText.length - b.innerText.length);
            if (all.length > 0) { all[0].click(); return { ok: true }; }
            return { ok: false };
        }""")
        if js_res.get("ok"):
            logger.info("Agreement clicked via JS")
            await asyncio.sleep(2)
            return True
    except Exception as e:
        logger.info("JS click failed: %s", e)

    return False


async def _ems_accept_agreement_on_page(agreement_page: Page) -> None:
    """在协议页面上点最后一个条款 + 点确认按钮。"""
    last_clause_selectors: list[str] = [
        "xpath=//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[1]/ul/li[last()]/div/p",
        "xpath=//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[1]/ul/li[5]/div/p",
    ]
    for sel in last_clause_selectors:
        try:
            clause = agreement_page.locator(sel)
            if await clause.count() > 0:
                await clause.first.click()
                await asyncio.sleep(0.5)
                break
        except Exception:
            continue

    accept_selectors: list[str] = [
        "xpath=//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[2]/div[3]/button[last()]",
        "xpath=//*[@id='app']/div[2]/div/div[2]/div/div[1]/div[2]/div[3]/button[2]",
    ]
    for sel in accept_selectors:
        try:
            btn = agreement_page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click(timeout=3000)
                logger.info("Agreement accept button clicked")
                await asyncio.sleep(1)
                return
        except Exception:
            continue
    logger.warning("Accept button not found on agreement page")


async def is_ems_login_window(page: Page, body_text: str) -> bool:
    """判断页面是否为 EMS 登录/扫码窗口。"""
    url_lower = page.url.lower()
    url_keywords = ("login", "passport", "auth", "oauth", "qrcode", "wx")
    if any(kw in url_lower for kw in url_keywords):
        return True
    body_keywords = (
        "扫码登录",
        "请使用微信扫码",
        "微信扫码",
        "登录",
        "手机号登录",
        "验证码登录",
    )
    return any(kw in body_text for kw in body_keywords)
