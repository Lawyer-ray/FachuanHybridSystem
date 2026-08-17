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


def _cleanup_stale_sessions() -> None:
    """移除已断开连接的浏览器会话。"""
    global _active_browser_sessions
    _active_browser_sessions[:] = [(pw, br) for pw, br in _active_browser_sessions if br.is_connected()]


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
        from apps.oa_filing.services.oa_scripts.jtn.archive import JtnArchiveScript

        script = JtnArchiveScript(account=str(credential.account), password=str(credential.password))
        playwright, browser = await script.open_page(oa_case_number, description)
        _cleanup_stale_sessions()
        _active_browser_sessions.append((playwright, browser))

    async def open_invoice_page(
        self,
        credential: Any,
        oa_case_number: str,
    ) -> None:
        """打开 OA 发票页面，输入案件编号并跳转到开票页面，保持浏览器打开。"""
        from apps.oa_filing.services.oa_scripts.jtn.invoice import JtnInvoiceScript

        script = JtnInvoiceScript(account=str(credential.account), password=str(credential.password))
        playwright, browser = await script.open_page(oa_case_number)
        _cleanup_stale_sessions()
        _active_browser_sessions.append((playwright, browser))

    async def open_stamp_page(
        self,
        credential: Any,
        oa_case_number: str,
    ) -> None:
        """打开 OA 盖章页面，登录→搜索案件→填表，保持浏览器打开。"""
        from apps.oa_filing.services.oa_scripts.jtn.stamp import JtnStampScript

        script = JtnStampScript(account=str(credential.account), password=str(credential.password))
        playwright, browser = await script.open_page(oa_case_number)
        _cleanup_stale_sessions()
        _active_browser_sessions.append((playwright, browser))

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
        return await script.search_case(case_no)

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
