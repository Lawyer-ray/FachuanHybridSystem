"""金诚同达 OA 立案脚本 —— Playwright 立案全流程。"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from playwright.sync_api import FrameLocator, Page, sync_playwright

from .constants import (
    _AJAX_WAIT,
    _FILING_URL,
    _HTTP_HEADERS,
    _LOGIN_URL,
    _MEDIUM_WAIT,
    _SHORT_WAIT,
    _XPATH_ADD_CLIENT_BTN,
    _XPATH_NAME_INPUT,
    _XPATH_PERSONAL_TAB,
    _XPATH_SEARCH_BTN,
)
from .filing_models import CaseInfo, ClientInfo, ConflictPartyInfo, ContractInfo

logger = logging.getLogger("apps.oa_filing.jtn")


class PlaywrightFilingMixin:
    """Playwright 立案全流程 mixin。"""

    _account: str
    _password: str
    _page: Page | None
    _context: Any  # BrowserContext | None

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def _run_via_playwright(
        self: Any,
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
            # Docker/NAS 环境通常没有 XServer，缺少 DISPLAY 时自动走无头模式。
            _headless = not bool(os.environ.get("DISPLAY"))
            browser = pw.chromium.launch(headless=_headless)
            self._context = browser.new_context()

            # 应用 playwright-stealth 反检测
            try:
                from playwright_stealth import Stealth

                stealth = Stealth()
                stealth.apply_stealth_sync(self._context)
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

    # ------------------------------------------------------------------
    # 登录 / 导航
    # ------------------------------------------------------------------

    def _login(self: Any) -> None:
        """通过 httpx 接口登录，将 cookie 注入 Playwright context。"""
        import httpx as _httpx

        logger.info("接口登录: %s", _LOGIN_URL)

        with _httpx.Client(headers=_HTTP_HEADERS, follow_redirects=True, timeout=15) as client:
            # 1. GET 登录页，拿 ASP.NET_SessionId + CSRFToken
            r = client.get(_LOGIN_URL)
            csrf_match = re.search(
                r'name=["\']CSRFToken["\'] value=["\']([^"\']+)["\']', r.text
            )
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

    def _navigate_to_filing(self: Any) -> None:
        """导航到立案页面。"""
        page = self._page
        assert page is not None

        logger.info("导航到立案页: %s", _FILING_URL)
        page.goto(_FILING_URL, wait_until="domcontentloaded")
        time.sleep(_MEDIUM_WAIT)
        logger.info("已进入立案页面")

    # ------------------------------------------------------------------
    # 客户操作
    # ------------------------------------------------------------------

    def _add_client(self: Any, client: ClientInfo) -> None:
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

    # ------------------------------------------------------------------
    # 案件信息
    # ------------------------------------------------------------------

    def _fill_case_info(self: Any, info: CaseInfo) -> None:
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

    # ------------------------------------------------------------------
    # 利益冲突信息
    # ------------------------------------------------------------------

    def _fill_conflict_info(self: Any, parties: list[ConflictPartyInfo]) -> None:
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

    # ------------------------------------------------------------------
    # 委托合同信息
    # ------------------------------------------------------------------

    def _fill_contract_info(self: Any, info: ContractInfo) -> None:
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

    # ------------------------------------------------------------------
    # 存草稿 / 切换标签
    # ------------------------------------------------------------------

    def _save_draft(self: Any) -> None:
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

    def _click_next_tab(self: Any) -> None:
        """点击"下一步"切换到下一个标签页。"""
        page = self._page
        assert page is not None
        page.click('a.legal_btn[data-type="tabNext"]')
        time.sleep(_MEDIUM_WAIT)
