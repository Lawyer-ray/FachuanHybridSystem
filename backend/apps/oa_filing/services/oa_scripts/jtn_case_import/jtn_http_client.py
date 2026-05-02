"""HTTP 登录会话 + HTTP 查询链路。"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

from ..jtn_case_import_models import (
    OACaseData,
    OAListCaseCandidate,
    CaseListFormState,
    CaseSearchItem,
)
from .. import jtn_case_html_parser as html_parser

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


class JtnHttpClientMixin:
    """HTTP 登录会话 + HTTP 查询链路。"""

    # --- 由 facade 或其他 mixin 提供 ---
    _account: str
    _password: str
    _http_cookies_cache: dict[str, str] | None
    _name_search_http_client: httpx.Client | None
    _name_search_form_state: CaseListFormState | None
    _force_playwright_name_search: bool

    # ------------------------------------------------------------------
    # 批量 HTTP 查询
    # ------------------------------------------------------------------
    def _search_cases_via_http(
        self: Any,
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
        self: Any,
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

    # ------------------------------------------------------------------
    # HTTP 登录 + cookie 管理
    # ------------------------------------------------------------------
    def _get_or_login_http_cookies(self: Any) -> dict[str, str]:
        if self._http_cookies_cache:
            return dict(self._http_cookies_cache)

        cookies = self._http_login_and_get_cookies()
        self._http_cookies_cache = dict(cookies)
        return dict(cookies)

    def _http_login_and_get_cookies(self: Any) -> dict[str, str]:
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

    # ------------------------------------------------------------------
    # 列表页表单解析
    # ------------------------------------------------------------------
    def _load_case_list_form_state(self: Any, client: httpx.Client) -> CaseListFormState:
        """加载案件列表页面并提取 ASP.NET 表单状态。"""
        response = client.get(_CASE_LIST_URL)
        response.raise_for_status()
        self._raise_if_sso_blocking(url=str(response.url), html_text=response.text, stage="HTTP 列表页访问")
        return self._extract_form_state(html_text=response.text, base_url=str(response.url), client=client)

    def _search_case_item_via_http(
        self: Any,
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
        self: Any,
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

    # ------------------------------------------------------------------
    # HTTP 按名称查询
    # ------------------------------------------------------------------
    def _search_cases_by_name_via_http(self: Any, *, keyword: str, limit: int) -> list[OAListCaseCandidate]:
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

    def _ensure_name_search_http_session(self: Any) -> tuple[httpx.Client, CaseListFormState]:
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

    def _build_name_search_http_client(self: Any, *, cookies: dict[str, str]) -> httpx.Client:
        return httpx.Client(
            headers={**_HTTP_HEADERS, "Connection": "close"},
            follow_redirects=True,
            timeout=_DEFAULT_HTTP_TIMEOUT,
            cookies=cookies,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            trust_env=False,
        )

    def _reset_name_search_http_session(self: Any) -> None:
        if self._name_search_http_client is not None:
            self._name_search_http_client.close()
        self._name_search_http_client = None
        self._name_search_form_state = None

    # ------------------------------------------------------------------
    # ASP.NET 表单解析
    # ------------------------------------------------------------------
    def _extract_form_state(
        self: Any,
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

    def _rank_name_candidates(
        self: Any,
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

    def _resolve_case_name_field(self: Any, payload: dict[str, str]) -> str | None:
        if _SEARCH_CASE_NAME_FIELD in payload:
            return _SEARCH_CASE_NAME_FIELD

        logger.warning("未找到指定案件名称查询字段: %s", _SEARCH_CASE_NAME_FIELD)
        return None

    # ------------------------------------------------------------------
    # 登录响应判断
    # ------------------------------------------------------------------
    def _is_login_failed_response(self: Any, response: httpx.Response) -> bool:
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
