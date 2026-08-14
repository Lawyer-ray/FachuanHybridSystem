"""金诚同达 OA 发票申请 — Playwright 自动化。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import Page

from ..auth.service import JtnAuthService

logger = logging.getLogger("apps.oa_filing.jtn_invoice")

_INVOICE_URL = (
    "https://ims.jtn.com/invoice/ProjectFapiaoRequest.aspx"
    "?FirstModel=FINANCE&SecondModel=FINANCE002&ThirdModel=FINANCE002-04"
)
_CASE_NO_INPUT = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
_SEARCH_BTN_XP = '//*[@id="wrap"]/div[1]/div[2]/div/div[4]/div[2]/table/tbody/tr[5]/td[3]/div/a'
_FIRST_APPLY_LINK_XP = '//*[@id="wrap"]/div[1]/div[2]/div/div[5]/table/tbody/tr[2]/td[9]/a'

_SHORT_WAIT = 0.5
_MEDIUM_WAIT = 2


class PlaywrightInvoiceMixin:
    """Playwright 发票页面自动化 mixin。"""

    _account: str
    _password: str
    _auth: JtnAuthService

    async def _open_page(self: Any, oa_case_number: str) -> tuple[Any, Any]:
        """打开发票页面，输入案件编号→搜索→点击申请对外开票，返回 (playwright, browser)。"""
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # ── 登录 ──
            cached = self._auth.load_cookies()
            if cached:
                logger.info("使用缓存 cookies 登录发票页面")
                await self._auth.inject_to_context(context, cached)
                await page.goto(_INVOICE_URL, wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(_MEDIUM_WAIT)
                if "login" not in page.url.lower():
                    logger.info("Cookies 有效，已进入发票页面")
                else:
                    logger.warning("缓存 cookies 已失效，执行 SSO 扫码登录")
                    # 在当前页面执行 SSO 扫码，复用已有浏览器窗口
                    cookies = await self._auth.perform_sso_login(page, context)
                    await self._auth.inject_to_context(context, cookies)
            else:
                logger.info("无缓存 cookies，执行 SSO 扫码登录")
                # 在当前页面执行 SSO 扫码，复用已有浏览器窗口
                cookies = await self._auth.perform_sso_login(page, context)
                await self._auth.inject_to_context(context, cookies)

            # ── 导航到发票页面 ──
            await page.goto(_INVOICE_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(_MEDIUM_WAIT)

            if "login" in page.url.lower():
                logger.warning("当前在登录页，等待 SSO 扫码...")
                await page.wait_for_url("**/ims.jtn.com/invoice/**", timeout=180_000)
                await asyncio.sleep(_MEDIUM_WAIT)

            logger.info("已进入发票管理页面: %s", page.url)

            # ── 输入案件编号 ──
            if oa_case_number:
                logger.info("输入案件编号: %s", oa_case_number)
                case_input_id = _CASE_NO_INPUT.lstrip("#")
                await page.evaluate(f"""() => {{
                    const el = document.getElementById("{case_input_id}");
                    if (el) {{
                        el.removeAttribute('readonly');
                        el.removeAttribute('disabled');
                        el.value = '{oa_case_number}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}""")
                await asyncio.sleep(_SHORT_WAIT)

                # ── 点击查找 ──
                logger.info("点击查找按钮")
                search_btn = page.locator(f"xpath={_SEARCH_BTN_XP}")
                count = await search_btn.count()
                if count > 0:
                    await search_btn.click(timeout=10_000)
                else:
                    logger.warning("XPath 未找到查找按钮，跳过")
                await asyncio.sleep(3)

                # ── 点击申请对外开票 ──
                logger.info("点击申请对外开票")
                try:
                    apply_link = page.locator(f"xpath={_FIRST_APPLY_LINK_XP}")
                    await apply_link.first.click(timeout=10_000)
                    await asyncio.sleep(_MEDIUM_WAIT)
                    logger.info("已跳转到开票页面: %s", page.url)
                except Exception:
                    logger.warning("XPath 未找到，尝试 JS 点击")
                    result = await page.evaluate("""() => {
                        const links = document.querySelectorAll('#wrap table a');
                        for (const a of links) {
                            if (a.textContent.includes('申请') || a.textContent.includes('开票')) {
                                a.click(); return 'clicked: ' + a.textContent.trim();
                            }
                        }
                        return 'not found';
                    }""")
                    logger.info("JS 点击结果: %s", result)
                    await asyncio.sleep(_MEDIUM_WAIT)

            logger.info("开票页面已打开")
            return playwright, browser

        except Exception:
            await browser.close()
            await playwright.stop()
            raise
