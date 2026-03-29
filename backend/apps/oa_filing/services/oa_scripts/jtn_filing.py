"""金诚同达 OA 立案脚本。

独立模块，不与其他律所 OA 共享逻辑。
通过 Playwright 自动化完成：
登录 → 进入立案页 → 添加委托方 → 填写案件信息 → 利冲信息 → 合同信息。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html
from playwright.sync_api import BrowserContext, FrameLocator, Page, sync_playwright

logger = logging.getLogger("apps.oa_filing.jtn")

# ============================================================
# 常量：URL 和 XPath
# ============================================================
_LOGIN_URL = "https://ims.jtn.com/member/login.aspx"
_FILING_URL = "https://ims.jtn.com/projflw/ProjectAppRegNew.aspx?t=1&&FirstModel=PROJECT&SecondModel=PROJECT003"
_PROJECT_HANDLER_BASE = "https://ims.jtn.com/Handle/ProjectAppHandler.ashx"
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_DEFAULT_HTTP_TIMEOUT = 20

# 立案页
_XPATH_ADD_CLIENT_BTN = '//*[@id="wrap"]/div[1]/div[2]/div/div[5]/div/div[1]/div[2]/a'

# 委托方弹窗 iframe（动态 ID，每次打开递增）
# 不再使用固定 xpath，改用 _find_latest_client_iframe() 动态定位

# iframe 内 - 客户类型切换
_XPATH_PERSONAL_TAB = '//*[@id="form1"]/div[3]/div/div[1]'

# iframe 内 - 搜索
_XPATH_NAME_INPUT = '//*[@id="form1"]/div[4]/div[1]/div/input'
_XPATH_ID_INPUT = '//*[@id="form1"]/div[4]/div[2]/div/input'
_XPATH_SEARCH_BTN = '//*[@id="form1"]/div[4]/a[1]'

# iframe 内 - 选择客户
_XPATH_RESULT_CHECKBOX = '//*[@id="form1"]/div[5]/div[2]/div[2]/table/tbody/tr/td[1]/div'
_XPATH_CONFIRM_BTN = '//*[@id="form1"]/div[5]/div[1]/div[1]/div/a[1]'

# iframe 内 - 创建新客户
_XPATH_CREATE_NEW_BTN = '//*[@id="form1"]/div[5]/div[1]/div[1]/div/a[2]'

# 客户类型 select 值映射（Chosen.js 组件，需通过 JS 操作）
_CUSTOMER_TYPE_MAP: dict[str, str] = {
    "natural": "11",  # 自然人
    "legal": "01",  # 企业（法人）
    "non_legal_org": "01",  # 企业（非法人组织也选企业）
}

# 客户类型细分映射
_CUSTOMER_TYPE_SUB_MAP: dict[str, str] = {
    "natural": "11-01",  # 境内自然人
    "legal": "01-08",  # 其他企业
    "non_legal_org": "01-08",
}

# 等待时间（秒）
_SHORT_WAIT = 1.0
_MEDIUM_WAIT = 2.0
_AJAX_WAIT = 2.5


def _gender_from_id_number(id_number: str) -> str:
    """从身份证号码推断性别。

    18位身份证第17位：奇数=男，偶数=女。

    Returns:
        "01" 男 / "02" 女，无法判断时返回 "01"。
    """
    if len(id_number) == 18 and id_number[:17].isdigit():
        return "01" if int(id_number[16]) % 2 == 1 else "02"
    return "01"


@dataclass
class ClientInfo:
    """委托方信息。"""

    name: str
    client_type: str  # natural / legal / non_legal_org
    id_number: str | None = None
    address: str | None = None
    phone: str | None = None
    legal_representative: str | None = None


@dataclass
class ConflictPartyInfo:
    """利益冲突方信息。"""

    name: str
    category: str = "11"  # 11=对方当事人
    legal_position: str = "02"  # 01=原告 02=被告 09=第三人（对方诉讼地位）
    customer_type: str = "01"  # 01=企业 11=自然人
    is_payer: str = "0"  # 0=否 1=是
    id_number: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None


@dataclass
class CaseInfo:
    """案件信息。"""

    manager_id: str  # 案件负责人 empid（可为空）
    manager_name: str  # 案件负责人姓名（按名字匹配 option）
    category: str  # 案件类型: 01~06
    stage: str  # 案件阶段: 0301 等
    which_side: str  # 代理何方: 01=原告 02=被告
    kindtype: str  # 业务类型一级
    kindtype_sed: str  # 业务类型二级
    kindtype_thr: str  # 业务类型三级
    case_name: str  # 案件名称（填合同名称）
    case_desc: str = ""  # 案情简介（填合同名称）
    resource: str = "01"  # 案源: 01=主动开拓
    language: str = "01"  # 语言: 01=中文
    is_foreign: str = "N"
    is_help: str = "N"
    is_publicgood: str = "0"
    is_factory: str = "N"
    is_secret: str = "N"
    isunion: str = "0"
    isforeigncoop: str = "0"
    start_date: str = ""  # 收案日期 yyyy-MM-dd（必填，空则取当天）
    contact_name: str = "/"  # 客户联系人姓名
    contact_phone: str = "/"  # 客户联系人电话


@dataclass
class ContractInfo:
    """委托合同信息。"""

    rec_type: str = "01"  # 收费方式: 01=定额 02=按标的比例 03=按小时
    currency: str = "RMB"
    contract_type: str = "30"  # 30=书面合同
    is_free: str = "N"
    start_date: str = ""
    end_date: str = ""
    amount: str = ""
    stamp_count: int = 3  # 预盖章份数，默认 3（1人+2）


@dataclass
class FilingFormState:
    """立案表单状态。"""

    action_url: str
    payload: dict[str, str]
    html_text: str


@dataclass
class ResolvedCustomer:
    """已匹配的 OA 客户。"""

    customer_id: str
    customer_name: str
    istemp: str = "Z"


class JtnFilingScript:
    """金诚同达 OA 立案自动化。"""

    def __init__(self, account: str, password: str) -> None:
        self._account = account
        self._password = password
        self._page: Page | None = None
        self._context: BrowserContext | None = None

    def run(
        self,
        clients: list[ClientInfo],
        case_info: CaseInfo | None = None,
        conflict_parties: list[ConflictPartyInfo] | None = None,
        contract_info: ContractInfo | None = None,
    ) -> None:
        """执行完整立案流程（HTTP 主链路 + Playwright 兜底）。"""
        try:
            self._run_via_http(
                clients=clients,
                case_info=case_info,
                conflict_parties=conflict_parties,
                contract_info=contract_info,
            )
            logger.info("HTTP 立案流程完成")
            return
        except Exception as exc:
            logger.warning("HTTP 立案失败，回退 Playwright: %s", exc, exc_info=True)

        self._run_via_playwright(
            clients=clients,
            case_info=case_info,
            conflict_parties=conflict_parties,
            contract_info=contract_info,
        )

    def _run_via_playwright(
        self,
        *,
        clients: list[ClientInfo],
        case_info: CaseInfo | None,
        conflict_parties: list[ConflictPartyInfo] | None,
        contract_info: ContractInfo | None,
    ) -> None:
        """Playwright 全量兜底流程。"""
        pw = sync_playwright().start()
        browser = None
        try:
            browser = pw.chromium.launch(headless=False)
            self._context = browser.new_context()
            
            # 应用 playwright-stealth 反检测
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(self._context)
                logger.info("已应用 playwright-stealth 反检测")
            except ImportError:
                logger.warning("playwright-stealth 未安装，跳过反检测")
            
            self._context.set_default_timeout(30_000)
            self._context.set_default_navigation_timeout(30_000)
            self._page = self._context.new_page()

            self._login()
            self._navigate_to_filing()

            # ── Tab 0: 客户信息 ──
            for i, client in enumerate(clients):
                self._add_client(client)
                if i < len(clients) - 1:
                    time.sleep(_MEDIUM_WAIT)

            # ── Tab 1: 案件信息 ──
            if case_info is not None:
                self._click_next_tab()
                self._fill_case_info(case_info)

            # ── Tab 2: 利益冲突信息 ──
            if conflict_parties is not None:
                self._click_next_tab()
                self._fill_conflict_info(conflict_parties)

            # ── Tab 3: 承办律师信息（跳过） ──
            self._click_next_tab()

            # ── Tab 4: 委托合同信息 ──
            if contract_info is not None:
                self._click_next_tab()
                self._fill_contract_info(contract_info)

            # ── 存草稿 ──
            self._save_draft()
            logger.info("Playwright 立案流程完成")
        finally:
            if browser is not None:
                browser.close()
            pw.stop()
            logger.info("Playwright 浏览器已关闭")

    def _run_via_http(
        self,
        *,
        clients: list[ClientInfo],
        case_info: CaseInfo | None,
        conflict_parties: list[ConflictPartyInfo] | None,
        contract_info: ContractInfo | None,
    ) -> None:
        """HTTP 主链路：直接提交立案草稿。"""
        if not clients:
            raise RuntimeError("HTTP 立案缺少委托方")

        with httpx.Client(headers=_HTTP_HEADERS, follow_redirects=True, timeout=_DEFAULT_HTTP_TIMEOUT) as client:
            self._http_login(client)
            form_state = self._load_filing_form_state(client)
            payload = dict(form_state.payload)

            resolved_customers = self._resolve_customers_via_http(client=client, clients=clients)
            self._apply_client_payload(payload=payload, customers=resolved_customers)

            if case_info is not None:
                self._apply_case_info_payload(payload=payload, case_info=case_info, form_state=form_state)
            if conflict_parties is not None:
                self._apply_conflict_payload(payload=payload, parties=conflict_parties)
            if contract_info is not None:
                self._apply_contract_payload(payload=payload, contract_info=contract_info)

            self._submit_filing_form_http(client=client, action_url=form_state.action_url, payload=payload)

    def _http_login(self, client: httpx.Client) -> None:
        """HTTP 登录（复用同一个 client 会话）。"""
        logger.info("HTTP 登录 OA: %s", _LOGIN_URL)
        login_page = client.get(_LOGIN_URL)
        login_page.raise_for_status()

        csrf_match = re.search(r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', login_page.text)
        csrf = csrf_match.group(1) if csrf_match else ""

        login_result = client.post(
            _LOGIN_URL,
            data={"CSRFToken": csrf, "userid": self._account, "password": self._password},
        )
        login_result.raise_for_status()
        if "login" in str(login_result.url).lower() or "logout" in login_result.text.lower()[:200]:
            raise RuntimeError(f"OA 登录失败，账号或密码错误: {self._account}")
        logger.info("HTTP 登录成功")

    def _load_filing_form_state(self, client: httpx.Client) -> FilingFormState:
        response = client.get(_FILING_URL)
        response.raise_for_status()
        return self._extract_filing_form_state(html_text=response.text, base_url=str(response.url))

    def _extract_filing_form_state(self, *, html_text: str, base_url: str) -> FilingFormState:
        root = lxml_html.fromstring(html_text)
        forms = root.xpath('//form[@id="aspnetForm"]')
        if not forms:
            raise RuntimeError("立案页面缺少 aspnetForm，无法执行 HTTP 立案")
        form = forms[0]

        action_attr = form.get("action") or _FILING_URL
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
            else:
                option_value = option.get("value")
                payload[name] = str(option_value) if option_value is not None else ""

        for textarea_node in form.xpath(".//textarea[@name]"):
            name = str(textarea_node.get("name") or "").strip()
            if not name:
                continue
            payload[name] = self._normalize_text("".join(textarea_node.itertext()))

        return FilingFormState(action_url=action_url, payload=payload, html_text=html_text)

    def _resolve_customers_via_http(self, *, client: httpx.Client, clients: list[ClientInfo]) -> list[ResolvedCustomer]:
        resolved: list[ResolvedCustomer] = []
        for client_info in clients:
            customer = self._search_customer_http(client=client, client_info=client_info)
            if customer is None:
                raise RuntimeError(f"HTTP 未找到 OA 客户，需回退 Playwright 创建: {client_info.name}")
            resolved.append(customer)
        return resolved

    def _search_customer_http(self, *, client: httpx.Client, client_info: ClientInfo) -> ResolvedCustomer | None:
        customer_type = "B" if client_info.client_type == "natural" else "A"
        response = client.post(
            self._handler_url("CustSeachGetList"),
            data={
                "customerType": customer_type,
                "cusName": client_info.name,
                "cusidentity": client_info.id_number or "",
            },
        )
        response.raise_for_status()
        payload = self._parse_json_object(response.text)
        rows = payload.get("data") if isinstance(payload, dict) else []
        if not isinstance(rows, list) or not rows:
            return None

        exact_name = self._normalize_text(client_info.name)
        candidates = [row for row in rows if self._normalize_text(str(row.get("customer_name") or "")) == exact_name]
        if not candidates:
            candidates = rows

        if client_info.client_type == "natural" and client_info.id_number:
            exact_id = self._normalize_text(client_info.id_number).upper()
            for row in candidates:
                card = self._normalize_text(str(row.get("customer_personcard") or "")).upper()
                if card and card == exact_id:
                    return ResolvedCustomer(
                        customer_id=str(row.get("customer_id") or "").strip(),
                        customer_name=str(row.get("customer_name") or "").strip(),
                    )

        first = candidates[0]
        customer_id = str(first.get("customer_id") or "").strip()
        customer_name = str(first.get("customer_name") or "").strip()
        if not customer_id or not customer_name:
            return None
        return ResolvedCustomer(customer_id=customer_id, customer_name=customer_name)

    def _apply_client_payload(self, *, payload: dict[str, str], customers: list[ResolvedCustomer]) -> None:
        if not customers:
            return
        for customer in customers:
            gid = uuid.uuid4().hex
            payload[f"pro_customer_istemp_{gid}"] = customer.istemp
            payload[f"pro_customer_id_{gid}"] = customer.customer_id
            payload[f"pro_customer_name_{gid}"] = customer.customer_name

        payload["project_cus_id"] = customers[0].customer_id
        payload["project_cus_name"] = customers[0].customer_name

    def _apply_case_info_payload(
        self,
        *,
        payload: dict[str, str],
        case_info: CaseInfo,
        form_state: FilingFormState,
    ) -> None:
        manager_field = self._project_field_name("manager_id")
        if case_info.manager_id:
            payload[manager_field] = case_info.manager_id
        elif case_info.manager_name:
            manager_value = self._resolve_manager_id_from_form(
                html_text=form_state.html_text,
                manager_name=case_info.manager_name,
            )
            if manager_value:
                payload[manager_field] = manager_value

        payload[self._project_field_name("category_id")] = case_info.category
        if case_info.stage:
            payload[self._project_field_name("stage_id")] = case_info.stage
            payload[self._project_field_name("which_side")] = case_info.which_side

        if case_info.kindtype:
            payload[self._project_field_name("kindtype_id")] = case_info.kindtype
        if case_info.kindtype_sed:
            payload[self._project_field_name("kindtypeSed_id")] = case_info.kindtype_sed
        payload[self._project_field_name("kindtypeThr_id")] = case_info.kindtype_thr or ""

        payload[self._project_field_name("resource_id")] = case_info.resource
        payload[self._project_field_name("language_id")] = case_info.language
        payload[self._project_field_name("is_foreign")] = case_info.is_foreign
        payload[self._project_field_name("is_help")] = case_info.is_help
        payload[self._project_field_name("is_publicgood")] = case_info.is_publicgood
        payload[self._project_field_name("is_factory")] = case_info.is_factory
        payload[self._project_field_name("is_secret")] = case_info.is_secret
        payload[self._project_field_name("is_emergency")] = "1"
        payload[self._project_field_name("urgentmemo")] = "着急将合同盖章拿给客户付款"
        payload[self._project_field_name("isunion")] = case_info.isunion
        payload[self._project_field_name("isforeigncoop")] = case_info.isforeigncoop

        payload[self._project_field_name("name")] = case_info.case_name
        payload[self._project_field_name("desc")] = case_info.case_desc

        from datetime import date as _date

        payload[self._project_field_name("date")] = case_info.start_date or _date.today().isoformat()

        for field_name in list(payload.keys()):
            if "pro_pl_name" in field_name:
                payload[field_name] = case_info.contact_name or "/"
            elif "pro_pl_phone" in field_name:
                payload[field_name] = case_info.contact_phone or "/"

    def _apply_conflict_payload(self, *, payload: dict[str, str], parties: list[ConflictPartyInfo]) -> None:
        for party in parties:
            gid = uuid.uuid4().hex
            payload[f"pro_pci_type_{gid}"] = party.category
            payload[f"pro_pci_relation_{gid}"] = party.legal_position
            payload[f"pro_pci_customertype_{gid}"] = party.customer_type
            payload[f"pro_pci_payment_{gid}"] = party.is_payer
            payload[f"pro_pci_name_{gid}"] = party.name
            payload[f"pro_pci_enname_{gid}"] = ""
            payload[f"pro_pci_linker_{gid}"] = party.contact_name or ""
            payload[f"pro_pci_no_{gid}"] = party.id_number or ""
            payload[f"pro_pci_phone_{gid}"] = party.contact_phone or ""

    def _apply_contract_payload(self, *, payload: dict[str, str], contract_info: ContractInfo) -> None:
        payload[self._project_field_name("rec_type")] = contract_info.rec_type
        payload[self._project_field_name("currency")] = contract_info.currency
        payload[self._project_field_name("contract_type")] = contract_info.contract_type
        payload[self._project_field_name("IsFree")] = contract_info.is_free
        payload[self._project_field_name("stamp_count")] = str(contract_info.stamp_count)

        if contract_info.start_date:
            payload[self._project_field_name("start_date")] = contract_info.start_date
        if contract_info.end_date:
            payload[self._project_field_name("end_date")] = contract_info.end_date
        if contract_info.amount:
            payload[self._project_field_name("amount")] = contract_info.amount

    def _submit_filing_form_http(self, *, client: httpx.Client, action_url: str, payload: dict[str, str]) -> None:
        save_button_name = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$btnSave"
        payload[save_button_name] = "　存草稿　"

        response = client.post(action_url, data=payload)
        response.raise_for_status()
        self._assert_http_submit_success(response.text)

    def _assert_http_submit_success(self, response_text: str) -> None:
        if "案件保存未提交" in response_text or "保存并提交成功" in response_text:
            return

        alert_match = re.search(r"alert\\('([^']*)'\\)", response_text)
        if alert_match:
            message = alert_match.group(1).strip()
            raise RuntimeError(f"HTTP 立案失败: {message}")

        raise RuntimeError("HTTP 立案失败：未检测到成功标记")

    def _resolve_manager_id_from_form(self, *, html_text: str, manager_name: str) -> str | None:
        root = lxml_html.fromstring(html_text)
        manager_field = self._project_field_name("manager_id")
        options = root.xpath(f'//select[@name="{manager_field}"]/option')
        target_name = self._normalize_text(manager_name)
        if not target_name:
            return None
        for option in options:
            text = self._normalize_text("".join(option.itertext()))
            if text == target_name:
                value = option.get("value")
                return str(value).strip() if value else None
        return None

    @staticmethod
    def _project_field_name(field: str) -> str:
        return f"ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_{field}"

    @staticmethod
    def _handler_url(method: str) -> str:
        return f"{_PROJECT_HANDLER_BASE}/{method}"

    @staticmethod
    def _parse_json_object(response_text: str) -> dict[str, Any]:
        text = response_text.strip().lstrip("\ufeff")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise RuntimeError("OA 接口返回格式异常")
        return data

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "")
        text = text.replace("\r", "\n").replace("\u00a0", " ").replace("\u3000", " ")
        text = re.sub(r"[ \t\f\v]+", " ", text)
        return text.strip()

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

    def _navigate_to_filing(self) -> None:
        """导航到立案页面。"""
        page = self._page
        assert page is not None

        logger.info("导航到立案页: %s", _FILING_URL)
        page.goto(_FILING_URL, wait_until="domcontentloaded")
        time.sleep(_MEDIUM_WAIT)
        logger.info("已进入立案页面")

    def _add_client(self, client: ClientInfo) -> None:
        """添加一个委托方。"""
        page = self._page
        assert page is not None

        logger.info("添加委托方: %s (%s)", client.name, client.client_type)

        page.locator(f"xpath={_XPATH_ADD_CLIENT_BTN}").click()
        time.sleep(_MEDIUM_WAIT)

        iframe_xpath: str = self._find_latest_client_iframe(page)
        iframe: FrameLocator = page.frame_locator(f"xpath={iframe_xpath}")

        is_natural: bool = client.client_type == "natural"

        if is_natural:
            iframe.locator(f"xpath={_XPATH_PERSONAL_TAB}").click()
            time.sleep(_SHORT_WAIT)

        iframe.locator(f"xpath={_XPATH_NAME_INPUT}").fill(client.name)

        iframe.locator(f"xpath={_XPATH_SEARCH_BTN}").click()
        time.sleep(_AJAX_WAIT)

        found = self._try_select_client(page, iframe)

        if not found:
            logger.info("未找到客户 %s，进入创建流程", client.name)
            self._create_new_client(iframe, client)

    def _try_select_client(self, page: Page, iframe: FrameLocator) -> bool:
        """尝试在搜索结果中选中第一个客户并确认。

        layui table radio 选中需通过内部缓存 LAY_CHECKED 标志，
        然后直接调用 parent.projectAppReg.loadCustomer 并关闭弹窗。
        """
        try:
            # 检查客户名称列（第4列，index=3）是否有实际内容
            name_cells = iframe.locator('xpath=//*[@id="form1"]/div[5]/div[2]/div[2]/table/tbody/tr/td[4]/div')
            if name_cells.count() == 0:
                return False
            first_name = name_cells.first.inner_text().strip()
            if not first_name:
                return False

            # 通过 JS 设置 layui table 内部缓存的选中状态，然后调用确认逻辑
            iframe_id = self._get_latest_iframe_id(page)
            page.evaluate(
                """(iframeId) => {
                const iframe = document.getElementById(iframeId);
                if (!iframe) return;
                const layui = iframe.contentWindow.layui;
                const cache = layui.table.cache['custable'];
                if (!cache || cache.length === 0) return;
                cache[0]['LAY_CHECKED'] = true;
                const data = [cache[0]];
                data[0]['istemp'] = 'Z';
                iframe.contentWindow.parent.projectAppReg.loadCustomer(data);
                const index = iframe.contentWindow.parent.layer.getFrameIndex(iframe.contentWindow.name);
                iframe.contentWindow.parent.layer.close(index);
            }""",
                iframe_id,
            )
            time.sleep(_MEDIUM_WAIT)
            logger.info("已选中已有客户: %s", first_name)
            return True
        except Exception as exc:
            logger.info("搜索结果检查异常: %s", exc)
        return False

    def _get_latest_iframe_id(self, page: Page) -> str:
        """获取当前最新弹窗 iframe 的 id。"""
        return (
            page.evaluate(
                """() => {
            const iframes = document.querySelectorAll('iframe[id^="layui-layer-iframe"]');
            let maxId = '', maxNum = -1;
            for (const f of iframes) {
                const num = parseInt(f.id.replace('layui-layer-iframe', ''), 10);
                if (num > maxNum) { maxNum = num; maxId = f.id; }
            }
            return maxId;
        }"""
            )
            or "layui-layer-iframe100002"
        )

    def _create_new_client(
        self,
        iframe: FrameLocator,
        client: ClientInfo,
    ) -> None:
        """点击创建新客户，进入二级 iframe 并填充所有必填字段。

        二级 iframe 的 id 是动态生成的（layui-layer-iframeXXXXX），
        通过 src 匹配 CreateCustomer.aspx 来定位。
        所有 Chosen.js 下拉框统一通过 jQuery 操作。
        """
        iframe.locator(f"xpath={_XPATH_CREATE_NEW_BTN}").click()
        time.sleep(_MEDIUM_WAIT)

        assert self._page is not None
        page = self._page

        type_value: str = _CUSTOMER_TYPE_MAP.get(client.client_type, "01")
        is_natural: bool = client.client_type == "natural"

        # ── 1. 选择客户类型（触发 change 事件加载客户类型细分） ──
        self._eval_create_iframe(
            page,
            """(typeValue) => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#customer_Type', doc).val(typeValue);
            $('#customer_Type', doc).trigger('chosen:updated');
            $('#customer_Type', doc).trigger('change');
        }""",
            type_value,
        )
        time.sleep(_AJAX_WAIT)

        # ── 2. 客户类型细分 ──
        type_sub: str = _CUSTOMER_TYPE_SUB_MAP.get(client.client_type, "01-08")
        self._set_chosen(page, "customer_Type_zj", type_sub)

        # ── 3. 基本信息 ──
        self._set_input(page, "customer_name", client.name)
        self._set_input(page, "customer_Address", client.address or "/")
        self._set_input(page, "customer_callNo", client.phone or "/")

        # ── 4. 固定默认值下拉框 ──
        self._set_chosen(page, "customer_country", "01")  # 中国
        self._set_chosen(page, "customer_Source", "01")  # 主动开拓获得客户

        if is_natural:
            self._fill_natural_person(page, client)
        else:
            self._fill_enterprise(page, client)

        # ── 5. 点击确定提交（使用原生 click 确保事件冒泡到委托处理器） ──
        self._eval_create_iframe(
            page,
            """() => {
            const doc = iframe.contentDocument;
            const btn = doc.getElementById('btnSaveCustomer');
            if (btn) btn.click();
        }""",
        )
        time.sleep(_MEDIUM_WAIT)
        logger.info("已提交创建客户: %s (%s)", client.name, client.client_type)

    def _fill_enterprise(self, page: Page, client: ClientInfo) -> None:
        """填充企业类型特有的必填字段。"""
        self._set_chosen(page, "customer_is_IPO", "0")  # 否
        self._set_chosen(page, "customer_is_FiveQ", "0")  # 否
        self._set_chosen(page, "customer_is_ChinaTopFiveH", "0")  # 否

        # 行业 - 随便选"批发和零售业"，触发 change 加载行业细分
        self._eval_create_iframe(
            page,
            """() => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#customer_hangye', doc).val('06');
            $('#customer_hangye', doc).trigger('chosen:updated');
            $('#customer_hangye', doc).trigger('change');
        }""",
        )
        time.sleep(_AJAX_WAIT)

        # 行业细分 - 选第一个非空选项
        self._eval_create_iframe(
            page,
            """() => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            const opts = $('#customer_hangye_zj option', doc);
            if (opts.length > 1) {
                $('#customer_hangye_zj', doc).val(opts.eq(1).val());
                $('#customer_hangye_zj', doc).trigger('chosen:updated');
            }
        }""",
        )

        # 法定代表人信息
        self._set_chosen(page, "customer_Statutory", "01")  # 法定代表人
        self._set_chosen(page, "customer_Statutory_Positions", "01")  # 董事长
        self._set_input(
            page,
            "customer_Statutory_name",
            client.legal_representative or "/",
        )
        self._set_input(page, "customer_Statutory_tel", "/")

    def _fill_natural_person(self, page: Page, client: ClientInfo) -> None:
        """填充自然人类型特有的必填字段。"""
        id_number: str = client.id_number or ""

        gender: str = _gender_from_id_number(id_number)
        self._set_chosen(page, "customer_PersonSex", gender)

        self._set_input(page, "customer_PersonCard", id_number)
        # 出生日期由 OA 页面的 getBirth 事件自动从身份证号提取，
        # 但需要触发 blur 事件
        self._eval_create_iframe(
            page,
            """() => {
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#customer_PersonCard', doc).trigger('blur');
        }""",
        )
        time.sleep(_SHORT_WAIT)

        # 如果出生日期仍为空，手动从身份证号提取
        self._eval_create_iframe(
            page,
            f"""() => {{
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            if (!$('#customer_PersonBirth', doc).val()) {{
                const id = '{id_number}';
                if (id.length === 18) {{
                    const y = id.substring(6, 10);
                    const m = id.substring(10, 12);
                    const d = id.substring(12, 14);
                    $('#customer_PersonBirth', doc).val(y + '-' + m + '-' + d);
                }}
            }}
        }}""",
        )

        # 身份证地址 = 客户地址
        self._set_input(
            page,
            "customer_PersonAddress",
            client.address or "/",
        )

    # ============================================================
    # Tab 1: 案件信息
    # ============================================================

    def _fill_case_info(self, info: CaseInfo) -> None:
        """填写案件信息标签。

        级联顺序: manager → category → stage → which_side
                  category → kindtype → kindtypeSed → kindtypeThr
        """
        page = self._page
        assert page is not None
        _p = "ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_"

        logger.info("填写案件信息: %s", info.case_name)

        # 案件负责人（触发 category 加载）
        # 优先按 empid 匹配，匹配不到按名字匹配
        if info.manager_id:
            self._set_select(page, f"{_p}manager_id", info.manager_id)
        else:
            page.evaluate(
                f"""(name) => {{
                const sel = document.getElementById('{_p}manager_id');
                if (!sel) return;
                for (let i = 0; i < sel.options.length; i++) {{
                    if (sel.options[i].text.trim() === name) {{
                        sel.value = sel.options[i].value;
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                        break;
                    }}
                }}
            }}""",
                info.manager_name,
            )
        time.sleep(_AJAX_WAIT)

        # 案件类型（触发 stage + kindtype 加载）
        self._set_select(page, f"{_p}category_id", info.category)
        time.sleep(_AJAX_WAIT)

        # 案件阶段（触发 which_side 加载）— 非诉类型无阶段
        if info.stage:
            self._set_select(page, f"{_p}stage_id", info.stage)
            time.sleep(_AJAX_WAIT)

        # 代理何方 — 非诉类型无此字段
        if info.stage:
            self._set_select(page, f"{_p}which_side", info.which_side)

        # 业务类型三级级联
        if info.kindtype:
            self._set_select(page, f"{_p}kindtype_id", info.kindtype)
            time.sleep(_AJAX_WAIT)
        if info.kindtype_sed:
            self._set_select(page, f"{_p}kindtypeSed_id", info.kindtype_sed)
            time.sleep(_AJAX_WAIT)
        if info.kindtype_thr:
            self._set_select(page, f"{_p}kindtypeThr_id", info.kindtype_thr)

        # 简单下拉框
        self._set_select(page, f"{_p}resource_id", info.resource)
        self._set_select(page, f"{_p}language_id", info.language)
        self._set_select(page, f"{_p}is_foreign", info.is_foreign)
        self._set_select(page, f"{_p}is_help", info.is_help)
        self._set_select(page, f"{_p}is_publicgood", info.is_publicgood)
        self._set_select(page, f"{_p}is_factory", info.is_factory)
        self._set_select(page, f"{_p}is_secret", info.is_secret)
        # 是否加急 → 是，并填写原因
        self._set_select(page, f"{_p}is_emergency", "1")
        time.sleep(_SHORT_WAIT)
        self._set_field(page, f"{_p}urgentmemo", "着急将合同盖章拿给客户付款")
        self._set_select(page, f"{_p}isunion", info.isunion)
        self._set_select(page, f"{_p}isforeigncoop", info.isforeigncoop)

        # 文本字段
        self._set_field(page, f"{_p}name", info.case_name)
        self._set_field(page, f"{_p}desc", info.case_desc)

        # 收案日期（必填，空则取当天）
        start_date: str = info.start_date
        if not start_date:
            from datetime import date as _date

            start_date = _date.today().isoformat()
        self._set_field(page, f"{_p}start_date", start_date)

        # 客户联系人（name 带动态 GUID，用 name 属性前缀匹配）
        if info.contact_name:
            page.evaluate(
                f"""() => {{
                var el = document.querySelector('input[name*="pro_pl_name"]');
                if (el) el.value = {self._js_str(info.contact_name)};
            }}"""
            )
        if info.contact_phone:
            page.evaluate(
                f"""() => {{
                var el = document.querySelector('input[name*="pro_pl_phone"]');
                if (el) el.value = {self._js_str(info.contact_phone)};
            }}"""
            )

        logger.info("案件信息填写完成")

    # ============================================================
    # Tab 2: 利益冲突信息
    # ============================================================

    def _fill_conflict_info(self, parties: list[ConflictPartyInfo]) -> None:
        """填写利益冲突信息标签。

        页面默认有一条空记录，字段名带动态 GUID 后缀。
        通过 name 属性前缀匹配来定位字段。
        """
        page = self._page
        assert page is not None

        if not parties:
            return

        logger.info("填写利冲信息: %d 条", len(parties))

        for idx, party in enumerate(parties):
            if idx > 0:
                # 点击"添加"按钮新增一条
                page.click('a.legal_btn[data-type="addConfict"]')
                time.sleep(_MEDIUM_WAIT)

            # 获取第 idx 个利冲条目的 GUID
            guid: str = (
                page.evaluate(
                    f"""() => {{
                var tables = document.querySelectorAll(
                    '#divConfict table[id^="table_confilct_"]'
                );
                var t = tables[{idx}];
                if (!t) return '';
                return t.id.replace('table_confilct_', '');
            }}"""
                )
                or ""
            )

            if not guid:
                logger.info("未找到第 %d 条利冲条目", idx + 1)
                continue

            # 下拉框
            self._set_field_by_name(page, f"pro_pci_type_{guid}", party.category)
            self._set_field_by_name(page, f"pro_pci_relation_{guid}", party.legal_position)
            self._set_field_by_name(page, f"pro_pci_customertype_{guid}", party.customer_type)
            self._set_field_by_name(page, f"pro_pci_payment_{guid}", party.is_payer)

            # 文本
            self._set_field_by_name(page, f"pro_pci_name_{guid}", party.name)
            if party.id_number:
                self._set_field_by_name(page, f"pro_pci_no_{guid}", party.id_number)
            if party.contact_name:
                self._set_field_by_name(page, f"pro_pci_linker_{guid}", party.contact_name)
            if party.contact_phone:
                self._set_field_by_name(page, f"pro_pci_phone_{guid}", party.contact_phone)

        logger.info("利冲信息填写完成")

    # ============================================================
    # Tab 4: 委托合同信息
    # ============================================================

    def _fill_contract_info(self, info: ContractInfo) -> None:
        """填写委托合同信息标签。"""
        page = self._page
        assert page is not None
        _p = "ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_"

        logger.info("填写合同信息")

        self._set_select(page, f"{_p}rec_type", info.rec_type)
        self._set_select(page, f"{_p}currency", info.currency)
        self._set_select(page, f"{_p}contract_type", info.contract_type)
        self._set_select(page, f"{_p}IsFree", info.is_free)

        if info.start_date:
            self._set_field(page, f"{_p}start_date", info.start_date)
        if info.end_date:
            self._set_field(page, f"{_p}end_date", info.end_date)
        if info.amount:
            self._set_field(page, f"{_p}amount", info.amount)

        self._set_field(page, f"{_p}stamp_count", str(info.stamp_count))

        logger.info("合同信息填写完成")

    def _save_draft(self) -> None:
        """点击存草稿按钮。

        OA 的 ``projectAppReg.frmOk('0')`` 会弹出 ``confirm`` 对话框，
        需要覆盖 ``window.confirm`` 使其自动返回 ``true``。
        """
        page = self._page
        assert page is not None

        logger.info("点击存草稿")

        # 覆盖 confirm，自动返回 true
        page.evaluate("window.confirm = () => true")

        page.click("#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_btnSave")
        time.sleep(_MEDIUM_WAIT)

        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        logger.info("存草稿完成，当前URL: %s", page.url)

    # ============================================================
    # Helper 方法
    # ============================================================

    def _click_next_tab(self) -> None:
        """点击"下一步"切换到下一个标签页。"""
        page = self._page
        assert page is not None
        page.click('a.legal_btn[data-type="tabNext"]')
        time.sleep(_MEDIUM_WAIT)

    def _find_latest_client_iframe(self, page: Page) -> str:
        """动态查找最新的 layui-layer-iframe。

        每次打开搜索弹窗，iframe ID 会递增（100002, 100003, ...）。
        取 ID 最大的那个即为当前弹窗。
        """
        iframe_id: str = (
            page.evaluate(
                """() => {
            const iframes = document.querySelectorAll('iframe[id^="layui-layer-iframe"]');
            if (iframes.length === 0) return '';
            let maxId = '';
            let maxNum = -1;
            for (const f of iframes) {
                const num = parseInt(f.id.replace('layui-layer-iframe', ''), 10);
                if (num > maxNum) {
                    maxNum = num;
                    maxId = f.id;
                }
            }
            return maxId;
        }"""
            )
            or ""
        )
        if not iframe_id:
            logger.warning("未找到 layui-layer-iframe，回退到默认 ID")
            iframe_id = "layui-layer-iframe100002"
        logger.info("使用 iframe: %s", iframe_id)
        return f'//*[@id="{iframe_id}"]'

    def _set_select(self, page: Page, element_id: str, value: str) -> None:
        """设置主页面 select 的值并触发 change 事件（非 Chosen.js）。"""
        page.evaluate(
            f"""(val) => {{
            var el = document.getElementById('{element_id}');
            if (el) {{
                el.value = val;
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
        }}""",
            value,
        )

    def _set_field(self, page: Page, element_id: str, value: str) -> None:
        """通过 id 设置 input/textarea 的值。"""
        page.evaluate(
            f"""(val) => {{
            var el = document.getElementById('{element_id}');
            if (el) el.value = val;
        }}""",
            value,
        )

    def _set_field_by_name(self, page: Page, name: str, value: str) -> None:
        """通过 name 属性设置 select/input 的值。"""
        page.evaluate(
            f"""(val) => {{
            var el = document.querySelector('[name="{name}"]');
            if (el) el.value = val;
        }}""",
            value,
        )

    @staticmethod
    def _js_str(value: str) -> str:
        """将 Python 字符串转为安全的 JS 字符串字面量。"""
        escaped: str = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        return f"'{escaped}'"

    def _eval_create_iframe(self, page: Page, js_code: str, *args: Any) -> Any:
        """在 CreateCustomer iframe 内执行 JS。

        js_code 是一个 JS 函数字符串，函数签名为 (arg?) => {...}。
        iframe 变量由本方法在 page.evaluate 的包装层注入。
        """
        wrapped = f"""(arg) => {{
            const iframe = document.querySelector('iframe[src*="CreateCustomer"]');
            if (!iframe) return null;
            const fn = {js_code};
            return fn(arg);
        }}"""
        arg = args[0] if args else None
        return page.evaluate(wrapped, arg)

    def _set_chosen(self, page: Page, field_id: str, value: str) -> None:
        """设置 Chosen.js 下拉框的值并触发更新事件。"""
        self._eval_create_iframe(
            page,
            f"""(val) => {{
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#{field_id}', doc).val(val);
            $('#{field_id}', doc).trigger('chosen:updated');
            $('#{field_id}', doc).trigger('change');
        }}""",
            value,
        )

    def _set_input(self, page: Page, field_id: str, value: str) -> None:
        """通过 jQuery 设置输入框的值。"""
        self._eval_create_iframe(
            page,
            f"""(val) => {{
            const $ = iframe.contentWindow.jQuery;
            const doc = iframe.contentDocument;
            $('#{field_id}', doc).val(val);
        }}""",
            value,
        )
