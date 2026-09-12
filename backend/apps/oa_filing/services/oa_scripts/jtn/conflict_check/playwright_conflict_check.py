"""金诚同达 OA 利益冲突信息预检 — Playwright 自动化。

复用 JtnAuthService 的 cookie 持久化复用机制（登录态有效时不再重新登录），
打开"利益冲突信息预检"页面，填入当事人名称并搜索，保持浏览器打开供律师查看。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import Page

from ..auth.service import JtnAuthService
from .constants import CONFLICT_CHECK_URL, KEYWORD_SELECTOR, MEDIUM_WAIT, SEARCH_BTN_SELECTOR, SEARCH_WAIT, SHORT_WAIT

logger = logging.getLogger("apps.oa_filing.jtn_conflict_check")


class PlaywrightConflictCheckMixin:
    """Playwright 利冲检查页面自动化 mixin。"""

    _account: str
    _password: str
    _auth: JtnAuthService

    async def _open_page(self: Any, keyword: str) -> tuple[Any, Any]:
        """打开利冲检查页面，填入当事人名称并搜索，返回 (playwright, browser) 保持浏览器打开。"""
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # 用户关闭浏览器时自动清理 playwright，释放进程
        def _cleanup(_: Any = None) -> None:
            try:
                asyncio.run(playwright.stop())
            except Exception:
                pass

        browser.on("disconnected", _cleanup)

        try:
            # ── 登录（优先复用缓存 cookies，失效则 SSO 扫码） ──
            await self._login(page, context)

            # ── 导航到利冲预检页面 ──
            await self._navigate(page)

            # ── 填入当事人名称并搜索 ──
            await self._search_by_name(page, keyword)

            logger.info("利冲检查页面已打开: %s", page.url)
            return playwright, browser

        except Exception:
            await browser.close()
            await playwright.stop()
            raise

    async def _login(self: Any, page: Page, context: Any) -> None:  # pragma: no cover
        """登录 OA：优先缓存 cookies，否则在当前页面 SSO 扫码。"""
        cached = self._auth.load_cookies()
        if cached:
            logger.info("使用缓存 cookies 登录利冲检查页面")
            await JtnAuthService.inject_to_context(context, cached)
            await page.goto(CONFLICT_CHECK_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(MEDIUM_WAIT)
            if "login" not in page.url.lower():
                logger.info("Cookies 有效，已进入利冲检查页面")
                return
            logger.warning("缓存 cookies 已失效，执行 SSO 扫码登录")

        cookies = await self._auth.perform_sso_login(page, context)
        await JtnAuthService.inject_to_context(context, cookies)

    async def _navigate(self: Any, page: Page) -> None:  # pragma: no cover
        """导航到利冲信息预检页面。"""
        logger.info("导航到利冲预检页面: %s", CONFLICT_CHECK_URL)
        await page.goto(CONFLICT_CHECK_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(MEDIUM_WAIT)

        if "login" in page.url.lower():
            logger.warning("当前在登录页，等待 SSO 扫码...")
            await page.wait_for_url("**/ims.jtn.com/projflw/**", timeout=180_000)
            await asyncio.sleep(MEDIUM_WAIT)

        logger.info("已进入利冲预检页面: %s", page.url)

    async def _search_by_name(self: Any, page: Page, keyword: str) -> None:  # pragma: no cover
        """在关键词输入框填入当事人名称并点击搜索。

        该输入框是 OA 联想组件（readonly + _ims_acprev），playwright fill() 拒绝写只读元素，
        需用 JS 移除 readonly 后写入 value 并派发 input/change 事件。
        """
        logger.info("利冲预检关键词: %s", keyword)
        found = await page.evaluate(
            """({ sel, value }) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                el.removeAttribute("readonly");
                el.value = value;
                el.dispatchEvent(new Event("input", { bubbles: true }));
                el.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
            }""",
            {"sel": KEYWORD_SELECTOR, "value": keyword},
        )
        if not found:
            raise RuntimeError(f"未找到利冲预检关键词输入框: {KEYWORD_SELECTOR}")
        await asyncio.sleep(SHORT_WAIT)
        await page.click(SEARCH_BTN_SELECTOR)
        await asyncio.sleep(SEARCH_WAIT)
        logger.info("利冲预检搜索已完成")
