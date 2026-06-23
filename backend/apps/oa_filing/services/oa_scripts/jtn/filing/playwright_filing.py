"""金诚同达 OA 立案脚本 —— Playwright 立案全流程。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import FrameLocator, Page

from apps.core.services.browser import create_browser_async

from .constants import (
    _AJAX_WAIT,
    _FILING_URL,
    _MEDIUM_WAIT,
    _SHORT_WAIT,
    _XPATH_ADD_CLIENT_BTN,
    _XPATH_NAME_INPUT,
    _XPATH_PERSONAL_TAB,
    _XPATH_SEARCH_BTN,
)
from .filing_models import CaseInfo, ClientInfo, ConflictPartyInfo, ContractInfo

logger = logging.getLogger("apps.oa_filing.jtn")


class PlaywrightFilingMixin:  # pragma: no cover
    """Playwright 立案全流程 mixin。"""

    _account: str
    _password: str
    _page: Page | None
    _context: Any  # BrowserContext | None

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    async def _run_via_playwright(  # pragma: no cover
        self: Any,
        *,
        clients: list[ClientInfo],
        case_info: CaseInfo | None,
        conflict_parties: list[ConflictPartyInfo] | None,
        contract_info: ContractInfo | None,
    ) -> None:
        """Playwright 全量兜底流程。"""
        async with create_browser_async("default", headless=True) as (page, context):
            self._page = page
            self._context = context

            await self._login()
            await self._navigate_to_filing()

            # ── Tab 0: 客户信息 ──
            for i, client in enumerate(clients):
                await self._add_client(client)
                if i < len(clients) - 1:
                    await asyncio.sleep(_MEDIUM_WAIT)

            # ── Tab 1: 案件信息 ──
            if case_info is not None:
                await self._click_next_tab()
                await self._fill_case_info(case_info)

            # ── Tab 2: 利益冲突信息 ──
            if conflict_parties is not None:
                await self._click_next_tab()
                await self._fill_conflict_info(conflict_parties)

            # ── Tab 3: 承办律师信息（跳过） ──
            await self._click_next_tab()

            # ── Tab 4: 委托合同信息 ──
            if contract_info is not None:
                await self._click_next_tab()
                await self._fill_contract_info(contract_info)

            # ── 存草稿 ──
            await self._save_draft()
            logger.info("Playwright 立案流程完成")

    # ------------------------------------------------------------------
    # 登录 / 导航
    # ------------------------------------------------------------------

    async def _login(self: Any) -> None:  # pragma: no cover
        """登录：优先使用缓存 cookies，过期则走 SSO 扫码流程。"""
        assert self._context is not None

        # 优先尝试缓存 cookies
        cached = self._auth.load_cookies()
        if cached is not None:
            await self._auth.inject_to_context(self._context, cached)
            # 验证 cookies 是否有效
            await self._page.goto(_FILING_URL, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(_MEDIUM_WAIT)
            if "login" not in self._page.url.lower():
                logger.info("Playwright 登录成功（使用缓存 cookies）")
                return
            logger.info("缓存 cookies 已失效，重新登录")

        # 走 SSO 扫码 + 凭证登录
        logger.info("SSO 登录（需要扫码）")
        await self._auth.sso_login()
        # 将新 cookies 注入 Playwright context
        new_cookies = self._auth.load_cookies()
        if new_cookies is None:
            raise RuntimeError("SSO 登录后未获取到 cookies")
        await self._auth.inject_to_context(self._context, new_cookies)
        logger.info("Playwright 登录成功（SSO 扫码完成）")

    async def _navigate_to_filing(self: Any) -> None:  # pragma: no cover
        """导航到立案页面（如果尚未在立案页）。"""
        page = self._page
        assert page is not None

        current = page.url
        if "ProjectAppRegNew" in current:
            logger.info("已在立案页面，跳过导航")
            return

        logger.info("导航到立案页: %s", _FILING_URL)
        await page.goto(_FILING_URL, wait_until="domcontentloaded")
        await asyncio.sleep(_MEDIUM_WAIT)
        logger.info("已进入立案页面")

    # ------------------------------------------------------------------
    # 客户操作
    # ------------------------------------------------------------------

    async def _add_client(self: Any, client: ClientInfo) -> None:  # pragma: no cover
        """添加一个委托方。"""
        page = self._page
        assert page is not None

        logger.info("添加委托方: %s (%s)", client.name, client.client_type)

        await page.locator(f"xpath={_XPATH_ADD_CLIENT_BTN}").click()
        await asyncio.sleep(_MEDIUM_WAIT)

        iframe_xpath: str = await self._find_latest_client_iframe(page)
        iframe: FrameLocator = page.frame_locator(f"xpath={iframe_xpath}")

        is_natural: bool = client.client_type == "natural"

        if is_natural:
            await iframe.locator(f"xpath={_XPATH_PERSONAL_TAB}").click()
            await asyncio.sleep(_SHORT_WAIT)

        await iframe.locator(f"xpath={_XPATH_NAME_INPUT}").fill(client.name)

        await iframe.locator(f"xpath={_XPATH_SEARCH_BTN}").click()
        await asyncio.sleep(_AJAX_WAIT)

        found = await self._try_select_client(page, iframe)

        if not found:
            logger.info("未找到客户 %s，进入创建流程", client.name)
            await self._create_new_client(iframe, client)

    # ------------------------------------------------------------------
    # 案件信息
    # ------------------------------------------------------------------

    async def _fill_case_info(self: Any, info: CaseInfo) -> None:  # pragma: no cover
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
            await self._set_select(page, f"{_p}manager_id", info.manager_id)
        else:
            await page.evaluate(
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
        await asyncio.sleep(_AJAX_WAIT)

        # 案件类型（触发 stage + kindtype 加载）
        await self._set_select(page, f"{_p}category_id", info.category)
        await asyncio.sleep(_AJAX_WAIT)

        # 案件阶段（触发 which_side 加载）— 非诉类型无阶段
        if info.stage:
            await self._set_select(page, f"{_p}stage_id", info.stage)
            await asyncio.sleep(_AJAX_WAIT)

        # 代理何方 — 非诉类型无此字段
        if info.stage:
            await self._set_select(page, f"{_p}which_side", info.which_side)

        # 业务类型三级级联
        if info.kindtype:
            await self._set_select(page, f"{_p}kindtype_id", info.kindtype)
            await asyncio.sleep(_AJAX_WAIT)
        if info.kindtype_sed:
            await self._set_select(page, f"{_p}kindtypeSed_id", info.kindtype_sed)
            await asyncio.sleep(_AJAX_WAIT)
        if info.kindtype_thr:
            await self._set_select(page, f"{_p}kindtypeThr_id", info.kindtype_thr)

        # 简单下拉框
        await self._set_select(page, f"{_p}resource_id", info.resource)
        await self._set_select(page, f"{_p}language_id", info.language)
        await self._set_select(page, f"{_p}is_foreign", info.is_foreign)
        await self._set_select(page, f"{_p}is_help", info.is_help)
        await self._set_select(page, f"{_p}is_publicgood", info.is_publicgood)
        await self._set_select(page, f"{_p}is_factory", info.is_factory)
        await self._set_select(page, f"{_p}is_secret", info.is_secret)
        # 是否加急 → 是，并填写原因
        await self._set_select(page, f"{_p}is_emergency", "1")
        await asyncio.sleep(_SHORT_WAIT)
        await self._set_field(page, f"{_p}urgentmemo", "着急将合同盖章拿给客户付款")
        await self._set_select(page, f"{_p}isunion", info.isunion)
        await self._set_select(page, f"{_p}isforeigncoop", info.isforeigncoop)

        # 文本字段
        await self._set_field(page, f"{_p}name", info.case_name)
        await self._set_field(page, f"{_p}desc", info.case_desc)

        # 收案日期（必填，空则取当天）
        start_date: str = info.start_date
        if not start_date:
            from datetime import date as _date

            start_date = _date.today().isoformat()
        await self._set_field(page, f"{_p}start_date", start_date)

        # 客户联系人（name 带动态 GUID，用 name 属性前缀匹配）
        if info.contact_name:
            await page.evaluate(
                f"""() => {{
                var el = document.querySelector('input[name*="pro_pl_name"]');
                if (el) el.value = {self._js_str(info.contact_name)};
            }}"""
            )
        if info.contact_phone:
            await page.evaluate(
                f"""() => {{
                var el = document.querySelector('input[name*="pro_pl_phone"]');
                if (el) el.value = {self._js_str(info.contact_phone)};
            }}"""
            )

        logger.info("案件信息填写完成")

    # ------------------------------------------------------------------
    # 利益冲突信息
    # ------------------------------------------------------------------

    async def _fill_conflict_info(self: Any, parties: list[ConflictPartyInfo]) -> None:  # pragma: no cover
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
                await page.click('a.legal_btn[data-type="addConfict"]')
                await asyncio.sleep(_MEDIUM_WAIT)

            # 获取第 idx 个利冲条目的 GUID
            guid: str = (
                await page.evaluate(
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
            await self._set_field_by_name(page, f"pro_pci_type_{guid}", party.category)
            await self._set_field_by_name(page, f"pro_pci_relation_{guid}", party.legal_position)
            await self._set_field_by_name(page, f"pro_pci_customertype_{guid}", party.customer_type)
            await self._set_field_by_name(page, f"pro_pci_payment_{guid}", party.is_payer)

            # 文本
            await self._set_field_by_name(page, f"pro_pci_name_{guid}", party.name)
            if party.id_number:
                await self._set_field_by_name(page, f"pro_pci_no_{guid}", party.id_number)
            if party.contact_name:
                await self._set_field_by_name(page, f"pro_pci_linker_{guid}", party.contact_name)
            if party.contact_phone:
                await self._set_field_by_name(page, f"pro_pci_phone_{guid}", party.contact_phone)

        logger.info("利冲信息填写完成")

    # ------------------------------------------------------------------
    # 委托合同信息
    # ------------------------------------------------------------------

    async def _fill_contract_info(self: Any, info: ContractInfo) -> None:  # pragma: no cover
        """填写委托合同信息标签。"""
        page = self._page
        assert page is not None
        _p = "ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_"

        logger.info("填写合同信息")

        await self._set_select(page, f"{_p}rec_type", info.rec_type)
        await self._set_select(page, f"{_p}currency", info.currency)
        await self._set_select(page, f"{_p}contract_type", info.contract_type)
        await self._set_select(page, f"{_p}IsFree", info.is_free)

        if info.start_date:
            await self._set_field(page, f"{_p}start_date", info.start_date)
        if info.end_date:
            await self._set_field(page, f"{_p}end_date", info.end_date)
        if info.amount:
            await self._set_field(page, f"{_p}amount", info.amount)

        await self._set_field(page, f"{_p}stamp_count", str(info.stamp_count))

        logger.info("合同信息填写完成")

    # ------------------------------------------------------------------
    # 存草稿 / 切换标签
    # ------------------------------------------------------------------

    async def _save_draft(self: Any) -> None:  # pragma: no cover
        """点击存草稿按钮。

        OA 的 ``projectAppReg.frmOk('0')`` 会弹出 ``confirm`` 对话框，
        需要覆盖 ``window.confirm`` 使其自动返回 ``true``。
        """
        page = self._page
        assert page is not None

        logger.info("点击存草稿")

        # 覆盖 confirm，自动返回 true
        await page.evaluate("window.confirm = () => true")

        await page.click("#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_btnSave")
        await asyncio.sleep(_MEDIUM_WAIT)

        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        logger.info("存草稿完成，当前URL: %s", page.url)

    async def _click_next_tab(self: Any) -> None:  # pragma: no cover
        """点击"下一步"切换到下一个标签页。"""
        page = self._page
        assert page is not None
        await page.click('a.legal_btn[data-type="tabNext"]')
        await asyncio.sleep(_MEDIUM_WAIT)
