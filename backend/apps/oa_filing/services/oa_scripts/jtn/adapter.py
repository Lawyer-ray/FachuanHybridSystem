"""金诚同达 OA 适配器。

实现 FilingAdapter / StampAdapter / ArchiveAdapter / CaseImportAdapter / ClientImportAdapter，
包含所有 JTN 特有的字段映射、数据组装和脚本调度逻辑。
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps as django_apps

# 保持"打开并留给用户操作"的浏览器会话存活，防止 GC 回收。
# 每个元素是 (playwright, browser) 元组。
_active_browser_sessions: list[tuple[Any, Any]] = []

from apps.oa_filing.services.base_firm_adapter import (
    ArchiveAdapter,
    CaseImportAdapter,
    ClientImportAdapter,
    FilingAdapter,
    StampAdapter,
)
from apps.oa_filing.services.exceptions import ScriptExecutionError

logger = logging.getLogger("apps.oa_filing.jtn_adapter")


class JTNAdapter(FilingAdapter, StampAdapter, ArchiveAdapter, CaseImportAdapter, ClientImportAdapter):
    """金诚同达 OA 适配器。"""

    def __init__(self, account: str, password: str) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)

    # ==================================================================
    # FilingAdapter
    # ==================================================================

    async def execute_filing(
        self,
        session: Any,
        credential: Any,
        contract_id: int,
        case_id: int | None,
    ) -> None:
        """执行金诚同达 OA 立案。"""
        from apps.oa_filing.models import FilingSession, SessionStatus
        from apps.oa_filing.services.oa_scripts.jtn.filing import (
            CaseInfo,
            ClientInfo,
            ConflictPartyInfo,
            ContractInfo,
            JtnFilingScript,
        )

        case_model = django_apps.get_model("cases", "Case")
        contract_model = django_apps.get_model("contracts", "Contract")
        contract_party_model = django_apps.get_model("contracts", "ContractParty")
        contract_assignment_model = django_apps.get_model("contracts", "ContractAssignment")

        # ── 委托方（PRINCIPAL） ──
        principal_parties = [
            p
            async for p in contract_party_model.objects.filter(contract_id=contract_id, role="PRINCIPAL")
            .select_related("client")
            .aiterator()
        ]
        clients: list[ClientInfo] = []
        for party in principal_parties:
            c = party.client
            clients.append(
                ClientInfo(
                    name=c.name,
                    client_type=c.client_type,
                    id_number=c.id_number,
                    address=c.address,
                    phone=c.phone,
                    legal_representative=c.legal_representative,
                )
            )
        if not clients:
            raise ScriptExecutionError("合同没有委托方当事人")

        # ── 主办律师 ──
        primary_assignment = await (
            contract_assignment_model.objects.filter(contract_id=contract_id, is_primary=True)
            .select_related("lawyer")
            .afirst()
        )
        if primary_assignment is None:
            primary_assignment = await (
                contract_assignment_model.objects.filter(contract_id=contract_id).select_related("lawyer").afirst()
            )
        manager_name = primary_assignment.lawyer.real_name or "" if primary_assignment else ""

        # ── 案件信息 ──
        contract = await contract_model.objects.aget(pk=contract_id)

        if case_id is not None:
            case = await case_model.objects.aget(pk=case_id)
            category = self._map_case_category(case)
            stage = self._map_case_stage(case)
            which_side = await self._async_map_which_side(case, contract_id)
            start_date = str(case.start_date) if case.start_date else ""
        else:
            category = {"advisor": "01", "special": "02"}.get(contract.case_type or "", "01")
            stage = ""
            which_side = "01"
            start_date = str(contract.start_date) if contract.start_date else ""

        kindtype, kindtype_sed = self._map_kindtype(category, principal_parties)

        case_info = CaseInfo(
            manager_id="",
            manager_name=manager_name,
            category=category,
            stage=stage,
            which_side=which_side,
            kindtype=kindtype,
            kindtype_sed=kindtype_sed,
            kindtype_thr="",
            case_name=contract.name,
            case_desc=contract.name,
            start_date=start_date,
            contact_name="/",
            contact_phone="/",
        )

        # ── 对方当事人（利冲） ──
        opposing_parties = [
            p
            async for p in contract_party_model.objects.filter(contract_id=contract_id, role="OPPOSING")
            .select_related("client")
            .aiterator()
        ]
        conflict_parties: list[ConflictPartyInfo] = []
        for party in opposing_parties:
            c = party.client
            conflict_parties.append(
                ConflictPartyInfo(
                    name=c.name,
                    legal_position=await self._async_map_legal_position(party),
                    customer_type="11" if c.client_type == "natural" else "01",
                    id_number=c.id_number,
                )
            )

        # ── 合同信息 ──
        stamp_count = len(principal_parties) + 2
        contract_info = ContractInfo(
            rec_type=self._map_fee_mode(contract),
            currency="RMB",
            contract_type="30",
            is_free="N",
            start_date=str(contract.start_date) if contract.start_date else "",
            end_date=str(contract.end_date) if contract.end_date else "",
            amount=str(int(contract.fixed_amount)) if contract.fixed_amount else "",
            stamp_count=stamp_count,
        )

        script = JtnFilingScript(account=self._account, password=self._password)
        await script.run(
            clients,
            case_info=case_info,
            conflict_parties=conflict_parties,
            contract_info=contract_info,
        )

    # ==================================================================
    # StampAdapter
    # ==================================================================

    async def execute_stamp(self, session: Any) -> None:
        """执行盖章申请。"""
        from apps.oa_filing.services.oa_scripts.jtn.stamp import JtnStampScript, StampFormData

        credential = session.credential
        if credential is None:
            raise RuntimeError("盖章申请缺少 OA 登录凭证")

        form_data = StampFormData(
            oa_case_number=session.oa_case_number,
            file_path=session.file_path,
        )
        script = JtnStampScript(account=str(credential.account), password=str(credential.password))
        await script.run(form_data)

    # ==================================================================
    # ArchiveAdapter
    # ==================================================================

    async def execute_archive(self, session: Any) -> None:
        """执行归档材料提交。"""
        from apps.oa_filing.services.oa_scripts.jtn.archive import ArchiveFormData, JtnArchiveScript

        credential = session.credential
        if credential is None:
            raise RuntimeError("归档申请缺少 OA 登录凭证")

        form_data = ArchiveFormData(
            oa_case_number=session.oa_case_number,
            file_paths=session.file_paths,
        )
        script = JtnArchiveScript(account=str(credential.account), password=str(credential.password))
        await script.run(form_data)

    async def open_oa_page(
        self,
        credential: Any,
        oa_case_number: str,
        description: str,
    ) -> None:
        """打开 OA 归档页面，填写案件编号和小结，保持浏览器打开。"""
        import asyncio

        from playwright.async_api import async_playwright

        from apps.oa_filing.services.oa_scripts.jtn.archive.constants import (
            _POPUP_IFRAME_KEYWORD,
            AJAX_WAIT,
            ARCHIVE_PAGE_URL,
            DESCRIPTION_SELECTOR,
            IFRAME_SEARCH_FN,
            MEDIUM_WAIT,
            POPUP_WAIT,
            SHORT_WAIT,
        )

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # ── 登录 ──
            cached = self._auth.load_cookies()
            if cached:
                logger.info("使用缓存 cookies 登录 OA")
                await self._auth.inject_to_context(context, cached)
                await page.goto(ARCHIVE_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(MEDIUM_WAIT)
                if "login" not in page.url.lower():
                    logger.info("Cookies 有效，已进入归档页面")
                else:
                    logger.warning("缓存 cookies 已失效，执行 SSO 扫码登录")
                    cookies = await self._auth.sso_login()
                    await self._auth.inject_to_context(context, cookies)
            else:
                logger.info("无缓存 cookies，执行 SSO 扫码登录")
                cookies = await self._auth.sso_login()
                await self._auth.inject_to_context(context, cookies)

            # ── 导航到归档页面 ──
            await page.goto(ARCHIVE_PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(MEDIUM_WAIT)

            if "login" in page.url.lower():
                logger.warning("当前在登录页，等待 SSO 扫码...")
                await page.wait_for_url("**/ims.jtn.com/projclose/**", timeout=180_000)
                await asyncio.sleep(MEDIUM_WAIT)

            logger.info("已进入归档页面: %s", page.url)

            # ── 搜索并选择案件 ──
            if oa_case_number:
                await self._search_and_select_case(page, oa_case_number)

            # ── 填写案件小结 ──
            await self._fill_description(page, description)

            # ── 点击删除按钮（清除默认附件） ──
            await self._click_delete_button(page)

            logger.info("OA 页面已打开并填写完成，浏览器保持打开状态")
            # 保持 playwright/browser 引用，防止 GC 回收关闭浏览器
            _active_browser_sessions.append((playwright, browser))

        except Exception:
            await browser.close()
            await playwright.stop()
            raise

    async def open_invoice_page(
        self,
        credential: Any,
        oa_case_number: str,
    ) -> None:
        """打开 OA 发票管理页面，输入案件编号、搜索、点击申请对外开票，保持浏览器打开。"""
        import asyncio

        from playwright.async_api import async_playwright

        _INVOICE_URL = (
            "https://ims.jtn.com/invoice/ProjectFapiaoRequest.aspx"
            "?FirstModel=FINANCE&SecondModel=FINANCE002&ThirdModel=FINANCE002-04"
        )
        _CASE_NO_INPUT = "#ctl00_ctl00_mainContentPlaceHolder_projmainPlaceHolder_project_no"
        _SEARCH_BTN_XP = '//*[@id="wrap"]/div[1]/div[2]/div/div[4]/div[2]/table/tbody/tr[5]/td[3]/div/a'
        _FIRST_APPLY_LINK_XP = '//*[@id="wrap"]/div[1]/div[2]/div/div[5]/table/tbody/tr[2]/td[9]/a'

        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # ── 登录 ──
            cached = self._auth.load_cookies()
            if cached:
                logger.info("使用缓存 cookies 登录 OA")
                await self._auth.inject_to_context(context, cached)
                await page.goto(_INVOICE_URL, wait_until="domcontentloaded", timeout=60_000)
                await asyncio.sleep(2)
                if "login" not in page.url.lower():
                    logger.info("Cookies 有效，已进入发票页面")
                else:
                    logger.warning("缓存 cookies 已失效，执行 SSO 扫码登录")
                    cookies = await self._auth.sso_login()
                    await self._auth.inject_to_context(context, cookies)
            else:
                logger.info("无缓存 cookies，执行 SSO 扫码登录")
                cookies = await self._auth.sso_login()
                await self._auth.inject_to_context(context, cookies)

            # ── 导航到发票管理页面 ──
            await page.goto(_INVOICE_URL, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(2)

            if "login" in page.url.lower():
                logger.warning("当前在登录页，等待 SSO 扫码...")
                await page.wait_for_url("**/ims.jtn.com/invoice/**", timeout=180_000)
                await asyncio.sleep(2)

            logger.info("已进入发票管理页面: %s", page.url)

            # ── 输入案件编号 ──
            if oa_case_number:
                logger.info("输入案件编号: %s", oa_case_number)
                await page.evaluate(f"""() => {{
                    const el = document.getElementById("{_CASE_NO_INPUT.lstrip("#")}");
                    if (el) {{
                        el.removeAttribute('readonly');
                        el.removeAttribute('disabled');
                        el.value = '{oa_case_number}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}""")
                await asyncio.sleep(0.5)

                # ── 点击查找 ──
                logger.info("点击查找按钮")
                search_btn = page.locator(f"xpath={_SEARCH_BTN_XP}")
                count = await search_btn.count()
                if count > 0:
                    await search_btn.click(timeout=10_000)
                else:
                    logger.warning("XPath 未找到查找按钮，跳过")
                await asyncio.sleep(3)

                # ── 点击第一个结果的"申请对外开票" ──
                logger.info("点击申请对外开票")
                try:
                    apply_link = page.locator(f"xpath={_FIRST_APPLY_LINK_XP}")
                    await apply_link.first.click(timeout=10_000)
                    await asyncio.sleep(2)
                    logger.info("已跳转到开票页面: %s", page.url)
                except Exception:
                    logger.warning("XPath 未找到，尝试 JS 点击")
                    result = await page.evaluate("""() => {
                        const links = document.querySelectorAll('#wrap table a');
                        for (const a of links) {
                            if (a.textContent.includes('申请') || a.textContent.includes('开票')) {
                                a.click(); return 'clicked: ' + a.textContent.trim();
                            }
                        }
                        return 'not found';
                    }""")
                    logger.info("JS 点击结果: %s", result)
                    await asyncio.sleep(2)

            logger.info("开票页面已打开，浏览器保持打开状态")
            # 保持 playwright/browser 引用，防止 GC 回收关闭浏览器
            _active_browser_sessions.append((playwright, browser))

        except Exception:
            await browser.close()
            await playwright.stop()
            raise

    async def _search_and_select_case(self, page: Any, case_no: str) -> None:
        """搜索案件并选择（复用 archive 的逻辑）。"""
        import asyncio

        from apps.oa_filing.services.oa_scripts.jtn.archive.constants import (
            _POPUP_IFRAME_KEYWORD,
            AJAX_WAIT,
            IFRAME_SEARCH_FN,
            POPUP_WAIT,
            SHORT_WAIT,
        )

        logger.info("搜索案件: %s", case_no)

        await page.evaluate("""() => {
            const tds = document.querySelectorAll('td');
            for (const td of tds) {
                if (td.textContent.trim().startsWith('案件编号')) {
                    const row = td.closest('tr');
                    if (row) { const img = row.querySelector('img'); if (img) { img.click(); return; } }
                }
            }
        }""")
        await asyncio.sleep(POPUP_WAIT)

        popup_frame = None
        for frame in page.frames:
            if _POPUP_IFRAME_KEYWORD in frame.url:
                popup_frame = frame
                break
        if popup_frame is None:
            raise RuntimeError("未找到案件搜索弹窗 iframe")

        await popup_frame.evaluate(f"""() => {{
            const el = document.getElementById("project_no");
            el.removeAttribute("readonly");
            el.value = "{case_no}";
        }}""")
        await asyncio.sleep(SHORT_WAIT)

        await popup_frame.evaluate(IFRAME_SEARCH_FN)
        await asyncio.sleep(AJAX_WAIT)

        radio_count = await popup_frame.locator('input[type="radio"]').count()
        if radio_count == 0:
            raise RuntimeError(f"未找到案件: {case_no}")

        await popup_frame.evaluate('document.querySelectorAll("input[type=radio]")[0].click()')
        await asyncio.sleep(SHORT_WAIT)

        await page.evaluate("""() => {
            const layers = document.querySelectorAll(".layui-layer");
            for (const layer of layers) {
                for (const a of layer.querySelectorAll("a")) {
                    if (a.innerText.trim() === "选择") { a.click(); return; }
                }
            }
        }""")
        await asyncio.sleep(POPUP_WAIT)
        logger.info("案件已回填到主页面")

    async def _fill_description(self, page: Any, description: str) -> None:
        """填写案件小结。"""
        import asyncio

        from apps.oa_filing.services.oa_scripts.jtn.archive.constants import DESCRIPTION_SELECTOR, SHORT_WAIT

        logger.info("填写案件小结: %s", description)
        result = await page.evaluate(f"""() => {{
            const ta = document.querySelector('{DESCRIPTION_SELECTOR}');
            if (!ta) return 'textarea not found';
            ta.readOnly = false;
            ta.removeAttribute('readonly');
            ta.value = '{description}';
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return 'ok';
        }}""")
        if result != "ok":
            raise RuntimeError(f"填写案件小结失败: {result}")
        await asyncio.sleep(SHORT_WAIT)

    async def _click_delete_button(self, page: Any) -> None:
        """点击删除按钮（清除默认附件行）。"""
        import asyncio

        from apps.oa_filing.services.oa_scripts.jtn.archive.constants import MEDIUM_WAIT

        logger.info("点击删除按钮")
        btn = page.locator('//*[@id="tblFiles"]/tbody/tr[3]/td[3]')
        count = await btn.count()
        if count == 0:
            logger.warning("未找到删除按钮")
            return
        await btn.first.click()
        await asyncio.sleep(MEDIUM_WAIT)
        logger.info("删除按钮已点击")

    # ==================================================================
    # CaseImportAdapter
    # ==================================================================

    async def execute_case_import(self, session: Any) -> None:
        """执行案件导入（委托给 CaseImportService）。"""
        from apps.oa_filing.services.case_import_service import CaseImportService

        CaseImportService(session).run_import(
            case_nos=session.result_data.get("case_nos", []),
            matched_case_nos=session.result_data.get("matched_case_nos"),
        )

    async def fetch_case_detail(self, case_no: str, credential: Any) -> Any | None:
        """从 OA 获取案件详情，返回 OACaseData 或 None。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript

        script = JtnCaseImportScript(
            account=str(credential.account),
            password=str(credential.password),
        )
        return await script.fetch_single_case(case_no)

    def search_cases(
        self,
        case_nos: list[str],
        credential: Any,
        *,
        workers: int = 2,
        headless: bool = True,
        progress_callback: Any = None,
    ) -> Any:
        """批量搜索案件，返回 AsyncGenerator[(case_no, OACaseData | None)]。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_import import JtnCaseImportScript

        script = JtnCaseImportScript(
            account=str(credential.account),
            password=str(credential.password),
            headless=headless,
            progress_callback=progress_callback,
        )
        return script.search_cases(case_nos, workers=workers, playwright_fallback=True)

    def build_case_detail_url(self, oa_data: Any) -> str:
        """构建 OA 案件详情页 URL。"""
        return f"https://ims.jtn.com/project/projectView.aspx?keyid={oa_data.keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"

    # ==================================================================
    # ClientImportAdapter
    # ==================================================================

    async def execute_client_import(self, session: Any, *, headless: bool = True, limit: int | None = None) -> None:
        """执行客户导入（委托给 ClientImportService）。"""
        from apps.oa_filing.services.client_import_service import ClientImportService

        ClientImportService(session).run_import(headless=headless, limit=limit)

    def iter_customers(
        self, session: Any, *, headless: bool = True, limit: int | None = None, progress_callback: Any = None
    ) -> Any:
        """返回 AsyncGenerator[OACustomerData]。"""
        from apps.oa_filing.services.oa_scripts.jtn.client_import import JtnClientImportScript

        credential = session.credential
        script = JtnClientImportScript(
            account=str(credential.account),
            password=str(credential.password),
            headless=headless,
            progress_callback=progress_callback,
        )
        return script.run(limit=limit)

    # ==================================================================
    # JTN 字段映射（私有）
    # ==================================================================

    def _map_case_category(self, case: Any) -> str:
        """案件类型 → OA category_id。"""
        mapping: dict[str | None, str] = {
            "civil": "03",
            "criminal": "05",
            "administrative": "04",
            "labor": "03",
            "intl": "06",
            "execution": "03",
            "bankruptcy": "03",
            "special": "02",
            "advisor": "01",
        }
        return mapping.get(case.case_type, "03")

    def _map_case_stage(self, case: Any) -> str:
        """案件阶段 → OA stage_id。"""
        category = self._map_case_category(case)
        if category in ("01", "02"):
            return ""

        stage: str | None = case.current_stage

        civil: dict[str | None, str] = {
            "first_trial": "0301",
            "second_trial": "0305",
            "enforcement": "0314",
            "apply_retrial": "0310",
            "retrial_first": "0313",
            "retrial_second": "0313",
            "rehearing_first": "0313",
            "rehearing_second": "0313",
            "petition": "0308",
            "apply_protest": "0309",
            "petition_protest": "0309",
            "review": "0310",
        }
        admin: dict[str | None, str] = {
            "administrative_review": "0401",
            "first_trial": "0402",
            "second_trial": "0403",
            "retrial_first": "0404",
            "retrial_second": "0405",
            "petition": "0406",
            "apply_retrial": "0408",
            "review": "0409",
            "rehearing_first": "0410",
            "rehearing_second": "0411",
        }
        criminal: dict[str | None, str] = {
            "private_prosecution": "0500",
            "investigation": "0501",
            "prosecution_review": "0502",
            "first_trial": "0503",
            "second_trial": "0504",
            "retrial_first": "0507",
            "retrial_second": "0508",
            "petition": "0509",
            "review": "0510",
            "death_penalty_review": "0511",
            "rehearing_first": "0512",
            "rehearing_second": "0513",
            "apply_retrial": "0509",
            "apply_protest": "0509",
            "petition_protest": "0509",
        }

        if category == "03":
            return civil.get(stage, "0301")
        if category == "04":
            return admin.get(stage, "0402")
        return criminal.get(stage, "0503")

    async def _async_map_which_side(self, case: Any, contract_id: int) -> str:
        """从我方当事人诉讼地位推断代理何方。"""
        case_party_model = django_apps.get_model("cases", "CaseParty")
        contract_party_model = django_apps.get_model("contracts", "ContractParty")
        our_client_ids = {
            cid
            async for cid in contract_party_model.objects.filter(contract_id=contract_id, role="PRINCIPAL")
            .values_list("client_id", flat=True)
            .aiterator()
        }
        party = await case_party_model.objects.filter(case=case, client_id__in=our_client_ids).afirst()
        mapping = {"plaintiff": "01", "defendant": "02", "third": "09"}
        return mapping.get(getattr(party, "legal_status", None) or "", "01")

    async def _async_map_legal_position(self, contract_party: Any) -> str:
        """对方当事人诉讼地位 → OA 法律地位值。"""
        case_party_model = django_apps.get_model("cases", "CaseParty")
        case_party = await case_party_model.objects.filter(client_id=contract_party.client_id).afirst()
        mapping = {"plaintiff": "01", "defendant": "02", "third": "09"}
        return mapping.get(getattr(case_party, "legal_status", None) or "", "02")

    def _map_fee_mode(self, contract: Any) -> str:
        """收费模式 → OA rec_type。"""
        mapping: dict[str | None, str] = {
            "FIXED": "01",
            "SEMI_RISK": "02",
            "FULL_RISK": "02",
            "CUSTOM": "01",
        }
        return mapping.get(contract.fee_mode, "01")

    def _map_kindtype(self, category: str, principal_parties: list[Any]) -> tuple[str, str]:
        """业务种类一级/二级。"""
        if category not in ("01", "02"):
            return "", ""
        has_natural = any(
            getattr(p, "client", None) and getattr(p.client, "client_type", "") == "natural" for p in principal_parties
        )
        if category == "01":
            return ("KindType01_05", "") if has_natural else ("KindType01_01", "KindType01_0103")
        return ("KindType02_05", "") if has_natural else ("KindType02_01", "")
