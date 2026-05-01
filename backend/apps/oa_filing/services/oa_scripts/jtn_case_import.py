"""金诚同达 OA 案件导入脚本。

通过 Playwright 自动化完成：
登录 → 搜索案件编号 → 进入详情页 → 提取3个Tab的数据（客户信息、案件信息、利益冲突）。

复用 JtnClientImportScript._login() 的登录逻辑。
"""

from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Generator
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from django.utils.translation import gettext_lazy as _
from lxml import html as lxml_html
from playwright.sync_api import Browser, BrowserContext, Frame, Page, Playwright, sync_playwright

logger = logging.getLogger("apps.oa_filing.jtn_case_import")

# ============================================================
# 常量：URL
# ============================================================
_LOGIN_URL = "https://ims.jtn.com/member/login.aspx"
_CASE_LIST_URL = "https://ims.jtn.com/project/index.aspx?FirstModel=PROJECT&SecondModel=PROJECT002"
_BASE_URL = "https://ims.jtn.com/project"
_DETAIL_URL_TEMPLATE = "{base}/projectView.aspx?keyid={keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_DEFAULT_HTTP_TIMEOUT = 20
_NAME_SEARCH_HTTP_ATTEMPTS = 2
_SEARCH_CASE_NO_FIELD = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_no"
_SEARCH_CASE_NAME_FIELD = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_name"
_SEARCH_CURRENT_PAGE_FIELD = "currentPage"

# 等待时间（秒）
_SHORT_WAIT = 0.5
_MEDIUM_WAIT = 1.5
_AJAX_WAIT = 2.0


# 数据结构（从子模块导入）
from .jtn_case_import_models import (
    OAConflictData,
    OACaseCustomerData,
    OACaseData,
    OACaseInfoData,
    OAListCaseCandidate,
    CaseListFormState,
    CaseSearchItem,
)
from . import jtn_case_html_parser as html_parser


