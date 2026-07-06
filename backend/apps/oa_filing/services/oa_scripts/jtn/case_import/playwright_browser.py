"""Playwright 导航 + IMS 表单 + 搜索链路。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Generator
from urllib.parse import urlparse

import httpx
from playwright.async_api import BrowserContext, Frame, Page

from apps.core.services.browser import create_browser_async

from .. import html_parser
from ..models import CaseSearchItem, OACaseData, OAListCaseCandidate
from .http_client import (
    _AJAX_WAIT,
    _BASE_URL,
    _CASE_LIST_URL,
    _DEFAULT_HTTP_TIMEOUT,
    _DETAIL_URL_TEMPLATE,
    _HTTP_HEADERS,
    _LOGIN_URL,
    _MEDIUM_WAIT,
    _SHORT_WAIT,
)

logger = logging.getLogger("apps.oa_filing.jtn_case_import")


class JtnPlaywrightBrowserMixin:  # pragma: no cover
    """Playwright 导航 + IMS 表单 + 搜索链路。"""

    # --- 由 facade 或其他 mixin 提供 ---
    _account: str
    _password: str
    _headless: bool
    _page: Page | None
    _context: BrowserContext | None
    _context_manager: Any  # CloakBrowser context manager
    _name_search_cm: Any  # name search CloakBrowser context manager

    # ------------------------------------------------------------------
    # Playwright 兜底批量查询
    # ------------------------------------------------------------------
    async def _search_cases_via_playwright(  # pragma: no cover
        self: Any,
        case_nos: list[str],
    ) -> list[tuple[str, OACaseData | None]]:
        """Playwright 兜底批量查询。"""
        fallback_results: list[tuple[str, OACaseData | None]] = []

        async with create_browser_async("default", headless=self._headless) as (page, context):
            self._page = page
            self._context = context

            await self._login()
            await self._navigate_to_case_list()

            for case_no in case_nos:
                try:
                    logger.info("搜索案件: %s", case_no)
                    await self._ensure_case_list_ready()

                    search_item = await self._search_case_by_no(case_no)
                    if not search_item:
                        logger.warning("未找到案件: %s", case_no)
                        fallback_results.append((case_no, None))
                        continue

                    case_data = await self._fetch_case_detail(search_item)
                    fallback_results.append((case_no, case_data))
                except Exception as exc:
                    logger.warning("Playwright 兜底查询异常 %s: %s", case_no, exc, exc_info=True)
                    fallback_results.append((case_no, None))

        return fallback_results

    async def _search_cases_by_name_via_playwright(
        self: Any, *, keyword: str, limit: int
    ) -> list[OAListCaseCandidate]:  # pragma: no cover
        try:
            await self._ensure_name_search_playwright_session()
            page = self._page
            assert page is not None

            selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_name"
            target_frame = await self._find_visible_frame_for_selector(selector=selector, timeout_ms=15_000)
            if target_frame is None:
                raise RuntimeError(f"未找到案件名称输入框: {selector}")

            input_locator = target_frame.locator(selector)
            await input_locator.wait_for(state="visible", timeout=15_000)
            await input_locator.fill(keyword)
            await asyncio.sleep(_SHORT_WAIT)

            try:
                await target_frame.evaluate("searchOk()")
            except Exception:
                await page.evaluate("searchOk()")

            await asyncio.sleep(_AJAX_WAIT)
            await page.wait_for_load_state("networkidle", timeout=15_000)
            await asyncio.sleep(_SHORT_WAIT)

            html_text = await target_frame.content()
            candidates = html_parser.extract_case_candidates_from_search_html(html_text)
            return self._rank_name_candidates(keyword=keyword, candidates=candidates, limit=limit)  # type: ignore[no-any-return]
        except Exception as exc:
            if self._is_sso_blocking_error(exc):
                raise
            logger.warning("Playwright 按名称查询异常 keyword=%s: %s", keyword, exc, exc_info=True)
            return []

    async def _ensure_name_search_playwright_session(self: Any) -> None:  # pragma: no cover
        if self._name_search_cm is not None and self._page is not None and self._context is not None:
            try:
                await self._ensure_case_list_ready()
                return
            except Exception:
                await self.close()

        self._name_search_cm = create_browser_async("default", headless=self._headless)
        self._page, self._context = await self._name_search_cm.__aenter__()

        await self._login()
        await self._navigate_to_case_list()
        await self._ensure_case_list_ready()

    # ------------------------------------------------------------------
    # Frame / 页面工具
    # ------------------------------------------------------------------
    async def _find_visible_frame_for_selector(
        self: Any, *, selector: str, timeout_ms: int
    ) -> Frame | None:  # pragma: no cover
        page = self._page
        assert page is not None

        deadline = asyncio.get_event_loop().time() + (max(100, timeout_ms) / 1000)
        while asyncio.get_event_loop().time() < deadline:
            for frame in page.frames:
                try:
                    locator = frame.locator(selector)
                    if await locator.count() <= 0:
                        continue
                    await locator.first.wait_for(state="visible", timeout=300)
                    return frame  # type: ignore[no-any-return]
                except Exception:
                    continue
            await asyncio.sleep(0.2)
        return None

    async def _ensure_case_list_ready(self: Any) -> None:  # pragma: no cover
        """确保当前在案件列表页并且搜索输入框可用。"""
        selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
        target_frame = await self._find_visible_frame_for_selector(selector=selector, timeout_ms=2_000)
        if target_frame is not None:
            return
        await self._navigate_to_case_list()

    # ------------------------------------------------------------------
    # Cookie 注入 + Playwright 登录
    # ------------------------------------------------------------------
    async def _inject_cookies_to_context(self: Any, cookies: dict[str, str]) -> None:  # pragma: no cover
        """将 cookie 字典注入 Playwright context。"""
        context = self._context
        assert context is not None
        if not cookies:
            return

        await context.add_cookies(
            [
                {
                    "name": str(name),
                    "value": str(value or ""),
                    "domain": "ims.jtn.com",
                    "path": "/",
                }
                for name, value in cookies.items()
                if str(name).strip()
            ]
        )

    async def _login(self: Any) -> None:  # pragma: no cover
        """通过 httpx 接口登录，将 cookie 注入 Playwright context。"""
        cached_cookies = self._http_cookies_cache or {}
        if cached_cookies:
            logger.info("接口登录复用 HTTP cookie=%s", len(cached_cookies))
            await self._inject_cookies_to_context(cached_cookies)
            return

        logger.info("接口登录: %s", _LOGIN_URL)

        async with httpx.AsyncClient(
            headers=_HTTP_HEADERS, follow_redirects=True, timeout=15, trust_env=False
        ) as client:
            r = await client.get(_LOGIN_URL)
            csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', r.text)
            csrf = csrf_match.group(1) if csrf_match else ""

            r2 = await client.post(
                _LOGIN_URL,
                data={"CSRFToken": csrf, "userid": self._account, "password": self._password},
            )

            if self._is_login_failed_response(r2):
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")

            cookies = dict(client.cookies.items())
            self._http_cookies_cache = cookies
            await self._inject_cookies_to_context(cookies)

        logger.info("接口登录成功，cookie 已注入")

    # ------------------------------------------------------------------
    # 导航到案件列表页
    # ------------------------------------------------------------------
    async def _navigate_to_case_list(self: Any) -> None:  # pragma: no cover
        """导航到案件列表页。"""
        page = self._page
        assert page is not None

        async def _goto_case_list_once() -> None:
            await page.goto(_CASE_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                logger.debug("案件列表页未达到 networkidle，继续后续检测")

        logger.info("导航到案件列表页: %s", _CASE_LIST_URL)
        await _goto_case_list_once()

        try:
            self._raise_if_sso_blocking(url=page.url, html_text=await page.content(), stage="Playwright 列表页访问")
        except Exception as exc:
            if not self._is_sso_blocking_error(exc):
                raise
            logger.warning("Playwright 触发 SSO，等待当前浏览器完成交互登录")
            await self._wait_for_playwright_sso_login()
            await _goto_case_list_once()
            self._raise_if_sso_blocking(url=page.url, html_text=await page.content(), stage="Playwright 列表页访问")

        if self._is_ims_login_form_page(str(page.url or "")) or await self._has_visible_ims_login_form(page):
            logger.warning("检测到 IMS 登录页，等待自动/人工登录完成")
            await self._wait_for_playwright_sso_login()
            await _goto_case_list_once()

        # 关闭可能存在的模态对话框
        try:
            confirm_btn = page.get_by_role("button", name="确定")
            if await confirm_btn.is_visible(timeout=3000):
                logger.info("检测到模态对话框，关闭中...")
                await confirm_btn.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(_MEDIUM_WAIT)
        except Exception:
            pass

        selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
        target_frame = await self._find_visible_frame_for_selector(selector=selector, timeout_ms=15_000)
        if target_frame is None:
            if self._is_ims_login_form_page(str(page.url or "")) or await self._has_visible_ims_login_form(page):
                logger.warning("搜索输入框未找到，当前仍在 IMS 登录页，等待登录后重试")
                await self._wait_for_playwright_sso_login()
                await _goto_case_list_once()
                target_frame = await self._find_visible_frame_for_selector(selector=selector, timeout_ms=15_000)

            if target_frame is None:
                raise RuntimeError("案件列表页搜索输入框未就绪，请完成登录后重试")

        await asyncio.sleep(_MEDIUM_WAIT)
        logger.info("已进入案件列表页面")

    # ------------------------------------------------------------------
    # IMS 登录页检测与自动填充
    # ------------------------------------------------------------------
    def _is_ims_login_form_page(self: Any, url: str) -> bool:  # pragma: no cover
        parsed = urlparse(str(url or "").strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        return host == "ims.jtn.com" and path == "/member/login.aspx"

    async def _resolve_ims_login_frame(self: Any, page: Page) -> Frame | None:  # pragma: no cover
        frame_candidates = [page.main_frame, *[frame for frame in page.frames if frame != page.main_frame]]
        user_selectors = (
            'input[name="userid"]',
            'input[id="userid"]',
            'input[name="username"]',
            'input[id="username"]',
            'input[type="text"]',
        )
        password_selectors = ('input[name="password"]', 'input[id="password"]', 'input[type="password"]')

        for frame in frame_candidates:
            try:
                has_visible_user = False
                for selector in user_selectors:
                    locator = frame.locator(selector)
                    if await locator.count() <= 0:
                        continue
                    try:
                        await locator.first.wait_for(state="visible", timeout=500)
                        has_visible_user = True
                        break
                    except Exception:
                        continue

                has_visible_password = False
                for selector in password_selectors:
                    locator = frame.locator(selector)
                    if await locator.count() <= 0:
                        continue
                    try:
                        await locator.first.wait_for(state="visible", timeout=500)
                        has_visible_password = True
                        break
                    except Exception:
                        continue

                if has_visible_user and has_visible_password:
                    return frame
            except Exception:
                continue
        return None

    async def _has_visible_ims_login_form(self: Any, page: Page) -> bool:  # pragma: no cover
        login_frame = await self._resolve_ims_login_frame(page)
        if login_frame is None:
            return False
        try:
            return await login_frame.locator('input[type="password"]').first.is_visible(timeout=500)  # type: ignore[no-any-return]
        except Exception:
            return False

    async def _try_playwright_ims_form_login(self: Any, page: Page) -> bool:  # pragma: no cover
        if not self._account or not self._password:
            return False

        login_frame = await self._resolve_ims_login_frame(page)
        if login_frame is None:
            logger.warning("已命中 IMS 登录页，但未定位到登录表单")
            return False

        user_selectors = [
            'input[name="userid"]',
            'input[id="userid"]',
            'input[name="username"]',
            'input[id="username"]',
            'input[type="text"]',
        ]
        password_selectors = ['input[name="password"]', 'input[id="password"]', 'input[type="password"]']

        user_input = None
        password_input = None

        for selector in user_selectors:
            try:
                candidate = login_frame.locator(selector).first
                await candidate.wait_for(state="visible", timeout=1_000)
                user_input = candidate
                break
            except Exception:
                continue

        for selector in password_selectors:
            try:
                candidate = login_frame.locator(selector).first
                await candidate.wait_for(state="visible", timeout=1_000)
                password_input = candidate
                break
            except Exception:
                continue

        if user_input is None or password_input is None:
            logger.warning("已命中 IMS 登录页，但未定位到用户名/密码输入框")
            return False

        try:
            await user_input.fill("")
            await user_input.fill(self._account)
            await password_input.fill("")
            await password_input.fill(self._password)

            submit_selectors = [
                'button:has-text("登录")',
                'input[type="submit"]',
                'a:has-text("登录")',
                ".loginbtn",
                ".btn-login",
            ]
            submitted = False
            for selector in submit_selectors:
                try:
                    submit_btn = login_frame.locator(selector).first
                    await submit_btn.wait_for(state="visible", timeout=800)
                    await submit_btn.click()
                    submitted = True
                    break
                except Exception:
                    continue

            if not submitted:
                try:
                    await password_input.press("Enter")
                    submitted = True
                except Exception:
                    submitted = False

            if not submitted:
                try:
                    await login_frame.evaluate(
                        """
                        () => {
                            const pwd = document.querySelector('input[type="password"], input[name="password"], input[id="password"]');
                            const form = pwd?.closest('form') || document.querySelector('form');
                            if (form) {
                                if (typeof form.requestSubmit === 'function') {
                                    form.requestSubmit();
                                } else {
                                    form.submit();
                                }
                                return;
                            }
                            const btn = document.querySelector('button[type="submit"], input[type="submit"], button, a.loginbtn, .btn-login');
                            btn?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        }
                        """
                    )
                except Exception:
                    logger.debug("IMS 登录页回退表单提交失败", exc_info=True)

            settle_deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < settle_deadline:
                current_url = str(page.url or "")
                if self._is_ims_case_list_url(current_url):
                    return True
                if not self._is_ims_login_form_page(current_url):
                    return True
                if not await self._has_visible_ims_login_form(page):
                    return True
                await asyncio.sleep(_SHORT_WAIT)
            return False
        except Exception:
            logger.debug("IMS 登录页自动填充失败，回退人工交互", exc_info=True)
            return False

    async def _wait_for_playwright_sso_login(self: Any) -> None:  # pragma: no cover
        page = self._page
        assert page is not None

        deadline = asyncio.get_event_loop().time() + 180
        has_triggered_case_list_navigation = False
        ims_login_try_count = 0
        last_ims_login_try_at = 0.0
        while asyncio.get_event_loop().time() < deadline:
            current_url = str(page.url or "")
            if self._is_ims_case_list_url(current_url):
                return

            is_ims_login_page = self._is_ims_login_form_page(current_url) or await self._has_visible_ims_login_form(
                page
            )
            if is_ims_login_page and ims_login_try_count < 5:
                now = asyncio.get_event_loop().time()
                if now - last_ims_login_try_at >= 2:
                    last_ims_login_try_at = now
                    ims_login_try_count += 1
                    if await self._try_playwright_ims_form_login(page):
                        logger.info("检测到 IMS 登录页，已自动提交账号密码")
                        continue
                    logger.warning("检测到 IMS 登录页，自动登录第 %d 次未成功，继续重试", ims_login_try_count)

            if not has_triggered_case_list_navigation and await self._is_access_portal_logged_in(page):
                has_triggered_case_list_navigation = True
                logger.info("检测到已登录飞连门户，自动跳转 OA 列表页")
                try:
                    await page.goto(_CASE_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
                    continue
                except Exception:
                    logger.debug("飞连门户跳转 OA 列表失败，继续等待用户操作", exc_info=True)

            await asyncio.sleep(1)

        raise RuntimeError("等待扫码登录超时，请完成扫码后重试")

    # ------------------------------------------------------------------
    # 案件搜索（Playwright）
    # ------------------------------------------------------------------
    async def _search_case_by_no(self: Any, case_no: str) -> CaseSearchItem | None:  # pragma: no cover
        """在案件列表页搜索指定案件编号。"""
        page = self._page
        assert page is not None

        try:
            selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
            target_frame = await self._find_visible_frame_for_selector(selector=selector, timeout_ms=10_000)
            if target_frame is None:
                logger.warning("未找到案件编号输入框: %s", selector)
                return None

            input_locator = target_frame.locator(selector)
            await input_locator.wait_for(state="visible", timeout=10_000)
            await input_locator.fill(case_no)
            await asyncio.sleep(_SHORT_WAIT)

            logger.info("尝试按 Enter 键触发搜索...")
            await input_locator.press("Enter")

            search_triggered = False
            try:
                await target_frame.locator("#table").first.wait_for(timeout=3000)
                logger.info("Enter 键成功触发搜索")
                search_triggered = True
            except Exception:
                logger.info("Enter 键未触发搜索，尝试 JavaScript 调用 searchOk()...")
                try:
                    await target_frame.evaluate("searchOk()")
                except Exception:
                    await page.evaluate("searchOk()")

            await asyncio.sleep(_AJAX_WAIT)

            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(_AJAX_WAIT)

            data_table = target_frame.locator("table").nth(7)
            await data_table.wait_for(state="visible", timeout=15000)

            rows = await data_table.locator("tr").all()
            for row in rows[1:]:
                try:
                    cells = await row.locator("td").all()
                    if len(cells) < 4:
                        continue

                    cell_text = (await cells[3].inner_text()).strip()

                    if case_no in cell_text:
                        last_cell = cells[-1]
                        view_links = await last_cell.locator("a").all()
                        view_link_href = None
                        for link in view_links:
                            link_text = (await link.inner_text()).strip()
                            if link_text == "查看":
                                view_link_href = await link.get_attribute("href") or ""
                                break

                        if not view_link_href:
                            continue

                        keyid_match = re.search(r"keyid=([^&]+)", view_link_href)
                        if keyid_match:
                            keyid = keyid_match.group(1)
                            logger.info("找到案件: %s, keyid: %s", cell_text, keyid)
                            logger.info("通过 JavaScript 导航到详情页...")
                            try:
                                detail_url = f"{_BASE_URL}/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"
                                await page.evaluate(f"window.location.href = '{detail_url}'")
                                await page.wait_for_load_state("networkidle", timeout=60000)
                                await asyncio.sleep(_MEDIUM_WAIT)

                                tables = await page.locator("table").all()
                                logger.info("导航后表格数量: %d", len(tables))

                                return CaseSearchItem(case_no=case_no, keyid=keyid)
                            except Exception as exc:
                                logger.warning("JavaScript 导航失败: %s", exc)
                                return None

                except Exception as exc:
                    logger.debug("检查行异常: %s", exc)
                    continue

            logger.info("未在列表中找到案件: %s", case_no)
            return None

        except Exception as exc:
            logger.warning("搜索案件异常 %s: %s", case_no, exc)
            return None
