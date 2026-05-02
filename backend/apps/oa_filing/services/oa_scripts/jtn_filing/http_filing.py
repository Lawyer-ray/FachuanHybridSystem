"""金诚同达 OA 立案脚本 —— HTTP 立案全流程。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import html as lxml_html

from .constants import (
    _DEFAULT_HTTP_TIMEOUT,
    _FILING_URL,
    _HTTP_HEADERS,
    _LOGIN_URL,
    _PROJECT_HANDLER_BASE,
)
from .filing_models import (
    CaseInfo,
    ClientInfo,
    ConflictPartyInfo,
    ContractInfo,
    FilingFormState,
    ResolvedCustomer,
)

logger = logging.getLogger("apps.oa_filing.jtn")


class HttpFilingMixin:
    """HTTP 立案主链路 mixin。"""

    _account: str
    _password: str

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def _run_via_http(
        self: Any,
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

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    def _http_login(self: Any, client: httpx.Client) -> None:
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

    # ------------------------------------------------------------------
    # 表单加载 / 解析
    # ------------------------------------------------------------------

    def _load_filing_form_state(self: Any, client: httpx.Client) -> FilingFormState:
        response = client.get(_FILING_URL)
        response.raise_for_status()
        return self._extract_filing_form_state(html_text=response.text, base_url=str(response.url))

    def _extract_filing_form_state(self: Any, *, html_text: str, base_url: str) -> FilingFormState:
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

    # ------------------------------------------------------------------
    # 客户解析
    # ------------------------------------------------------------------

    def _resolve_customers_via_http(
        self: Any, *, client: httpx.Client, clients: list[ClientInfo]
    ) -> list[ResolvedCustomer]:
        resolved: list[ResolvedCustomer] = []
        for client_info in clients:
            customer = self._search_customer_http(client=client, client_info=client_info)
            if customer is None:
                raise RuntimeError(f"OA 系统中未找到客户「{client_info.name}」，HTTP 无法创建新客户")
            resolved.append(customer)
        return resolved

    def _search_customer_http(
        self: Any, *, client: httpx.Client, client_info: ClientInfo
    ) -> ResolvedCustomer | None:
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

    # ------------------------------------------------------------------
    # Payload 组装
    # ------------------------------------------------------------------

    def _apply_client_payload(
        self: Any, *, payload: dict[str, str], customers: list[ResolvedCustomer]
    ) -> None:
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
        self: Any,
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

    def _apply_conflict_payload(
        self: Any, *, payload: dict[str, str], parties: list[ConflictPartyInfo]
    ) -> None:
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

    def _apply_contract_payload(
        self: Any, *, payload: dict[str, str], contract_info: ContractInfo
    ) -> None:
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

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------

    def _submit_filing_form_http(
        self: Any, *, client: httpx.Client, action_url: str, payload: dict[str, str]
    ) -> None:
        save_button_name = "ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$btnSave"
        payload[save_button_name] = "　存草稿　"

        response = client.post(action_url, data=payload)
        response.raise_for_status()
        self._assert_http_submit_success(response.text)

    def _assert_http_submit_success(self: Any, response_text: str) -> None:
        if "案件保存未提交" in response_text or "保存并提交成功" in response_text:
            return

        alert_match = re.search(r"alert\\('([^']*)'\\)", response_text)
        if alert_match:
            message = alert_match.group(1).strip()
            raise RuntimeError(f"HTTP 立案失败: {message}")

        raise RuntimeError("HTTP 立案失败：未检测到成功标记")

    def _resolve_manager_id_from_form(
        self: Any, *, html_text: str, manager_name: str
    ) -> str | None:
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

    # ------------------------------------------------------------------
    # 工具方法（也由其他 mixin 使用）
    # ------------------------------------------------------------------

    @staticmethod
    def _project_field_name(field: str) -> str:
        return f"ctl00$ctl00$mainContentPlaceHolder$projmainPlaceHolder$project_{field}"

    @staticmethod
    def _handler_url(method: str) -> str:
        return f"{_PROJECT_HANDLER_BASE}/{method}"

    @staticmethod
    def _parse_json_object(response_text: str) -> dict[str, Any]:
        text = response_text.strip().lstrip("﻿")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise RuntimeError("OA 接口返回格式异常")
        return data

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "")
        text = text.replace("\r", "\n").replace(" ", " ").replace("　", " ")
        text = re.sub(r"[ \t\f\v]+", " ", text)
        return text.strip()
