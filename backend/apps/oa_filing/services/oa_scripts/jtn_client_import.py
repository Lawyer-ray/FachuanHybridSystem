"""金诚同达 OA 客户导入脚本。

默认走 HTTP 批量查询，失败时回落 Playwright 兜底：
登录 → 客户列表分页 → 客户详情提取。
"""

from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Generator
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from lxml import html as lxml_html
from playwright.sync_api import BrowserContext, Page, sync_playwright

logger = logging.getLogger("apps.oa_filing.jtn_client_import")

# ============================================================
# 常量：URL
# ============================================================
_LOGIN_URL = "https://ims.jtn.com/member/login.aspx"
_CLIENT_LIST_URL = "https://ims.jtn.com/customer/index.aspx?Category=A&FirstModel=PROJECT&SecondModel=PROJECT001"
_BASE_URL = "https://ims.jtn.com/customer"
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_DEFAULT_HTTP_TIMEOUT = 20
_LIST_CURRENT_PAGE_FIELD = "currentPage"

# 等待时间（秒）
_SHORT_WAIT = 0.5
_MEDIUM_WAIT = 1.5
_AJAX_WAIT = 2.0


@dataclass
class OACustomerData:
    """OA客户数据。"""

    name: str  # 客户名称
    client_type: str  # natural=自然人 / legal=企业
    phone: str | None = None  # 联系电话
    address: str | None = None  # 地址
    id_number: str | None = None  # 身份证号码（自然人）
    legal_representative: str | None = None  # 法定代表人（企业）
    gender: str | None = None  # 性别（自然人）


@dataclass
class CustomerListItem:
    """客户列表项。"""

    name: str
    client_type: str  # natural=自然人 / legal=企业
    key_id: str  # 客户KeyID，用于构造详情页URL


@dataclass
class ClientListFormState:
    """客户列表表单状态。"""

    action_url: str
    payload: dict[str, str]
    total_count: int = 0
    page_size: int = 20