# ============================================================
# Playwright 脚本
# ============================================================
class JtnCaseImportScript:
    """金诚同达 OA 案件导入自动化。"""

    def __init__(
        self,
        account: str,
        password: str,
        *,
        headless: bool = True,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._account = account
        self._password = password
        self._headless = bool(headless)
        self._progress_callback = progress_callback
        self._page: Page | None = None
        self._context: BrowserContext | None = None
        self._http_cookies_cache: dict[str, str] | None = None
        self._name_search_http_client: httpx.Client | None = None
        self._name_search_form_state: CaseListFormState | None = None
        self._name_search_pw: Playwright | None = None
        self._name_search_browser: Browser | None = None
        self._force_playwright_name_search = False

    def search_case(self, case_no: str) -> OACaseData | None:
        """根据案件编号搜索并提取完整数据。

        Args:
            case_no: OA案件编号，如 2024GZM0501

        Returns:
            OACaseData 或 None（未找到）
        """
        normalized_case_no = str(case_no).strip()
        if not normalized_case_no:
            return None

        for _, case_data in self.search_cases([normalized_case_no], workers=1):
            return case_data
        return None

    def search_cases_by_name(self, contract_name: str, *, limit: int = 6) -> list[OAListCaseCandidate]:
        """按案件名称查询 OA 列表候选项（仅在 HTTP 不可用时回退 Playwright）。"""
        keyword = str(contract_name or "").strip()
        if not keyword:
            return []

        effective_limit = max(1, int(limit))

        if self._force_playwright_name_search:
            return self._search_cases_by_name_via_playwright(keyword=keyword, limit=effective_limit)

        last_http_error: Exception | None = None
        for attempt in range(1, _NAME_SEARCH_HTTP_ATTEMPTS + 1):
            try:
                return self._search_cases_by_name_via_http(keyword=keyword, limit=effective_limit)
            except Exception as exc:
                last_http_error = exc
                if self._is_sso_blocking_error(exc):
                    raise
                if attempt < _NAME_SEARCH_HTTP_ATTEMPTS:
                    logger.warning(
                        "HTTP 按名称查询异常，准备重试 HTTP: keyword=%s attempt=%d/%d err=%s",
                        keyword,
                        attempt,
                        _NAME_SEARCH_HTTP_ATTEMPTS,
                        exc,
                    )
                    continue

        logger.warning("HTTP 按名称查询异常，准备回退 Playwright: keyword=%s err=%s", keyword, last_http_error)

        playwright_candidates = self._search_cases_by_name_via_playwright(keyword=keyword, limit=effective_limit)
        if playwright_candidates:
            logger.info(
                "按名称查询启用 Playwright 兜底成功: keyword=%s playwright_count=%d",
                keyword,
                len(playwright_candidates),
            )
        return playwright_candidates

    def ensure_name_search_ready(self) -> None:
        """预检查 OA 案件列表可访问性（纯 Playwright 链路）。"""
        self._force_playwright_name_search = True
        self._ensure_name_search_playwright_session()

    def search_cases(
        self,
        case_nos: list[str],
        *,
        workers: int = 1,
        playwright_fallback: bool = True,
    ) -> Generator[tuple[str, OACaseData | None], None, None]:
        """批量搜索案件。

        Args:
            case_nos: 案件编号列表
            workers: HTTP 并发数（同一登录会话下并发查询）
            playwright_fallback: HTTP 失败时是否回落 Playwright

        Yields:
            (case_no, case_data) 元组
        """
        normalized_case_nos = [str(case_no).strip() for case_no in case_nos if str(case_no).strip()]
        if not normalized_case_nos:
            return

        indexed_case_nos = list(enumerate(normalized_case_nos))
        resolved: list[OACaseData | None] = [None] * len(indexed_case_nos)

        # 先走 HTTP 直连链路（一次登录 + 多线程并发查询）。
        http_failed_indexes: list[int] = []
        try:
            http_results = self._search_cases_via_http(indexed_case_nos=indexed_case_nos, workers=workers)
            for index, _, case_data in http_results:
                resolved[index] = case_data
                if case_data is None:
                    http_failed_indexes.append(index)
        except Exception as exc:
            logger.warning("HTTP 批量查询异常，准备回落 Playwright: %s", exc)
            http_failed_indexes = [index for index, _ in indexed_case_nos]

        # HTTP 没查到或解析失败的，统一回落 Playwright（单次登录批量兜底）。
        if playwright_fallback and http_failed_indexes:
            fallback_case_nos = [normalized_case_nos[index] for index in http_failed_indexes]
            logger.info(
                "触发 Playwright 兜底: failed=%d total=%d",
                len(fallback_case_nos),
                len(normalized_case_nos),
            )
            fallback_by_case_no: dict[str, OACaseData | None] = {}
            try:
                fallback_results = list(self._search_cases_via_playwright(fallback_case_nos))
                fallback_by_case_no = dict(fallback_results)
            except Exception as exc:
                logger.warning("Playwright 兜底批量查询异常，返回空结果: %s", exc, exc_info=True)
            for index in http_failed_indexes:
                case_no = normalized_case_nos[index]
                resolved[index] = fallback_by_case_no.get(case_no)

        for index, case_no in indexed_case_nos:
            self._emit_progress(
                "searching",
                case_no=case_no,
                message=f"正在搜索案件 {case_no}",
            )
            yield case_no, resolved[index]

    def _search_cases_via_http(
        self,
        *,
        indexed_case_nos: list[tuple[int, str]],
        workers: int,
    ) -> list[tuple[int, str, OACaseData | None]]:
        """通过 HTTP 会话并发查询案件。"""
        if not indexed_case_nos:
            return []

        effective_workers = max(1, min(int(workers), len(indexed_case_nos)))
        shared_cookies = self._get_or_login_http_cookies()

        if effective_workers == 1:
            return self._search_cases_chunk_via_http(
                indexed_chunk=indexed_case_nos,
                shared_cookies=shared_cookies,
            )

        chunk_size = (len(indexed_case_nos) + effective_workers - 1) // effective_workers
        indexed_chunks = [
            indexed_case_nos[start : start + chunk_size] for start in range(0, len(indexed_case_nos), chunk_size)
        ]

        indexed_results: list[tuple[int, str, OACaseData | None] | None] = [None] * len(indexed_case_nos)
        with ThreadPoolExecutor(max_workers=effective_workers, thread_name_prefix="oa-http-search") as executor:
            futures = [
                executor.submit(
                    self._search_cases_chunk_via_http,
                    indexed_chunk=indexed_chunk,
                    shared_cookies=shared_cookies,
                )
                for indexed_chunk in indexed_chunks
            ]
            for future in as_completed(futures):
                chunk_results = future.result()
                for index, case_no, case_data in chunk_results:
                    indexed_results[index] = (index, case_no, case_data)

        ordered_results: list[tuple[int, str, OACaseData | None]] = []
        for index, case_no in indexed_case_nos:
            maybe_result = indexed_results[index]
            if maybe_result is None:
                ordered_results.append((index, case_no, None))
                continue
            ordered_results.append(maybe_result)
        return ordered_results

    def _search_cases_chunk_via_http(
        self,
        *,
        indexed_chunk: list[tuple[int, str]],
        shared_cookies: dict[str, str],
    ) -> list[tuple[int, str, OACaseData | None]]:
        """HTTP 并发 worker：复用同一登录 cookie 顺序查询一个分片。"""
        results: list[tuple[int, str, OACaseData | None]] = []

        with httpx.Client(
            headers=_HTTP_HEADERS,
            follow_redirects=True,
            timeout=_DEFAULT_HTTP_TIMEOUT,
            cookies=shared_cookies,
            trust_env=False,
        ) as client:
            form_state = self._load_case_list_form_state(client)

            for index, case_no in indexed_chunk:
                try:
                    search_item, form_state = self._search_case_item_via_http(
                        client=client,
                        case_no=case_no,
                        form_state=form_state,
                    )
                    if not search_item:
                        logger.warning("HTTP 未找到案件: %s", case_no)
                        results.append((index, case_no, None))
                        continue

                    case_data = self._fetch_case_detail_via_http(client=client, search_item=search_item)
                    results.append((index, case_no, case_data))
                except Exception as exc:
                    logger.warning("HTTP 查询案件异常 %s: %s", case_no, exc)
                    results.append((index, case_no, None))

        return results

    def _get_or_login_http_cookies(self) -> dict[str, str]:
        if self._http_cookies_cache:
            return dict(self._http_cookies_cache)

        cookies = self._http_login_and_get_cookies()
        self._http_cookies_cache = dict(cookies)
        return dict(cookies)

    def _http_login_and_get_cookies(self) -> dict[str, str]:
        """执行一次 HTTP 登录并返回可复用 cookie。"""
        logger.info("HTTP 登录 OA: %s", _LOGIN_URL)

        with httpx.Client(headers=_HTTP_HEADERS, follow_redirects=True, timeout=15, trust_env=False) as client:
            login_resp = client.get(_LOGIN_URL)
            csrf_token = html_parser.extract_hidden_input(login_resp.text, "CSRFToken")

            login_result = client.post(
                _LOGIN_URL,
                data={"CSRFToken": csrf_token, "userid": self._account, "password": self._password},
            )
            if self._is_login_failed_response(login_result):
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")

            cookies = dict(client.cookies.items())

        logger.info("HTTP 登录成功，获取 cookie=%d", len(cookies))
        return cookies

    def _load_case_list_form_state(self, client: httpx.Client) -> CaseListFormState:
        """加载案件列表页面并提取 ASP.NET 表单状态。"""
        response = client.get(_CASE_LIST_URL)
        response.raise_for_status()
        self._raise_if_sso_blocking(url=str(response.url), html_text=response.text, stage="HTTP 列表页访问")
        return self._extract_form_state(html_text=response.text, base_url=str(response.url), client=client)

    def _search_case_item_via_http(
        self,
        *,
        client: httpx.Client,
        case_no: str,
        form_state: CaseListFormState,
    ) -> tuple[CaseSearchItem | None, CaseListFormState]:
        """通过 POST 提交列表查询并返回案件 keyid。"""
        payload = dict(form_state.payload)
        payload[_SEARCH_CASE_NO_FIELD] = case_no
        payload[_SEARCH_CURRENT_PAGE_FIELD] = "1"

        response = client.post(form_state.action_url, data=payload)
        response.raise_for_status()

        next_form_state = self._extract_form_state(html_text=response.text, base_url=str(response.url), client=client)
        keyid = html_parser.extract_case_keyid_from_search_html(html_text=response.text, case_no=case_no)
        if not keyid:
            return None, next_form_state

        return CaseSearchItem(case_no=case_no, keyid=keyid), next_form_state

    def _fetch_case_detail_via_http(
        self,
        *,
        client: httpx.Client,
        search_item: CaseSearchItem,
    ) -> OACaseData | None:
        """通过 HTTP 获取案件详情并解析。"""
        detail_url = _DETAIL_URL_TEMPLATE.format(base=_BASE_URL, keyid=search_item.keyid)
        response = client.get(detail_url)
        response.raise_for_status()
        return html_parser.parse_case_detail_html(
            html_text=response.text,
            case_no=search_item.case_no,
            keyid=search_item.keyid,
        )

    def _search_cases_by_name_via_http(self, *, keyword: str, limit: int) -> list[OAListCaseCandidate]:
        try:
            client, form_state = self._ensure_name_search_http_session()
            payload = dict(form_state.payload)

            field_name = self._resolve_case_name_field(payload)
            if not field_name:
                logger.warning("未找到案件名称查询字段，跳过 HTTP 按名称查询")
                return []

            payload[field_name] = keyword
            payload[_SEARCH_CURRENT_PAGE_FIELD] = "1"

            response = client.post(form_state.action_url, data=payload)
            response.raise_for_status()
            self._name_search_form_state = self._extract_form_state(
                html_text=response.text,
                base_url=str(response.url),
                client=client,
            )
            candidates = html_parser.extract_case_candidates_from_search_html(response.text)
            return self._rank_name_candidates(keyword=keyword, candidates=candidates, limit=limit)
        except Exception:
            self._reset_name_search_http_session()
            raise

    def _ensure_name_search_http_session(self) -> tuple[httpx.Client, CaseListFormState]:
        if self._name_search_http_client is not None and self._name_search_form_state is not None:
            return self._name_search_http_client, self._name_search_form_state

        shared_cookies = self._get_or_login_http_cookies()
        client = self._build_name_search_http_client(cookies=shared_cookies)
        try:
            form_state = self._load_case_list_form_state(client)
        except Exception as exc:
            if not self._is_sso_blocking_error(exc):
                client.close()
                raise

            sso_login_url = self._extract_sso_login_url_from_text(str(exc))
            logger.warning("HTTP 会话触发 SSO，尝试在可见浏览器完成一次交互登录: %s", sso_login_url)
            try:
                refreshed_cookies = self._complete_sso_interactive_login(login_url=sso_login_url)
            finally:
                client.close()

            client = self._build_name_search_http_client(cookies=refreshed_cookies)
            try:
                form_state = self._load_case_list_form_state(client)
            except Exception as retry_exc:
                if self._is_sso_blocking_error(retry_exc):
                    client.close()
                    self._force_playwright_name_search = True
                    raise RuntimeError(str(retry_exc)) from retry_exc
                client.close()
                raise

        self._name_search_http_client = client
        self._name_search_form_state = form_state
        return client, form_state

    def _build_name_search_http_client(self, *, cookies: dict[str, str]) -> httpx.Client:
        return httpx.Client(
            headers={**_HTTP_HEADERS, "Connection": "close"},
            follow_redirects=True,
            timeout=_DEFAULT_HTTP_TIMEOUT,
            cookies=cookies,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            trust_env=False,
        )

    def _complete_sso_interactive_login(self, *, login_url: str) -> dict[str, str]:
        target_url = str(login_url or "").strip() or "https://access.jtn.com/login"
        logger.warning("请在弹出的浏览器完成飞连/企微扫码登录（系统将自动检测登录成功），最多等待 180 秒")

        pw = sync_playwright().start()
        browser: Browser | None = None
        try:
            # Docker/NAS 环境通常没有 XServer，缺少 DISPLAY 时自动走无头模式。
            _headless = not bool(os.environ.get("DISPLAY"))
            browser = pw.chromium.launch(headless=_headless)
            context = browser.new_context()
            page = context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)

            deadline = time.time() + 180
            merged_cookies = dict(self._http_cookies_cache or {})
            has_triggered_case_list_navigation = False
            while time.time() < deadline:
                if any(self._is_ims_case_list_url(str(candidate_page.url or "")) for candidate_page in context.pages):
                    logger.info("检测到浏览器已进入 OA 列表页，判定交互登录完成")
                    break

                ims_cookies = self._collect_ims_cookies_from_browser_context(context)
                if ims_cookies:
                    merged_cookies.update(ims_cookies)
                    if self._can_access_case_list_with_cookies(merged_cookies):
                        logger.info("检测到 OA 会话可用，判定交互登录完成")
                        break

                if not has_triggered_case_list_navigation and self._is_access_portal_logged_in(page):
                    has_triggered_case_list_navigation = True
                    logger.info("检测到已登录飞连门户，自动跳转 OA 列表进行会话校验")
                    try:
                        page.goto(_CASE_LIST_URL, wait_until="domcontentloaded", timeout=60_000)
                        continue
                    except Exception:
                        logger.debug("门户跳转 OA 列表失败，等待用户继续操作", exc_info=True)

                time.sleep(1)
            else:
                raise RuntimeError(str(_("等待扫码登录超时，请完成扫码后重试")))

            if not merged_cookies:
                raise RuntimeError(str(_("扫码登录完成，但未获取到 OA 会话，请重试")))

            self._http_cookies_cache = dict(merged_cookies)
            logger.info("交互登录成功，已回灌 cookie=%d", len(merged_cookies))
            return dict(merged_cookies)
        finally:
            if browser is not None:
                browser.close()
            pw.stop()

    def _is_ims_case_list_url(self, url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        if host != "ims.jtn.com":
            return False
        if path == "/member/login.aspx":
            return False
        return path.startswith("/project/")

    def _is_access_portal_logged_in(self, page: Page) -> bool:
        current_url = str(page.url or "").lower()
        if "access.jtn.com" not in current_url:
            return False
        if "/login" in current_url:
            return False
        try:
            content_text = str(page.content() or "")
        except Exception:
            return False
        markers = ("推荐应用", "搜索应用/平台名称", "IMS", "aijagent")
        return any(marker in content_text for marker in markers)

    def _collect_ims_cookies_from_browser_context(self, context: BrowserContext) -> dict[str, str]:
        return {
            str(item.get("name") or ""): str(item.get("value") or "")
            for item in context.cookies("https://ims.jtn.com")
            if str(item.get("name") or "").strip()
        }

    def _can_access_case_list_with_cookies(self, cookies: dict[str, str]) -> bool:
        if not cookies:
            return False
        try:
            with httpx.Client(
                headers=_HTTP_HEADERS,
                follow_redirects=True,
                timeout=10,
                cookies=cookies,
                trust_env=False,
            ) as client:
                response = client.get(_CASE_LIST_URL)
                response.raise_for_status()
                return not self._is_sso_login_page(url=str(response.url), html_text=response.text)
        except Exception:
            return False

    def _reset_name_search_http_session(self) -> None:
        if self._name_search_http_client is not None:
            self._name_search_http_client.close()
        self._name_search_http_client = None
        self._name_search_form_state = None

    def _search_cases_by_name_via_playwright(self, *, keyword: str, limit: int) -> list[OAListCaseCandidate]:
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

    def _ensure_name_search_playwright_session(self) -> None:
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

    def _rank_name_candidates(
        self,
        *,
        keyword: str,
        candidates: list[OAListCaseCandidate],
        limit: int,
    ) -> list[OAListCaseCandidate]:
        normalized = html_parser.normalize_text(keyword)
        ordered_candidates = list(candidates)
        ordered_candidates.sort(
            key=lambda item: (
                0 if normalized and normalized in html_parser.normalize_text(item.case_name) else 1,
                item.case_no,
                item.keyid,
            )
        )
        return ordered_candidates[: max(1, int(limit))]

    def _extract_form_state(
        self,
        *,
        html_text: str,
        base_url: str,
        client: httpx.Client | None = None,
        depth: int = 0,
    ) -> CaseListFormState:
        """解析 ASP.NET 表单状态（隐藏字段 + 过滤条件）。"""
        try:
            root = lxml_html.fromstring(html_text)
        except Exception as exc:
            raise RuntimeError(f"解析案件列表HTML失败: {exc}") from exc

        forms = root.xpath('//form[@id="aspnetForm"]')
        if not forms:
            if client is not None and depth < 2:
                frame_src_list = root.xpath("//iframe[@src]/@src | //frame[@src]/@src")
                for frame_src in frame_src_list:
                    src_text = str(frame_src or "").strip()
                    if not src_text or src_text.lower().startswith("javascript:"):
                        continue
                    frame_url = urljoin(base_url, src_text)
                    try:
                        frame_resp = client.get(frame_url)
                        frame_resp.raise_for_status()
                        logger.info("案件列表页未直接命中表单，尝试 frame 回退: %s", frame_url)
                        return self._extract_form_state(
                            html_text=frame_resp.text,
                            base_url=str(frame_resp.url),
                            client=client,
                            depth=depth + 1,
                        )
                    except Exception as exc:
                        logger.warning("案件列表 frame 回退失败 url=%s err=%s", frame_url, exc)

            raise RuntimeError("案件列表页缺少 aspnetForm，无法执行 HTTP 查询")
        form = forms[0]

        action_attr = form.get("action") or _CASE_LIST_URL
        action_url = urljoin(base_url, action_attr)
        payload: dict[str, str] = {}

        for input_node in form.xpath(".//input[@name]"):
            name = str(input_node.get("name") or "").strip()
            if not name:
                continue
            input_type = str(input_node.get("type") or "text").strip().lower()
            if input_type in {"submit", "button", "image", "file", "reset"}:
                continue
            if input_type in {"checkbox", "radio"} and input_node.get("checked") is None:
                continue
            payload[name] = str(input_node.get("value") or "")

        for select_node in form.xpath(".//select[@name]"):
            name = str(select_node.get("name") or "").strip()
            if not name:
                continue
            selected = select_node.xpath("./option[@selected]")
            option = selected[0] if selected else (select_node.xpath("./option") or [None])[0]
            if option is None:
                payload[name] = ""
                continue
            option_value = option.get("value")
            payload[name] = (
                str(option_value) if option_value is not None else html_parser.normalize_text("".join(option.itertext()))
            )

        for textarea_node in form.xpath(".//textarea[@name]"):
            name = str(textarea_node.get("name") or "").strip()
            if not name:
                continue
            payload[name] = html_parser.normalize_text("".join(textarea_node.itertext()))

        return CaseListFormState(action_url=action_url, payload=payload)

    def _resolve_case_name_field(self, payload: dict[str, str]) -> str | None:
        if _SEARCH_CASE_NAME_FIELD in payload:
            return _SEARCH_CASE_NAME_FIELD

        logger.warning("未找到指定案件名称查询字段: %s", _SEARCH_CASE_NAME_FIELD)
        return None


    def _is_login_failed_response(self, response: httpx.Response) -> bool:
        """根据登录响应判断是否仍停留在登录失败状态。"""
        url_lower = str(response.url).lower()
        body_lower = response.text.lower()
        head = body_lower[:2500]

        stayed_on_login_page = "member/login.aspx" in url_lower
        has_userid_input = 'name="userid"' in head or "name='userid'" in head
        has_password_input = 'name="password"' in head or "name='password'" in head
        has_login_form = has_userid_input and has_password_input
        has_login_error_text = any(
            token in body_lower for token in ("账号或密码错误", "用户名或密码错误", "invalid password", "login failed")
        )
        return bool((stayed_on_login_page and has_login_form) or has_login_error_text)

    def _is_sso_login_page(self, *, url: str, html_text: str) -> bool:
        url_text = str(url or "").strip()
        parsed = urlparse(url_text)
        host = str(parsed.hostname or "").lower()
        if host == "access.jtn.com" or host.endswith(".access.jtn.com"):
            return True

        text_lower = str(html_text or "").lower()
        markers = (
            "企业微信 quick login",
            "please scan the qr code above in wechat work",
            "multiple-pages/qrcode-login",
            "access.jtn.com/login",
            "access.jtn.com/multiple-pages",
        )
        return any(marker in text_lower for marker in markers)

    def _build_sso_blocking_message(self, *, stage: str, login_url: str) -> str:
        return str(
            _(
                "%(stage)s 触发飞连/企微单点登录（二维码），当前自动化无法完成无交互登录。"
                "请先在可见浏览器完成扫码登录后重试：%(login_url)s"
            )
            % {"stage": stage, "login_url": login_url}
        )

    def _raise_if_sso_blocking(self, *, url: str, html_text: str, stage: str) -> None:
        if not self._is_sso_login_page(url=url, html_text=html_text):
            return
        login_url = str(url or "").strip()
        message = self._build_sso_blocking_message(stage=stage, login_url=login_url)
        logger.warning("%s", message)
        raise RuntimeError(message)

    def _is_sso_blocking_error(self, exc: Exception) -> bool:
        text = str(exc or "")
        return "飞连/企微单点登录（二维码）" in text

    def _extract_sso_login_url_from_text(self, text: str) -> str:
        message = str(text or "")
        matched = re.search(r"https://access\.jtn\.com/[^\s\"'<>]+", message)
        if matched:
            return str(matched.group(0)).strip()
        return "https://access.jtn.com/login"

    def _search_cases_via_playwright(
        self,
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

    def _find_visible_frame_for_selector(self, *, selector: str, timeout_ms: int) -> Frame | None:
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

    def _ensure_case_list_ready(self) -> None:
        """确保当前在案件列表页并且搜索输入框可用。"""
        selector = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
        target_frame = self._find_visible_frame_for_selector(selector=selector, timeout_ms=2_000)
        if target_frame is not None:
            return
        self._navigate_to_case_list()

    def close(self) -> None:
        self._reset_name_search_http_session()
        if self._name_search_browser is not None:
            self._name_search_browser.close()
        if self._name_search_pw is not None:
            self._name_search_pw.stop()
        self._name_search_browser = None
        self._name_search_pw = None
        self._context = None
        self._page = None

    def _emit_progress(self, event: str, **payload: Any) -> None:
        if self._progress_callback is None:
            return
        try:
            self._progress_callback({"event": event, **payload})
        except Exception:
            logger.debug("进度回调处理异常: event=%s", event, exc_info=True)

    def _inject_cookies_to_context(self, cookies: dict[str, str]) -> None:
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

    def _login(self) -> None:
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

    def _navigate_to_case_list(self) -> None:
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

    def _is_ims_login_form_page(self, url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        return host == "ims.jtn.com" and path == "/member/login.aspx"

    def _resolve_ims_login_frame(self, page: Page) -> Frame | None:
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

    def _has_visible_ims_login_form(self, page: Page) -> bool:
        login_frame = self._resolve_ims_login_frame(page)
        if login_frame is None:
            return False
        try:
            return login_frame.locator('input[type="password"]').first.is_visible(timeout=500)
        except Exception:
            return False

    def _try_playwright_ims_form_login(self, page: Page) -> bool:
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

    def _wait_for_playwright_sso_login(self) -> None:
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

    def _search_case_by_no(self, case_no: str) -> CaseSearchItem | None:
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

    def _fetch_case_detail(self, search_item: CaseSearchItem) -> OACaseData | None:
        """打开案件详情页，提取3个Tab的数据。

        注意：如果页面已经在详情页（由 _search_case_by_no 通过 JavaScript 导航后），
        则不需要再次 goto。
        """
        page = self._page
        assert page is not None

        detail_url = _DETAIL_URL_TEMPLATE.format(base=_BASE_URL, keyid=search_item.keyid)
        logger.info("进入案件详情: %s (keyid: %s)", search_item.case_no, search_item.keyid)

        try:
            # 检查当前页面是否已经是详情页（通过表格数量判断）
            tables = page.locator("table").all()
            if len(tables) < 20:  # 详情页应该有 28 个表格，列表页只有 7 个
                logger.info("当前不在详情页，执行 goto...")
                page.goto(
                    detail_url,
                    wait_until="networkidle",
                    timeout=60000,
                )
                time.sleep(_MEDIUM_WAIT)
            else:
                logger.info("当前已在详情页，直接提取数据...")

            # 初始化返回数据
            case_data = OACaseData(case_no=search_item.case_no, keyid=search_item.keyid)

            # Tab 1: 客户信息
            case_data.customers = self._extract_customer_tab()

            # Tab 2: 案件信息
            case_data.case_info = self._extract_case_info_tab()

            # Tab 3: 利益冲突信息
            case_data.conflicts = self._extract_conflict_tab()

            logger.info(
                "解析案件详情完成: case_no=%s, customers=%d, conflicts=%d",
                case_data.case_no,
                len(case_data.customers),
                len(case_data.conflicts),
            )
            return case_data

        except Exception as exc:
            logger.warning("提取案件详情异常 %s: %s", search_item.case_no, exc)
            return None

    def _extract_customer_tab(self) -> list[OACaseCustomerData]:
        """提取客户信息Tab（Tab 1）。"""
        page = self._page
        assert page is not None

        customers: list[OACaseCustomerData] = []

        try:
            # 所有Tab内容都在一页上，不需要switchTab
            # 表格1 (索引1): 客户信息 - 47行

            tables = page.locator("table").all()
            if len(tables) > 1:
                customer_table = tables[1]  # 索引1是客户信息表
                rows = customer_table.locator("tr").all()

                current_customer: OACaseCustomerData | None = None

                for row in rows:
                    try:
                        cells = row.locator("td").all()
                        if not cells:
                            continue

                        row_text = row.inner_text()
                        cell_count = len(cells)

                        # 检查是否是标题行（包含"客户"和"信息"）
                        if "客户" in row_text and "信息" in row_text and "（" in row_text:
                            # 保存上一个客户
                            if current_customer and current_customer.name:
                                customers.append(current_customer)
                            # 提取客户名称
                            # 格式: "客户（XXX）信息"
                            name_match = re.search(r"客户（([^）]+)）信息", row_text)
                            if name_match:
                                customer_name = name_match.group(1)
                                # 判断是企业还是自然人
                                is_legal = "企业" in row_text or "公司" in customer_name
                                current_customer = OACaseCustomerData(
                                    name=customer_name,
                                    customer_type="legal" if is_legal else "natural",
                                )
                            else:
                                current_customer = None
                            continue

                        # 数据行解析
                        if current_customer and cell_count >= 2:
                            # 尝试2列或4列布局
                            for i in range(0, cell_count - 1, 2):
                                label_cell = cells[i].inner_text().strip()
                                value_cell = cells[i + 1].inner_text().strip() if i + 1 < cell_count else ""

                                # 解析标签
                                if "地址" in label_cell:
                                    current_customer.address = value_cell
                                elif any(x in label_cell for x in ("电话", "号码")):
                                    current_customer.phone = value_cell
                                elif "身份证" in label_cell:
                                    current_customer.id_number = value_cell
                                elif "行业" in label_cell:
                                    current_customer.industry = value_cell
                                elif any(x in label_cell for x in ("法定代表", "负责人", "姓名")):
                                    current_customer.legal_representative = value_cell

                    except Exception as exc:
                        logger.debug("解析客户行异常: %s", exc)
                        continue

                # 保存最后一个客户
                if current_customer and current_customer.name:
                    customers.append(current_customer)

            logger.info("提取客户信息: %d 个客户", len(customers))
            return customers

        except Exception as exc:
            logger.warning("提取客户信息Tab异常: %s", exc)

        return customers

    def _extract_case_info_tab(self) -> OACaseInfoData | None:
        """提取案件信息Tab（Tab 2）。"""
        page = self._page
        assert page is not None

        try:
            # 所有Tab内容都在一页上，不需要switchTab
            # 表格2 (索引2): 案件基本信息 - 24行
            # 表格结构: 每个单元格交替包含标签和值

            tables = page.locator("table").all()
            if len(tables) > 2:
                case_table = tables[2]  # 索引2是案件基本信息表
                rows = case_table.locator("tr").all()

                case_info = OACaseInfoData(case_no="")

                for row in rows:
                    try:
                        cells = row.locator("td").all()
                        if len(cells) < 2:
                            continue

                        row_text = row.inner_text().strip()

                        # 检查是否是案件基本信息标题行
                        if "案件基本信息" in row_text:
                            continue

                        # 解析标签-值对（交错排列）
                        for i in range(0, len(cells) - 1, 2):
                            label = cells[i].inner_text().strip()
                            value = cells[i + 1].inner_text().strip()

                            if not label:
                                continue

                            if "案件名称" in label:
                                case_info.case_name = value
                            elif "案件阶段" in label:
                                case_info.case_stage = value
                            elif "收案日期" in label:
                                case_info.acceptance_date = value
                            elif "案件类别" in label or "案件类型" in label:
                                case_info.case_category = value
                            elif "业务种类" in label:
                                case_info.case_type = value
                            elif "案件负责人" in label:
                                case_info.responsible_lawyer = value
                            elif "案情简介" in label:
                                case_info.description = value[:500] if value else None
                            elif "代理何方" in label:
                                case_info.client_side = value
                            elif "案件编号" in label:
                                case_info.case_no = value

                    except Exception as exc:
                        logger.debug("解析案件信息行异常: %s", exc)
                        continue

                logger.info(
                    "提取案件信息: no=%s, name=%s, stage=%s",
                    case_info.case_no,
                    case_info.case_name,
                    case_info.case_stage,
                )
                return case_info

        except Exception as exc:
            logger.warning("提取案件信息Tab异常: %s", exc)

        return None

    def _extract_conflict_tab(self) -> list[OAConflictData]:
        """提取利益冲突信息Tab（Tab 3）。"""
        page = self._page
        assert page is not None

        conflicts: list[OAConflictData] = []

        try:
            # 所有Tab内容都在一页上，不需要switchTab
            # 表格3 (索引3): 利益冲突信息 - 21行
            # 表格结构: 每行4列 [标签1, 值1, 标签2, 值2]

            tables = page.locator("table").all()
            if len(tables) > 3:
                conflict_table = tables[3]  # 索引3是利益冲突信息表
                rows = conflict_table.locator("tr").all()

                current_name = None
                current_type = None

                for row in rows:
                    try:
                        cells = row.locator("td").all()
                        if not cells:
                            continue

                        row_text = row.inner_text().strip()

                        # 检查是否是标题行
                        if "利益冲突" in row_text:
                            continue

                        # 解析标签-值对
                        for i in range(0, len(cells) - 1, 2):
                            label = cells[i].inner_text().strip()
                            value = cells[i + 1].inner_text().strip() if i + 1 < len(cells) else ""

                            if not label:
                                continue

                            if "中文名称" in label and value:
                                # 保存上一个冲突方（如果有）
                                if current_name:
                                    conflicts.append(
                                        OAConflictData(
                                            name=current_name,
                                            conflict_type=current_type,
                                        )
                                    )
                                current_name = value
                                current_type = None
                            elif ("法律地位" in label and value) or (
                                "类型" in label and "客户类型" not in label and "法律地位" not in label and value
                            ):
                                current_type = value

                    except Exception as exc:
                        logger.debug("解析利益冲突行异常: %s", exc)
                        continue

                # 保存最后一个冲突方
                if current_name:
                    conflicts.append(
                        OAConflictData(
                            name=current_name,
                            conflict_type=current_type,
                        )
                    )

        except Exception as exc:
            logger.warning("提取利益冲突Tab异常: %s", exc)

        logger.info("提取利益冲突: %d 个", len(conflicts))
        return conflicts
