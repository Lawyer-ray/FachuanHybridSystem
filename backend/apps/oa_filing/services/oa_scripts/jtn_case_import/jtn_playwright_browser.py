"""Playwright 导航 + IMS 表单 + 搜索链路。"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Generator
from urllib.parse import urlparse

import httpx
from django.utils.translation import gettext_lazy as _
from playwright.sync_api import Browser, BrowserContext, Frame, Page, Playwright, sync_playwright

from ..jtn_case_import_models import (
    OACaseData,
    OAListCaseCandidate,
    CaseSearchItem,
)
from .. import jtn_case_html_parser as html_parser
from .jtn_http_client import (
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


class JtnPlaywrightBrowserMixin:
    """Playwright 导航 + IMS 表单 + 搜索链路。"""

    # --- 由 facade 或其他 mixin 提供 ---
    _account: str
    _password: str
    _headless: bool
    _page: Page | None
    _context: BrowserContext | None
    _http_cookies_cache: dict[str, str] | None
    _name_search_pw: Playwright | None
    _name_search_browser: Browser | None
    _force_playwright_name_search: bool

    # ------------------------------------------------------------------
    # Playwright 兜底批量查询
    # ------------------------------------------------------------------
    def _search_cases_via_playwright(
        self: Any,
        case_nos: list[str],
    ) -> list[tuple[str, OACaseData | None]]:
        """Playwright 兜底批量查询。"""
        pw = sync_playwright().start()
        browser = None
        fallback_results: list[tuple[str, OACaseData | None]] = []
        try:
            browser = pw.chromium.launch(headless=self._headless)
            self._context = browser.new_context()

            # 应用 playwright-stealth 反检测
            try:
                from playwright_stealth import Stealth

                stealth = Stealth()
                stealth.apply_stealth_sync(self._context)
                logger.debug("已应用 playwright-stealth 反检测")
            except ImportError:
                logger.warning("playwright-stealth 未安装，跳过反检测")

            self._context.set_default_timeout(30_000)
            self._context.set_default_navigation_timeout(30_000)
            self._page = self._context.new_page()

            self._login()
            self._navigate_to_case_list()

            for case_no in case_nos:
                try:
                    logger.info("搜索案件: %s", case_no)
                    # 抓取上一条案件详情后页面可能停留在详情页，下一次搜索前确保回到列表页。
                    self._ensure_case_list_ready()

                    search_item = self._search_case_by_no(case_no)
                    if not search_item:
                        logger.warning("未找到案件: %s", case_no)
                        fallback_results.append((case_no, None))
                        continue

                    case_data = self._fetch_case_detail(search_item)
                    fallback_results.append((case_no, case_data))
                except Exception as exc:
                    logger.warning("Playwright 兜底查询异常 %s: %s", case_no, exc, exc_info=True)
                    fallback_results.append((case_no, None))

        finally:
            if browser is not None:
                browser.close()
            pw.stop()
        return fallback_results

    def _search_cases_by_name_via_playwright(self: Any, *, keyword: str, limit: int) -> list[OAListCaseCandidate]:
        try:
            self._ensure_name_search_playwright_session()
            page = self._page
            assert page is not None

            selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_name"
            target_frame = self._find_visible_frame_for_selector(selector=selector, timeout_ms=15_000)
            if target_frame is None:
                raise RuntimeError(f"未找到案件名称输入框: {selector}")

            input_locator = target_frame.locator(selector)
            input_locator.wait_for(state="visible", timeout=15_000)
            input_locator.fill(keyword)
            time.sleep(_SHORT_WAIT)

            try:
                target_frame.evaluate("searchOk()")
            except Exception:
                page.evaluate("searchOk()")

            time.sleep(_AJAX_WAIT)
            page.wait_for_load_state("networkidle", timeout=15_000)
            time.sleep(_SHORT_WAIT)

            html_text = target_frame.content()
            candidates = html_parser.extract_case_candidates_from_search_html(html_text)
            return self._rank_name_candidates(keyword=keyword, candidates=candidates, limit=limit)
        except Exception as exc:
            if self._is_sso_blocking_error(exc):
                raise
            logger.warning("Playwright 按名称查询异常 keyword=%s: %s", keyword, exc, exc_info=True)
            return []

    def _ensure_name_search_playwright_session(self: Any) -> None:
        if self._name_search_browser is not None and self._page is not None and self._context is not None:
            try:
                self._ensure_case_list_ready()
                return
            except Exception:
                self.close()

        self._name_search_pw = sync_playwright().start()
        self._name_search_browser = self._name_search_pw.chromium.launch(headless=self._headless)
        self._context = self._name_search_browser.new_context()

        try:
            from playwright_stealth import Stealth

            stealth = Stealth()
            stealth.apply_stealth_sync(self._context)
            logger.debug("已应用 playwright-stealth 反检测")
        except ImportError:
            logger.warning("playwright-stealth 未安装，跳过反检测")

        self._context.set_default_timeout(30_000)
        self._context.set_default_navigation_timeout(30_000)
        self._page = self._context.new_page()

        self._login()
        self._navigate_to_case_list()
        self._ensure_case_list_ready()

    # ------------------------------------------------------------------
    # Frame / 页面工具
    # ------------------------------------------------------------------
    def _find_visible_frame_for_selector(self: Any, *, selector: str, timeout_ms: int) -> Frame | None:
        page = self._page
        assert page is not None

        deadline = time.time() + (max(100, timeout_ms) / 1000)
        while time.time() < deadline:
            for frame in page.frames:
                try:
                    locator = frame.locator(selector)
                    if locator.count() <= 0:
                        continue
                    locator.first.wait_for(state="visible", timeout=300)
                    return frame
                except Exception:
                    continue
            time.sleep(0.2)
        return None

    def _ensure_case_list_ready(self: Any) -> None:
        """确保当前在案件列表页并且搜索输入框可用。"""
        selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
        target_frame = self._find_visible_frame_for_selector(selector=selector, timeout_ms=2_000)
        if target_frame is not None:
            return
        self._navigate_to_case_list()

    # ------------------------------------------------------------------
    # Cookie 注入 + Playwright 登录
    # ------------------------------------------------------------------
    def _inject_cookies_to_context(self: Any, cookies: dict[str, str]) -> None:
        """将 cookie 字典注入 Playwright context。"""
        context = self._context
        assert context is not None
        if not cookies:
            return

        context.add_cookies(
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

    def _login(self: Any) -> None:
        """通过 httpx 接口登录，将 cookie 注入 Playwright context。"""
        cached_cookies = self._http_cookies_cache or {}
        if cached_cookies:
            logger.info("接口登录复用 HTTP cookie=%s", len(cached_cookies))
            self._inject_cookies_to_context(cached_cookies)
            return

        logger.info("接口登录: %s", _LOGIN_URL)

        with httpx.Client(headers=_HTTP_HEADERS, follow_redirects=True, timeout=15, trust_env=False) as client:
            # 1. GET 登录页，拿 ASP.NET_SessionId + CSRFToken
            r = client.get(_LOGIN_URL)
            csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', r.text)
            csrf = csrf_match.group(1) if csrf_match else ""

            # 2. POST 登录
            r2 = client.post(
                _LOGIN_URL,
                data={"CSRFToken": csrf, "userid": self._account, "password": self._password},
            )

            if self._is_login_failed_response(r2):
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")

            cookies = dict(client.cookies.items())
            self._http_cookies_cache = cookies
            self._inject_cookies_to_context(cookies)

        logger.info("接口登录成功，cookie 已注入")

    # ------------------------------------------------------------------
    # 导航到案件列表页
    # ------------------------------------------------------------------
    def _navigate_to_case_list(self: Any) -> None:
        """导航到案件列表页。"""
        page = self._page
        assert page is not None

        def _goto_case_list_once() -> None:
            page.goto(_CASE_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                logger.debug("案件列表页未达到 networkidle，继续后续检测")

        logger.info("导航到案件列表页: %s", _CASE_LIST_URL)
        _goto_case_list_once()

        try:
            self._raise_if_sso_blocking(url=page.url, html_text=page.content(), stage="Playwright 列表页访问")
        except Exception as exc:
            if not self._is_sso_blocking_error(exc):
                raise
            logger.warning("Playwright 触发 SSO，等待当前浏览器完成交互登录")
            self._wait_for_playwright_sso_login()
            _goto_case_list_once()
            self._raise_if_sso_blocking(url=page.url, html_text=page.content(), stage="Playwright 列表页访问")

        if self._is_ims_login_form_page(str(page.url or "")) or self._has_visible_ims_login_form(page):
            logger.warning("检测到 IMS 登录页，等待自动/人工登录完成")
            self._wait_for_playwright_sso_login()
            _goto_case_list_once()

        # 关闭可能存在的模态对话框，并等待页面完全渲染
        try:
            confirm_btn = page.get_by_role("button", name="确定")
            if confirm_btn.is_visible(timeout=3000):
                logger.info("检测到模态对话框，关闭中...")
                confirm_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(_MEDIUM_WAIT)
        except Exception:
            pass

        selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
        target_frame = self._find_visible_frame_for_selector(selector=selector, timeout_ms=15_000)
        if target_frame is None:
            if self._is_ims_login_form_page(str(page.url or "")) or self._has_visible_ims_login_form(page):
                logger.warning("搜索输入框未找到，当前仍在 IMS 登录页，等待登录后重试")
                self._wait_for_playwright_sso_login()
                _goto_case_list_once()
                target_frame = self._find_visible_frame_for_selector(selector=selector, timeout_ms=15_000)

            if target_frame is None:
                raise RuntimeError(str(_("案件列表页搜索输入框未就绪，请完成登录后重试")))

        time.sleep(_MEDIUM_WAIT)
        logger.info("已进入案件列表页面")

    # ------------------------------------------------------------------
    # IMS 登录页检测与自动填充
    # ------------------------------------------------------------------
    def _is_ims_login_form_page(self: Any, url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        return host == "ims.jtn.com" and path == "/member/login.aspx"

    def _resolve_ims_login_frame(self: Any, page: Page) -> Frame | None:
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
                    if locator.count() <= 0:
                        continue
                    try:
                        locator.first.wait_for(state="visible", timeout=500)
                        has_visible_user = True
                        break
                    except Exception:
                        continue

                has_visible_password = False
                for selector in password_selectors:
                    locator = frame.locator(selector)
                    if locator.count() <= 0:
                        continue
                    try:
                        locator.first.wait_for(state="visible", timeout=500)
                        has_visible_password = True
                        break
                    except Exception:
                        continue

                if has_visible_user and has_visible_password:
                    return frame
            except Exception:
                continue
        return None

    def _has_visible_ims_login_form(self: Any, page: Page) -> bool:
        login_frame = self._resolve_ims_login_frame(page)
        if login_frame is None:
            return False
        try:
            return login_frame.locator('input[type="password"]').first.is_visible(timeout=500)
        except Exception:
            return False

    def _try_playwright_ims_form_login(self: Any, page: Page) -> bool:
        if not self._account or not self._password:
            return False

        login_frame = self._resolve_ims_login_frame(page)
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
                candidate.wait_for(state="visible", timeout=1_000)
                user_input = candidate
                break
            except Exception:
                continue

        for selector in password_selectors:
            try:
                candidate = login_frame.locator(selector).first
                candidate.wait_for(state="visible", timeout=1_000)
                password_input = candidate
                break
            except Exception:
                continue

        if user_input is None or password_input is None:
            logger.warning("已命中 IMS 登录页，但未定位到用户名/密码输入框")
            return False

        try:
            user_input.fill("")
            user_input.fill(self._account)
            password_input.fill("")
            password_input.fill(self._password)

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
                    submit_btn.wait_for(state="visible", timeout=800)
                    submit_btn.click()
                    submitted = True
                    break
                except Exception:
                    continue

            if not submitted:
                try:
                    password_input.press("Enter")
                    submitted = True
                except Exception:
                    submitted = False

            if not submitted:
                try:
                    login_frame.evaluate(
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

            settle_deadline = time.time() + 20
            while time.time() < settle_deadline:
                current_url = str(page.url or "")
                if self._is_ims_case_list_url(current_url):
                    return True
                if not self._is_ims_login_form_page(current_url):
                    return True
                if not self._has_visible_ims_login_form(page):
                    return True
                time.sleep(_SHORT_WAIT)
            return False
        except Exception:
            logger.debug("IMS 登录页自动填充失败，回退人工交互", exc_info=True)
            return False

    def _wait_for_playwright_sso_login(self: Any) -> None:
        page = self._page
        assert page is not None

        deadline = time.time() + 180
        has_triggered_case_list_navigation = False
        ims_login_try_count = 0
        last_ims_login_try_at = 0.0
        while time.time() < deadline:
            current_url = str(page.url or "")
            if self._is_ims_case_list_url(current_url):
                return

            is_ims_login_page = self._is_ims_login_form_page(current_url) or self._has_visible_ims_login_form(page)
            if is_ims_login_page and ims_login_try_count < 5:
                now = time.time()
                if now - last_ims_login_try_at >= 2:
                    last_ims_login_try_at = now
                    ims_login_try_count += 1
                    if self._try_playwright_ims_form_login(page):
                        logger.info("检测到 IMS 登录页，已自动提交账号密码")
                        continue
                    logger.warning("检测到 IMS 登录页，自动登录第 %d 次未成功，继续重试", ims_login_try_count)

            if not has_triggered_case_list_navigation and self._is_access_portal_logged_in(page):
                has_triggered_case_list_navigation = True
                logger.info("检测到已登录飞连门户，自动跳转 OA 列表页")
                try:
                    page.goto(_CASE_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
                    continue
                except Exception:
                    logger.debug("飞连门户跳转 OA 列表失败，继续等待用户操作", exc_info=True)

            time.sleep(1)

        raise RuntimeError(str(_("等待扫码登录超时，请完成扫码后重试")))

    # ------------------------------------------------------------------
    # 案件搜索（Playwright）
    # ------------------------------------------------------------------
    def _search_case_by_no(self: Any, case_no: str) -> CaseSearchItem | None:
        """在案件列表页搜索指定案件编号。"""
        page = self._page
        assert page is not None

        try:
            # 输入案件编号（支持列表在 iframe 中）
            selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
            target_frame = self._find_visible_frame_for_selector(selector=selector, timeout_ms=10_000)
            if target_frame is None:
                logger.warning("未找到案件编号输入框: %s", selector)
                return None

            input_locator = target_frame.locator(selector)
            input_locator.wait_for(state="visible", timeout=10_000)
            input_locator.fill(case_no)
            time.sleep(_SHORT_WAIT)

            # 优先尝试按 Enter 键触发搜索（很多ASP.NET页面支持）
            logger.info("尝试按 Enter 键触发搜索...")
            input_locator.press("Enter")

            # 立即检查Enter键是否成功触发搜索
            search_triggered = False
            try:
                target_frame.locator("#table").first.wait_for(timeout=3000)
                logger.info("Enter 键成功触发搜索")
                search_triggered = True
            except Exception:
                logger.info("Enter 键未触发搜索，尝试 JavaScript 调用 searchOk()...")
                # 搜索按钮是 <A onclick='searchOk()'>查　询</A>
                try:
                    target_frame.evaluate("searchOk()")
                except Exception:
                    page.evaluate("searchOk()")

            # 等待AJAX完成
            time.sleep(_AJAX_WAIT)

            # 等待表格加载 - 使用正确的表格选择器
            # ASP.NET页面的数据在第8个表格（索引7）
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(_AJAX_WAIT)

            # 等待数据行出现（通过检查表格行数）
            data_table = target_frame.locator("table").nth(7)  # 第8个表格是数据列表
            data_table.wait_for(state="visible", timeout=15000)

            # 查找案件编号匹配的行（跳过表头行）
            rows = data_table.locator("tr").all()
            for row in rows[1:]:  # 跳过表头
                try:
                    # 案件编号在第4列(td[3])
                    cells = row.locator("td").all()
                    if len(cells) < 4:
                        continue

                    # td[3] 包含案件名称和案件编号（通过<br>分隔）
                    cell_text = cells[3].inner_text().strip()

                    if case_no in cell_text:
                        # 从最后一个 td 的下拉菜单中找到"查看"链接
                        # 格式: projectView.aspx?keyid=xxx&...
                        last_cell = cells[-1]
                        view_links = last_cell.locator("a").all()
                        view_link_href = None
                        for link in view_links:
                            link_text = link.inner_text().strip()
                            if link_text == "查看":
                                view_link_href = link.get_attribute("href") or ""
                                break

                        if not view_link_href:
                            continue

                        keyid_match = re.search(r"keyid=([^&]+)", view_link_href)
                        if keyid_match:
                            keyid = keyid_match.group(1)
                            logger.info("找到案件: %s, keyid: %s", cell_text, keyid)
                            # 通过 JavaScript 导航到详情页，保持 ASP.NET session
                            logger.info("通过 JavaScript 导航到详情页...")
                            try:
                                # 使用 JavaScript 导航，保持 session 状态
                                detail_url = f"{_BASE_URL}/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"
                                page.evaluate(f"window.location.href = '{detail_url}'")
                                page.wait_for_load_state("networkidle", timeout=60000)
                                time.sleep(_MEDIUM_WAIT)

                                # 验证页面已经跳转到详情页（通过检查表格数量）
                                tables = page.locator("table").all()
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