class JtnClientImportScript:
    """金诚同达 OA 客户导入自动化。"""

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

    def run(self, *, limit: int | None = None) -> Generator[OACustomerData, None, None]:
        """执行客户导入流程，yield 每条客户数据（HTTP主链路 + Playwright兜底）。"""
        self._emit_progress("discovery_started", message="正在登录OA并进入客户列表")

        try:
            shared_cookies = self._http_login_and_get_cookies()
            all_items = self._discover_clients_via_http(shared_cookies=shared_cookies, limit=limit)

            logger.info("HTTP 共收集到 %d 个客户", len(all_items))
            self._emit_progress(
                "discovery_completed",
                discovered_count=len(all_items),
                total_count=len(all_items),
                message=f"已发现 {len(all_items)} 条，准备开始导入",
            )

            if not all_items:
                self._emit_progress("import_collected", total_count=0, message="未发现可导入的当事人")
                return

            detail_workers = self._resolve_detail_workers(total=len(all_items))
            self._emit_progress("import_started", total_count=len(all_items), message="开始导入当事人")
            resolved_details = self._fetch_customer_details_via_http(
                items=all_items,
                shared_cookies=shared_cookies,
                workers=detail_workers,
            )

            failed_indexes = [idx for idx, data in enumerate(resolved_details) if data is None]
            if failed_indexes:
                fallback_items = [all_items[idx] for idx in failed_indexes]
                logger.info("客户详情触发 Playwright 兜底: failed=%d", len(fallback_items))
                fallback_map = self._fetch_customer_details_via_playwright_fallback(fallback_items)
                for idx in failed_indexes:
                    resolved_details[idx] = fallback_map.get(all_items[idx].key_id)

            for index, item in enumerate(all_items, start=1):
                data = resolved_details[index - 1]
                if data is None:
                    data = OACustomerData(name=item.name, client_type=item.client_type)

                logger.info("处理详情 [%d/%d]: %s", index, len(all_items), item.name)
                self._emit_progress(
                    "import_progress",
                    index=index,
                    total_count=len(all_items),
                    discovered_count=len(all_items),
                    name=item.name,
                    message=f"正在导入当事人 ({index}/{len(all_items)})",
                )
                yield data

            self._emit_progress("import_collected", total_count=len(all_items), message="当事人详情提取完成")
            logger.info("客户导入完成，共处理 %d 个客户", len(all_items))
            return
        except Exception as exc:
            logger.warning("HTTP 客户导入异常，回退 Playwright 全量流程: %s", exc, exc_info=True)
            yield from self._run_via_playwright(limit=limit)

    def _run_via_playwright(self, *, limit: int | None = None) -> Generator[OACustomerData, None, None]:
        """Playwright 全量兜底流程。"""
        pw = sync_playwright().start()
        browser = None
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
            self._navigate_to_client_list()

            all_items: list[CustomerListItem] = []
            page_index = 0
            while True:
                items = self._extract_page_customers()
                page_index += 1
                all_items.extend(items)
                logger.info("本页共 %d 个客户，已累计 %d 个", len(items), len(all_items))
                self._emit_progress(
                    "discovery_progress",
                    page=page_index,
                    page_count=len(items),
                    discovered_count=len(all_items),
                    message=f"正在查找并发现当事人（第{page_index}页）",
                )

                if limit is not None and limit > 0 and len(all_items) >= limit:
                    all_items = all_items[:limit]
                    self._emit_progress(
                        "discovery_progress",
                        page=page_index,
                        page_count=len(items),
                        discovered_count=len(all_items),
                        message=f"已达到导入上限 {limit} 条",
                    )
                    break

                if not self._click_next_page():
                    break

            logger.info("Playwright 共收集到 %d 个客户", len(all_items))
            self._emit_progress(
                "discovery_completed",
                discovered_count=len(all_items),
                total_count=len(all_items),
                message=f"已发现 {len(all_items)} 条，准备开始导入",
            )

            self._emit_progress("import_started", total_count=len(all_items), message="开始导入当事人")
            for i, item in enumerate(all_items):
                logger.info("处理详情 [%d/%d]: %s", i + 1, len(all_items), item.name)
                self._emit_progress(
                    "import_progress",
                    index=i + 1,
                    total_count=len(all_items),
                    discovered_count=len(all_items),
                    name=item.name,
                    message=f"正在导入当事人 ({i + 1}/{len(all_items)})",
                )
                data = self._fetch_customer_detail(item)
                if data:
                    yield data
                time.sleep(_SHORT_WAIT)

            self._emit_progress("import_collected", total_count=len(all_items), message="当事人详情提取完成")
            logger.info("Playwright 兜底导入完成，共处理 %d 个客户", len(all_items))
        finally:
            if browser is not None:
                browser.close()
            pw.stop()

    def _resolve_detail_workers(self, *, total: int) -> int:
        """解析客户详情并发数。"""
        if total <= 1:
            return 1
        raw = os.environ.get("OA_CLIENT_IMPORT_DETAIL_WORKERS", "6")
        try:
            configured = int(raw)
        except ValueError:
            logger.warning("OA_CLIENT_IMPORT_DETAIL_WORKERS 非法值: %s，回退为 6", raw)
            configured = 6
        return max(1, min(configured, total))

    def _http_login_and_get_cookies(self) -> dict[str, str]:
        """HTTP 登录并返回可复用 cookie。"""
        logger.info("HTTP 登录 OA: %s", _LOGIN_URL)
        with httpx.Client(headers=_HTTP_HEADERS, follow_redirects=True, timeout=15) as client:
            login_page = client.get(_LOGIN_URL)
            csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', login_page.text)
            csrf = csrf_match.group(1) if csrf_match else ""

            login_result = client.post(
                _LOGIN_URL,
                data={"CSRFToken": csrf, "userid": self._account, "password": self._password},
            )
            if "login" in str(login_result.url).lower() or "logout" in login_result.text.lower()[:200]:
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")
            cookies = dict(client.cookies.items())
        logger.info("HTTP 登录成功，获取 cookie=%d", len(cookies))
        return cookies

    def _discover_clients_via_http(
        self,
        *,
        shared_cookies: dict[str, str],
        limit: int | None = None,
    ) -> list[CustomerListItem]:
        """通过 HTTP 分页抓取客户列表。"""
        all_items: list[CustomerListItem] = []
        seen_key_ids: set[str] = set()

        with httpx.Client(
            headers=_HTTP_HEADERS,
            follow_redirects=True,
            timeout=_DEFAULT_HTTP_TIMEOUT,
            cookies=shared_cookies,
        ) as client:
            form_state = self._load_client_list_form_state(client)
            max_pages = self._resolve_total_pages(form_state.total_count, form_state.page_size)
            page_index = 1

            while True:
                page_items, form_state = self._query_client_list_page(
                    client=client,
                    form_state=form_state,
                    page_index=page_index,
                )
                for item in page_items:
                    if item.key_id in seen_key_ids:
                        continue
                    seen_key_ids.add(item.key_id)
                    all_items.append(item)

                logger.info("HTTP 客户列表第 %d 页：本页=%d，累计=%d", page_index, len(page_items), len(all_items))
                self._emit_progress(
                    "discovery_progress",
                    page=page_index,
                    page_count=len(page_items),
                    discovered_count=len(all_items),
                    message=f"正在查找并发现当事人（第{page_index}页）",
                )

                if limit is not None and limit > 0 and len(all_items) >= limit:
                    all_items = all_items[:limit]
                    self._emit_progress(
                        "discovery_progress",
                        page=page_index,
                        page_count=len(page_items),
                        discovered_count=len(all_items),
                        message=f"已达到导入上限 {limit} 条",
                    )
                    break

                if not page_items:
                    break
                if max_pages and page_index >= max_pages:
                    break
                if form_state.page_size > 0 and len(page_items) < form_state.page_size:
                    break
                page_index += 1

        return all_items

    def _resolve_total_pages(self, total_count: int, page_size: int) -> int:
        if total_count <= 0 or page_size <= 0:
            return 0
        return (total_count + page_size - 1) // page_size

    def _load_client_list_form_state(self, client: httpx.Client) -> ClientListFormState:
        response = client.get(_CLIENT_LIST_URL)
        response.raise_for_status()
        return self._extract_client_list_form_state(html_text=response.text, base_url=str(response.url))

    def _query_client_list_page(
        self,
        *,
        client: httpx.Client,
        form_state: ClientListFormState,
        page_index: int,
    ) -> tuple[list[CustomerListItem], ClientListFormState]:
        payload = dict(form_state.payload)
        payload[_LIST_CURRENT_PAGE_FIELD] = str(page_index)
        response = client.post(form_state.action_url, data=payload)
        response.raise_for_status()

        next_state = self._extract_client_list_form_state(html_text=response.text, base_url=str(response.url))
        page_items = self._extract_customer_rows_from_html(response.text)
        return page_items, next_state

    def _extract_client_list_form_state(self, *, html_text: str, base_url: str) -> ClientListFormState:
        root = lxml_html.fromstring(html_text)
        forms = root.xpath('//form[@id="aspnetForm"]')
        if not forms:
            raise RuntimeError("客户列表页缺少 aspnetForm，无法执行 HTTP 查询")
        form = forms[0]

        action_attr = form.get("action") or _CLIENT_LIST_URL
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
            payload[name] = str(option_value) if option_value is not None else ""

        for textarea_node in form.xpath(".//textarea[@name]"):
            name = str(textarea_node.get("name") or "").strip()
            if not name:
                continue
            payload[name] = self._normalize_text("".join(textarea_node.itertext()))

        rows = root.xpath('//table[@id="table"]//tr[position()>1]')
        page_size = len(rows) or 20
        total_count = self._to_int(payload.get("TotalCount"))
        return ClientListFormState(
            action_url=action_url,
            payload=payload,
            total_count=total_count,
            page_size=page_size,
        )

    def _extract_customer_rows_from_html(self, html_text: str) -> list[CustomerListItem]:
        root = lxml_html.fromstring(html_text)
        rows = root.xpath('//table[@id="table"]//tr[position()>1]')
        items: list[CustomerListItem] = []

        for row in rows:
            cells = row.xpath("./td")
            if len(cells) < 5:
                continue

            name_text = self._normalize_text("".join(cells[2].itertext()))
            type_text = self._normalize_text("".join(cells[4].itertext()))
            if not name_text or not type_text or "客户类型" in type_text:
                continue

            key_id = None
            for href in row.xpath('.//a[contains(@href, "CustomerInfor.aspx")]/@href'):
                maybe_key = self._extract_key_id_from_href(str(href))
                if maybe_key:
                    key_id = maybe_key
                    break
            if not key_id:
                continue

            client_type = "legal" if "企业" in type_text else "natural"
            items.append(CustomerListItem(name=name_text, client_type=client_type, key_id=key_id))

        return items

    def _extract_key_id_from_href(self, href: str) -> str | None:
        if not href:
            return None
        full_url = urljoin(_CLIENT_LIST_URL, href)
        query = parse_qs(urlparse(full_url).query)
        key_id = query.get("KeyID", query.get("keyid", [None]))[0]
        return str(key_id).strip() if key_id else None

    def _fetch_customer_details_via_http(
        self,
        *,
        items: list[CustomerListItem],
        shared_cookies: dict[str, str],
        workers: int,
    ) -> list[OACustomerData | None]:
        if not items:
            return []

        indexed_items = list(enumerate(items))
        if workers <= 1:
            ordered = self._fetch_customer_detail_chunk_via_http(
                indexed_chunk=indexed_items,
                shared_cookies=shared_cookies,
            )
            return [data for _, data in ordered]

        chunk_size = (len(indexed_items) + workers - 1) // workers
        chunks = [indexed_items[start : start + chunk_size] for start in range(0, len(indexed_items), chunk_size)]

        indexed_results: list[OACustomerData | None] = [None] * len(items)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="oa-client-detail-http") as executor:
            futures = [
                executor.submit(
                    self._fetch_customer_detail_chunk_via_http,
                    indexed_chunk=chunk,
                    shared_cookies=shared_cookies,
                )
                for chunk in chunks
            ]
            for future in as_completed(futures):
                for idx, data in future.result():
                    indexed_results[idx] = data

        return indexed_results

    def _fetch_customer_detail_chunk_via_http(
        self,
        *,
        indexed_chunk: list[tuple[int, CustomerListItem]],
        shared_cookies: dict[str, str],
    ) -> list[tuple[int, OACustomerData | None]]:
        results: list[tuple[int, OACustomerData | None]] = []
        with httpx.Client(
            headers=_HTTP_HEADERS,
            follow_redirects=True,
            timeout=_DEFAULT_HTTP_TIMEOUT,
            cookies=shared_cookies,
        ) as client:
            for idx, item in indexed_chunk:
                try:
                    data = self._fetch_customer_detail_via_http(client=client, item=item)
                    results.append((idx, data))
                except Exception as exc:
                    logger.warning("HTTP 提取客户详情异常 %s(%s): %s", item.name, item.key_id, exc)
                    results.append((idx, None))
        return results

    def _fetch_customer_detail_via_http(
        self,
        *,
        client: httpx.Client,
        item: CustomerListItem,
    ) -> OACustomerData:
        detail_url = (
            f"{_BASE_URL}/CustomerInfor.aspx?KeyID={item.key_id}&Category=A&FirstModel=PROJECT&SecondModel=PROJECT001"
        )
        response = client.get(detail_url)
        response.raise_for_status()
        text = self._extract_text_from_html(response.text)
        return self._parse_customer_detail_text(item.name, item.client_type, text)

    def _fetch_customer_details_via_playwright_fallback(
        self,
        items: list[CustomerListItem],
    ) -> dict[str, OACustomerData | None]:
        """对失败详情使用 Playwright 兜底（单次浏览器会话）。"""
        if not items:
            return {}

        pw = sync_playwright().start()
        browser = None
        fallback_map: dict[str, OACustomerData | None] = {}
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
            self._navigate_to_client_list()
            for item in items:
                try:
                    fallback_map[item.key_id] = self._fetch_customer_detail(item)
                except Exception as exc:
                    logger.warning("Playwright 兜底客户详情异常 %s(%s): %s", item.name, item.key_id, exc)
                    fallback_map[item.key_id] = None
        finally:
            if browser is not None:
                browser.close()
            pw.stop()
        return fallback_map

    def _extract_text_from_html(self, html_text: str) -> str:
        try:
            root = lxml_html.fromstring(html_text)
            return self._normalize_text(root.text_content())
        except Exception:
            return self._normalize_text(html_text)

    def _parse_customer_detail_text(self, customer_name: str, client_type: str, text: str) -> OACustomerData:
        """从详情页文本中解析客户字段（HTTP/Playwright 复用）。"""
        data = OACustomerData(name=customer_name, client_type=client_type)
        normalized = self._normalize_text(text)

        try:
            # 身份证号码
            m = re.search(r"身份证号码\s*[：:]\s*([A-Za-z0-9]{15,18})", normalized)
            if m:
                data.id_number = m.group(1).upper()

            # 性别
            m = re.search(r"性\s*别\s*[：:]\s*([男女])", normalized)
            if m:
                data.gender = m.group(1)

            # 联系电话
            for label in ("联系电话", "客户电话", "手机号码", "手机号"):
                val = self._extract_labeled_value(normalized, label)
                if self._is_valid_phone(val):
                    data.phone = val
                    break

            # 地址
            id_addr = self._extract_labeled_value(normalized, "身份证地址")
            if self._is_valid_field_value(id_addr):
                data.address = id_addr
            if not data.address:
                for label in ("地 址", "地址"):
                    val = self._extract_labeled_value(normalized, label)
                    if self._is_valid_field_value(val):
                        data.address = val
                        break

            # 法定代表人 / 负责人
            for label in ("法定代表人", "负责人"):
                val = self._extract_labeled_value(normalized, label)
                if self._is_valid_field_value(val):
                    data.legal_representative = val
                    break

            # 客户类型兜底确认
            if data.id_number:
                data.client_type = "natural"
            elif data.legal_representative:
                data.client_type = "legal"
            elif "自然人" in normalized:
                data.client_type = "natural"
            elif "企业" in normalized:
                data.client_type = "legal"
        except Exception as exc:
            logger.warning("解析客户详情异常 %s: %s", customer_name, exc)

        logger.info(
            "解析客户详情完成: %s, type=%s, phone=%s, address=%s, id=%s",
            data.name,
            data.client_type,
            data.phone,
            data.address,
            data.id_number,
        )
        return data

    def _extract_labeled_value(self, text: str, label: str) -> str | None:
        pattern = rf"{re.escape(label)}\s*[：:]\s*([^\n]+)"
        m = re.search(pattern, text)
        if not m:
            return None
        value = self._normalize_text(m.group(1))
        value = value.replace("，", ",").strip(" :,：")
        return value

    def _is_valid_field_value(self, value: str | None) -> bool:
        if not value:
            return False
        return value not in {"/", "-", "--", "N/A", "无", "：", ":"}

    def _is_valid_phone(self, value: str | None) -> bool:
        if not self._is_valid_field_value(value):
            return False
        digits = re.sub(r"\D", "", value or "")
        # 电话通常 7-13 位，避免将身份证号（15/18位）误识别为电话
        return 7 <= len(digits) <= 13

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "")
        text = text.replace("\r", "\n").replace("\u00a0", " ").replace("\u3000", " ")
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _to_int(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        try:
            return int(str(value).strip())
        except Exception:
            digits = re.findall(r"\d+", str(value))
            if not digits:
                return 0
            try:
                return int("".join(digits))
            except Exception:
                return 0

    def _emit_progress(self, event: str, **payload: Any) -> None:
        if self._progress_callback is None:
            return
        try:
            self._progress_callback({"event": event, **payload})
        except Exception:
            logger.debug("进度回调处理异常: event=%s", event, exc_info=True)

    def _login(self) -> None:
        """通过 httpx 接口登录，将 cookie 注入 Playwright context。"""
        logger.info("接口登录: %s", _LOGIN_URL)

        with httpx.Client(headers=_HTTP_HEADERS, follow_redirects=True, timeout=15) as client:
            # 1. GET 登录页，拿 ASP.NET_SessionId + CSRFToken
            r = client.get(_LOGIN_URL)
            csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', r.text)
            csrf = csrf_match.group(1) if csrf_match else ""

            # 2. POST 登录
            r2 = client.post(
                _LOGIN_URL,
                data={"CSRFToken": csrf, "userid": self._account, "password": self._password},
            )

            if "login" in str(r2.url).lower() or "logout" in r2.text.lower()[:200]:
                raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")

            # 3. 将 cookie 注入 Playwright context
            assert self._context is not None
            for cookie in client.cookies.jar:
                self._context.add_cookies(
                    [
                        {
                            "name": cookie.name,
                            "value": cookie.value or "",
                            "domain": cookie.domain or "ims.jtn.com",
                            "path": cookie.path or "/",
                        }
                    ]
                )

        logger.info("接口登录成功，cookie 已注入，当前重定向URL: %s", r2.url)

    def _navigate_to_client_list(self) -> None:
        """导航到客户列表页。"""
        page = self._page
        assert page is not None

        logger.info("导航到客户列表页: %s", _CLIENT_LIST_URL)
        page.goto(_CLIENT_LIST_URL, wait_until="domcontentloaded")
        time.sleep(_MEDIUM_WAIT)
        logger.info("已进入客户列表页面")

    def _extract_page_customers(self) -> list[CustomerListItem]:
        """提取当前页所有客户信息。

        Returns:
            List of CustomerListItem.
        """
        page = self._page
        assert page is not None

        customers: list[CustomerListItem] = []

        # 等待表格加载
        page.wait_for_selector("#table", timeout=15000)
        time.sleep(_AJAX_WAIT)

        # 查找表格中的客户名称单元格
        # 表格结构: table#table > tbody > tr
        # 客户名称在 td:nth-child(3)，客户类型在 td:nth-child(5)
        rows = page.locator("#table tbody tr").all()
        for row in rows:
            try:
                name_cell = row.locator("td:nth-child(3)")
                type_cell = row.locator("td:nth-child(5)")

                # 从 a 标签获取客户名称和 KeyID
                name_link = name_cell.locator("a").first
                if name_link.count() == 0:
                    continue

                name_text = name_link.inner_text().strip()
                href = name_link.get_attribute("href") or ""

                # 从 href 中提取 KeyID
                # 格式: CustomerInfor.aspx?KeyID=xxx&Category=...
                key_id = ""
                if "KeyID=" in href:
                    match = re.search(r"KeyID=([^&]+)", href)
                    if match:
                        key_id = match.group(1)

                type_text = type_cell.inner_text().strip()

                if name_text and type_text:
                    # 跳过表头行
                    if "客户类型" in type_text or "等级" in type_text or not key_id:
                        continue
                    # 判断是企业还是自然人
                    client_type = "legal" if "企业" in type_text else "natural"
                    customers.append(CustomerListItem(name=name_text, client_type=client_type, key_id=key_id))
                    logger.info("发现客户: %s (%s), KeyID: %s", name_text, client_type, key_id)
            except Exception as exc:
                logger.warning("提取客户行异常: %s", exc)
                continue

        return customers

    def _fetch_customer_detail(self, item: CustomerListItem) -> OACustomerData | None:
        """打开客户详情页，提取字段。"""
        page = self._page
        assert page is not None

        logger.info("进入客户详情: %s (KeyID: %s)", item.name, item.key_id)

        try:
            # 直接导航到详情页
            detail_url = f"{_BASE_URL}/CustomerInfor.aspx?KeyID={item.key_id}&Category=A&FirstModel=PROJECT&SecondModel=PROJECT001"
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(_MEDIUM_WAIT)

            # 提取详情页字段
            data = self._parse_customer_detail(item.name, item.client_type)
            return data

        except Exception as exc:
            logger.warning("提取客户详情异常 %s: %s", item.name, exc)
            # 返回基础数据
            return OACustomerData(
                name=item.name,
                client_type=item.client_type,
            )

    def _parse_customer_detail(self, customer_name: str, client_type: str) -> OACustomerData:
        """解析客户详情页，提取字段。"""
        page = self._page
        assert page is not None

        try:
            text = page.inner_text("body")
            return self._parse_customer_detail_text(customer_name, client_type, text)
        except Exception as exc:
            logger.warning("解析客户详情异常 %s: %s", customer_name, exc)
            return OACustomerData(name=customer_name, client_type=client_type)

    def _click_next_page(self) -> bool:
        """点击下一页按钮。

        Returns:
            True if successfully clicked and loaded next page, False if no more pages.
        """
        page = self._page
        assert page is not None

        try:
            # layui 分页组件的下一页按钮
            next_btn = page.locator(".layui-laypage-next")
            if next_btn.count() == 0:
                logger.info("未找到下一页按钮，已到最后一页")
                return False

            # 检查是否禁用（最后一页）
            is_disabled = next_btn.get_attribute("class")
            if "disabled" in (is_disabled or ""):
                logger.info("下一页按钮已禁用，已到最后一页")
                return False

            next_btn.click()
            time.sleep(_AJAX_WAIT)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(_SHORT_WAIT)
            logger.info("已点击下一页")
            return True

        except Exception as exc:
            logger.warning("点击下一页异常: %s", exc)
            return False
