"""金诚同达 OA 发票申请 — Playwright 自动化。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import Page

from apps.core.services.browser import BrowserSessionHandle, close_browser_session, create_browser_async_manual

from ..auth.service import JtnAuthService

logger = logging.getLogger("apps.oa_filing.jtn_invoice")

_INVOICE_URL = (
    "https://ims.jtn.com/invoice/ProjectFapiaoRequest.aspx"
    "?FirstModel=FINANCE&SecondModel=FINANCE002&ThirdModel=FINANCE002-04"
)
_CASE_NO_INPUT = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
_SEARCH_BTN_XP = '//*[@id="wrap"]/div[1]/div[2]/div/div[4]/div[2]/table/tbody/tr[5]/td[3]/div/a'

_SHORT_WAIT = 0.5
_MEDIUM_WAIT = 2


class PlaywrightInvoiceMixin:
    """Playwright 发票页面自动化 mixin。"""

    _account: str
    _password: str
    _auth: JtnAuthService

    async def _open_page(self: Any, oa_case_number: str) -> BrowserSessionHandle:
        """打开发票页面，输入案件编号→搜索→点击申请对外开票，返回浏览器会话句柄（长生命周期）。"""
        session = await create_browser_async_manual("jtn")
        page, context = session.page, session.context
        # 浏览器关闭后的回收由 adapter.wait_open_browsers_closed 负责（调度器压住
        # 事件循环直到用户关掉浏览器）；脚本执行中途的异常路径在下方 except 里
        # 通过工厂的 close_browser_session 显式回收。

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
                await page.evaluate(
                    """({ inputId, value }) => {
                        const el = document.getElementById(inputId);
                        if (el) {
                            el.removeAttribute('readonly');
                            el.removeAttribute('disabled');
                            el.value = value;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""",
                    {"inputId": case_input_id, "value": oa_case_number},
                )
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
                # 必须命中目标案件所在行：查找静默失败时点首行会打开别的案件的
                # 申请页（业务错误比报错更糟），因此行级定位；未命中不兜底点击，
                # 浏览器保持打开交人工操作。
                row_xpath = f'//tr[contains(., "{oa_case_number}")]'
                row = page.locator(f"xpath={row_xpath}")
                row_found = False
                for _ in range(10):
                    if await row.count() > 0:
                        row_found = True
                        break
                    await asyncio.sleep(1)

                if not row_found:
                    logger.warning(
                        "查找结果中未出现案件 %s，不点「申请对外开票」，请人工在已打开页面操作",
                        oa_case_number,
                    )
                else:
                    apply_link = page.locator(f'xpath={row_xpath}//a[contains(., "申请") or contains(., "开票")]')
                    if await apply_link.count() == 0:
                        logger.warning("案件 %s 行内未找到申请入口，请人工在已打开页面操作", oa_case_number)
                    else:
                        await apply_link.first.click(timeout=10_000)
                        await asyncio.sleep(_MEDIUM_WAIT)
                        logger.info("已跳转到开票页面: %s", page.url)

            logger.info("开票页面已打开")
            return session

        except Exception:
            await close_browser_session(session)
            raise
