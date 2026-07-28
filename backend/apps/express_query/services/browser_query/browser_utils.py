"""通用 Playwright 工具方法。

借鉴 Chrome 插件 (songda-chrome-extension) 的交互模式：
- native_fill: fill() 失败时 fallback 到逐字符输入
- 每阶段独立超时 + 结构化错误
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page

logger = logging.getLogger("apps.express_query")


# ── 阶段追踪 ─────────────────────────────────────────────────


@dataclass
class StageTracker:
    """追踪查询流程当前阶段，用于结构化错误报告。"""

    stage: str = "init"
    tracking_number: str = ""

    def set(self, stage: str) -> None:
        self.stage = stage
        logger.info("[%s] stage → %s", self.tracking_number or "?", stage)

    def error_message(self, base: str) -> str:
        return f"[{self.stage}] {base}"


@dataclass
class AbortFlag:
    """协作式取消标记。在每个关键步骤检查。"""

    aborted: str = ""

    def abort(self, reason: str) -> None:
        self.aborted = reason

    def check(self) -> None:
        if self.aborted:
            raise RuntimeError(self.aborted)


# ── 输入填写 ─────────────────────────────────────────────────


async def fill_first(page: Page, selectors: list[str], value: str) -> None:  # pragma: no cover
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


async def native_fill(page: Page, selectors: list[str], value: str) -> None:  # pragma: no cover
    """增强版输入填写：fill() 失败时 fallback 到逐字符输入。

    借鉴 Chrome 插件 typeTextLikeUser 的思路：
    1. 优先用 Playwright fill()（走 CDP，最可靠）
    2. 失败则用 keyboard.type()（触发完整键盘事件序列）
    3. 最后尝试 blur/focusout 触发框架状态更新
    """
    # 第1级：标准 fill()
    try:
        await fill_first(page, selectors, value)
        logger.info("native_fill: fill() succeeded")
        return
    except Exception:
        logger.info("native_fill: fill() failed, trying keyboard.type()")

    # 第2级：找到输入框，用 keyboard.type() 逐字符输入
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count() == 0:
                continue
            first = locator.first
            await first.click(force=True)
            await first.focus()

            # 清空
            await page.keyboard.press("Meta+a")
            await page.keyboard.press("Backspace")

            # 逐字符输入（触发 keydown/keypress/keyup/input 事件）
            await page.keyboard.type(value, delay=30)

            # 触发 change + blur（某些框架在 blur 时才更新内部状态）
            await page.evaluate(
                """(val) => {
                const el = document.activeElement;
                if (!el) return;
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                el.dispatchEvent(new Event('focusout', { bubbles: true }));
            }""",
                value,
            )

            logger.info("native_fill: keyboard.type() succeeded")
            return
        except Exception:
            continue

    raise RuntimeError(f"native_fill: all methods failed for selectors: {selectors[:3]}")


# ── 点击 ─────────────────────────────────────────────────────


async def click_locator_if_visible(locator: Locator, description: str) -> bool:  # pragma: no cover
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


async def click_first(page: Page, selectors: list[str]) -> bool:  # pragma: no cover
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


async def click_first_non_disabled(page: Page, selectors: list[str]) -> bool:  # pragma: no cover
    """点击第一个可见且非禁用的元素（借鉴 Chrome 插件 isDisabled 过滤）。"""
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
                # 检查是否禁用
                is_disabled = await candidate.is_disabled()
                if is_disabled:
                    continue
                await candidate.scroll_into_view_if_needed()
                await candidate.click(force=True, timeout=2000)
                return True
            except Exception:
                continue
    return False


async def has_any_visible(page: Page, selectors: list[str]) -> bool:  # pragma: no cover
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


async def has_any_text(page: Page, keywords: list[str]) -> bool:  # pragma: no cover
    """检查页面 body 是否包含任意关键词。"""
    try:
        body = (await page.locator("body").text_content()) or ""
    except Exception:
        return False
    return any(kw in body for kw in keywords)


# ── 页面状态检测 ─────────────────────────────────────────────


async def detect_page_state(
    page: Page,
    *,
    tracking_number: str = "",
    login_selectors: list[str] | None = None,
    login_keywords: list[str] | None = None,
    logged_in_selectors: list[str] | None = None,
    logged_in_keywords: list[str] | None = None,
    captcha_selectors: list[str] | None = None,
    captcha_keywords: list[str] | None = None,
    not_found_keywords: list[str] | None = None,
    result_keywords: list[str] | None = None,
    result_selectors: list[str] | None = None,
    input_selectors: list[str] | None = None,
) -> str:
    """检测 EMS 页面当前状态（借鉴 Chrome 插件 getStatus 状态机）。

    返回: loading | loginRequired | captcha | resultReady | notFound |
          waitingResult | needFill | unknown
    """
    from .selectors_config import get_ems_selectors, get_ems_text

    if await page.evaluate("() => document.readyState") == "loading":
        return "loading"

    try:
        body_text = (await page.locator("body").text_content()) or ""
    except Exception:
        body_text = ""
    normalized = body_text.replace(" ", "").replace("\n", "")

    _login_selectors = login_selectors or get_ems_selectors("loginIndicators")
    _login_keywords = login_keywords or get_ems_text("loginKeywords")
    _logged_in_selectors = logged_in_selectors or get_ems_selectors("loggedInIndicators")
    _logged_in_keywords = logged_in_keywords or get_ems_text("loggedInKeywords")
    _captcha_selectors = captcha_selectors or get_ems_selectors("captchaIndicators")
    _captcha_keywords = captcha_keywords or get_ems_text("captchaKeywords")
    _not_found_keywords = not_found_keywords or get_ems_text("notFoundKeywords")
    _result_keywords = result_keywords or get_ems_text("resultKeywords")
    _result_selectors = result_selectors or get_ems_selectors("resultContainers")
    _input_selectors = input_selectors or get_ems_selectors("trackingInputs")

    # 登录检测（带负守卫：有登录关键词 且 无已登录关键词 → 需要登录）
    has_login = any(kw in normalized for kw in _login_keywords)
    has_logged_in = await has_any_visible(page, _logged_in_selectors) or any(
        kw in normalized for kw in _logged_in_keywords
    )
    if has_login and not has_logged_in:
        if await has_any_visible(page, _login_selectors):
            return "loginRequired"

    # 验证码检测（仅检测真正的验证码输入框是否可见，不扫描页面文本
    # 避免页面帮助文本中出现"验证码"三字导致误判）
    _captcha_inputs = [
        "input[placeholder*='验证码']",
        "input[aria-label*='验证码']",
        "input[type='tel'][maxlength='4']",
        "input[type='tel'][maxlength='6']",
        "img[src*='captcha']",
        "img[src*='verify']",
    ]
    if await has_any_visible(page, _captcha_inputs):
        return "captcha"

    # 结果就绪检测
    result_visible = await has_any_visible(page, _result_selectors)
    result_text = any(kw in normalized for kw in _result_keywords)
    if result_visible and result_text:
        if tracking_number:
            tn_clean = tracking_number.replace(" ", "")
            if tn_clean in normalized:
                return "resultReady"
        else:
            return "resultReady"

    # 未找到检测
    if any(kw in normalized for kw in _not_found_keywords):
        return "notFound"

    # 已填入单号等待结果
    if tracking_number:
        tn_clean = tracking_number.replace(" ", "")
        if tn_clean in normalized:
            return "waitingResult"

    # 输入框就绪
    if await has_any_visible(page, _input_selectors):
        return "needFill"

    return "unknown"


# ── 安全页面导航 ─────────────────────────────────────────────


async def ensure_query_page(page: Page, clean_url: str) -> bool:  # pragma: no cover
    """检测页面是否被重定向（如登录后跳到个人中心），是则导航回查询页。

    借鉴 Chrome 插件 ensureEmsQueryPage：在每个轮询周期检查。
    """
    current = page.url.lower()
    if "personal_center" in current or ("query_express_delivery" not in current and "querylist" not in current):
        logger.info("Redirected to %s, navigating back to %s", page.url, clean_url)
        await page.goto(clean_url, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2)
        return True
    return False
