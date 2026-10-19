"""金诚同达 OA 适配器。

实现 FilingAdapter / StampAdapter / ArchiveAdapter / CaseImportAdapter / ClientImportAdapter，
包含所有 JTN 特有的字段映射、数据组装和脚本调度逻辑。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.apps import apps as django_apps

from apps.core.services.browser import BrowserSessionHandle, close_browser_session

# 保持"打开并留给用户操作"的浏览器会话存活，防止 GC 回收。
# 每个元素是浏览器工厂返回的 BrowserSessionHandle（长生命周期会话句柄）。
_active_browser_sessions: list[BrowserSessionHandle] = []


async def _cleanup_stale_sessions() -> None:
    """剔除断连或窗口已被用户关闭的浏览器会话，并回收残留进程。

    macOS 点窗口关闭按钮只关窗口不退 Chromium 进程（app 常驻 Dock）：
    此类会话 is_connected() 仍为 True 但 context.pages 已空。正常路径由
    wait_open_browsers_closed 的页面级关闭信号回收，这里兜底处理异常路径
    遗留的句柄（如事件循环重启后没收尾的会话），防止进程在 Dock 无限堆积。
    """
    stale = [s for s in _active_browser_sessions if not s.browser.is_connected() or not s.context.pages]
    _active_browser_sessions[:] = [s for s in _active_browser_sessions if s not in stale]
    for session in stale:
        await close_browser_session(session)


from apps.oa_filing.services.base_firm_adapter import (
    ArchiveAdapter,
    CaseGuidLookupAdapter,
    CaseImportAdapter,
    ClientImportAdapter,
    ConflictCheckAdapter,
    FilingAdapter,
    StampAdapter,
)
from apps.oa_filing.services.exceptions import ScriptExecutionError

logger = logging.getLogger("apps.oa_filing.jtn_adapter")

# OA「代理何方」选项随案件阶段变化（WhichSideGetList 逐阶段实测枚举，2026-10-11）：
# 一审族（0301/0306/0311/0312/0313）= 01原告/02被告/09第三人；
# 二审再审族（0302/0303/0305/0307）= 03上诉人/04被上诉人/21原审原告/22原审被告/23原审第三人；
# 仲裁执行申诉族（0304/0308/0309/0314）= 05申请人/06被申请人；
# 0310 申请再审=再审族+申请人族混合；0315 全量；06/07 仲裁/涉外=05/06/09。
_WHICH_SIDE_OPTIONS_BY_STAGE: dict[str, frozenset[str]] = {
    "0301": frozenset({"01", "02", "09"}),
    "0302": frozenset({"03", "04", "21", "22", "23"}),
    "0303": frozenset({"03", "04", "21", "22", "23"}),
    "0304": frozenset({"05", "06"}),
    "0305": frozenset({"03", "04", "21", "22", "23"}),
    "0306": frozenset({"01", "02", "09"}),
    "0307": frozenset({"03", "04", "21", "22", "23"}),
    "0308": frozenset({"05", "06"}),
    "0309": frozenset({"05", "06"}),
    "0310": frozenset({"05", "06", "21", "22", "23"}),
    "0311": frozenset({"01", "02", "09"}),
    "0312": frozenset({"01", "02", "09"}),
    "0313": frozenset({"01", "02", "09"}),
    "0314": frozenset({"05", "06"}),
    "0315": frozenset({"01", "02", "03", "04", "05", "06", "09", "21", "22", "23"}),
    "06": frozenset({"05", "06", "09"}),
    "07": frozenset({"05", "06", "09"}),
}

# 诉讼地位 → (诉讼族值, 特别程序族值)：两族互为同义（原告↔申请人、被告↔被申请人），
# 先取本族、无效时取另一族，保证「劳动仲裁被申请人不会被填成一审原告」这类错位
_WHICH_SIDE_BY_STATUS: dict[str, tuple[str, str]] = {
    "plaintiff": ("01", "05"),
    "defendant": ("02", "06"),
    "third": ("09", "09"),
    "applicant": ("01", "05"),
    "respondent": ("02", "06"),
    "appellant": ("03", "05"),
    "appellee": ("04", "06"),
    "orig_plaintiff": ("21", "05"),
    "orig_defendant": ("22", "06"),
    "orig_third": ("23", "09"),
}

# 利冲表「法律地位」取值（通用原告/被告/第三人标签，与阶段无关的保守映射）
_CONFLICT_RELATION_BY_STATUS: dict[str, str] = {
    "plaintiff": "01",
    "defendant": "02",
    "third": "09",
    "applicant": "01",
    "respondent": "02",
    "appellant": "03",
    "appellee": "04",
    "orig_plaintiff": "21",
    "orig_defendant": "22",
    "orig_third": "23",
}


# ── 模块级函数（Service 层禁止静态方法装饰器，棘轮 test_four_layer_architecture 把关） ──


async def resolve_filing_attachments_safe(contract_id: int) -> list[str]:
    """解析立案合同附件（材料优先 → 绑定文件夹），失败不阻断立案。"""
    from asgiref.sync import sync_to_async

    from apps.oa_filing.services.filing_attachment_service import resolve_filing_attachments

    try:
        return await sync_to_async(resolve_filing_attachments, thread_sensitive=False)(contract_id)
    except Exception:
        logger.exception("立案附件解析失败（按无附件继续）: contract=%s", contract_id)
        return []


def map_which_side_value(legal_status: str, stage: str) -> str:
    """诉讼地位 + 案件阶段 → OA 代理何方值。

    OA 的选项随阶段变化（执行/仲裁是 05申请人/06被申请人，不是 01/02），
    顺序：本族值 → 同义族值 → 该阶段含 01 用 01 → 最小可用值。
    """
    options = _WHICH_SIDE_OPTIONS_BY_STAGE.get(stage, frozenset())
    litigation, special = _WHICH_SIDE_BY_STATUS.get(str(legal_status or ""), ("", ""))
    if options:
        if litigation in options:
            return litigation
        if special in options:
            return special
        if "01" in options:
            return "01"
        return sorted(options)[0]
    return "01"


def map_case_contact(clients: list[Any]) -> tuple[str, str]:
    """客户本案联系人：企业用法定代表人、自然人用本人，缺失回退 "/"。"""
    if not clients:
        return "/", "/"
    first = clients[0]
    if str(first.client_type) == "natural":
        contact_name = str(first.name or "")
    else:
        contact_name = str(first.legal_representative or first.name or "")
    return (contact_name or "/", str(first.phone or "") or "/")


# 民事（category=03）案由关键词 → 业务种类 KindType03_xx。
# 选项清单取自 OA 立案草稿页服务端渲染的 kindtype 下拉（2026-10-11 实测，
# 共 10 类：01人格权 02婚姻家庭继承 03物权 04合同无因管理不当得利 05知产竞争
# 06劳动人事 07海事海商 08公司证券保险票据 09侵权责任 10特殊程序）。
# 顺序即优先级：具体类别在前，"合同/协议"等泛化词殿后；刻意不用裸"公司"等
# 常见于当事人名称的关键词（案由缺失时用案件/合同名称兜底匹配，防误判）。
_CIVIL_KINDTYPE_RULES: tuple[tuple[str, str], ...] = (
    ("劳动", "KindType03_06"),
    ("人事争议", "KindType03_06"),
    ("工伤", "KindType03_06"),
    ("社会保险", "KindType03_06"),
    ("竞业限制", "KindType03_06"),
    ("知识产权", "KindType03_05"),
    ("专利", "KindType03_05"),
    ("商标", "KindType03_05"),
    ("著作权", "KindType03_05"),
    ("版权", "KindType03_05"),
    ("商业秘密", "KindType03_05"),
    ("不正当竞争", "KindType03_05"),
    ("垄断", "KindType03_05"),
    ("股权", "KindType03_08"),
    ("股东", "KindType03_08"),
    ("公司决议", "KindType03_08"),
    ("公司盈余", "KindType03_08"),
    ("损害公司利益", "KindType03_08"),
    ("证券", "KindType03_08"),
    ("票据", "KindType03_08"),
    ("保险", "KindType03_08"),
    ("合伙", "KindType03_08"),
    ("清算", "KindType03_08"),
    ("破产", "KindType03_08"),
    ("婚姻", "KindType03_02"),
    ("离婚", "KindType03_02"),
    ("继承", "KindType03_02"),
    ("抚养", "KindType03_02"),
    ("赡养", "KindType03_02"),
    ("扶养", "KindType03_02"),
    ("收养", "KindType03_02"),
    ("分家析产", "KindType03_02"),
    ("物权", "KindType03_03"),
    ("所有权", "KindType03_03"),
    ("相邻", "KindType03_03"),
    ("共有", "KindType03_03"),
    ("返还原物", "KindType03_03"),
    ("排除妨害", "KindType03_03"),
    ("建筑物区分", "KindType03_03"),
    ("抵押权", "KindType03_03"),
    ("质权", "KindType03_03"),
    ("留置权", "KindType03_03"),
    ("地役权", "KindType03_03"),
    ("宅基地", "KindType03_03"),
    ("土地承包", "KindType03_03"),
    ("海事", "KindType03_07"),
    ("海商", "KindType03_07"),
    ("船舶", "KindType03_07"),
    ("港口", "KindType03_07"),
    ("侵权", "KindType03_09"),
    ("交通事故", "KindType03_09"),
    ("机动车", "KindType03_09"),
    ("产品责任", "KindType03_09"),
    ("损害赔偿", "KindType03_09"),
    ("生命权", "KindType03_09"),
    ("健康权", "KindType03_09"),
    ("身体权", "KindType03_09"),
    ("医疗损害", "KindType03_09"),
    ("医疗事故", "KindType03_09"),
    ("环境污染", "KindType03_09"),
    ("生态破坏", "KindType03_09"),
    ("饲养动物", "KindType03_09"),
    ("高空抛物", "KindType03_09"),
    ("物件损害", "KindType03_09"),
    ("安全保障义务", "KindType03_09"),
    ("人格权", "KindType03_01"),
    ("名誉权", "KindType03_01"),
    ("肖像权", "KindType03_01"),
    ("姓名权", "KindType03_01"),
    ("荣誉权", "KindType03_01"),
    ("隐私", "KindType03_01"),
    ("个人信息", "KindType03_01"),
    ("合同", "KindType03_04"),
    ("协议", "KindType03_04"),
    ("无因管理", "KindType03_04"),
    ("不当得利", "KindType03_04"),
    ("债权", "KindType03_04"),
    ("债务", "KindType03_04"),
    ("借款", "KindType03_04"),
    ("买卖", "KindType03_04"),
    ("租赁", "KindType03_04"),
    ("建设工程", "KindType03_04"),
    ("装修", "KindType03_04"),
    ("赠与", "KindType03_04"),
    ("保管", "KindType03_04"),
    ("运输", "KindType03_04"),
    ("委托", "KindType03_04"),
    ("服务", "KindType03_04"),
    ("保证", "KindType03_04"),
)


class JTNAdapter(
    FilingAdapter,
    StampAdapter,
    ArchiveAdapter,
    ConflictCheckAdapter,
    CaseImportAdapter,
    CaseGuidLookupAdapter,
    ClientImportAdapter,
):
    """金诚同达 OA 适配器。"""

    def __init__(self, account: str, password: str) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.auth.service import JtnAuthService

        self._account = account
        self._password = password
        self._auth = JtnAuthService(account, password)
        # 本次适配器实例打开的半自动浏览器会话句柄（BrowserSessionHandle）。
        # 回收（wait_open_browsers_closed）只处理自己打开的会话，
        # 不误等其他线程/请求打开的浏览器。
        self._opened_sessions: list[BrowserSessionHandle] = []

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

        case: Any = None
        if case_id is not None:
            case = await case_model.objects.aget(pk=case_id)
            category = self._map_case_category(case)
            stage = self._map_case_stage(case)
            which_side = await self._async_map_which_side(case, contract_id)
            start_date = str(case.start_date) if case.start_date else ""
            # 民事案由用于业务种类映射；案由缺失时用案件名称兜底
            cause_text = str(getattr(case, "cause_of_action", "") or "") or str(getattr(case, "name", "") or "")
        else:
            category = {"advisor": "01", "special": "02"}.get(contract.case_type or "", "01")
            stage = ""
            which_side = "01"
            start_date = str(contract.start_date) if contract.start_date else ""
            cause_text = str(contract.name or "")

        kindtype, kindtype_sed = self._map_kindtype(category, principal_parties, cause_text=cause_text)
        if kindtype and not kindtype_sed:
            kindtype_sed = await self._resolve_kindtype_sed(kindtype=kindtype, cause_text=cause_text)
        contact_name, contact_phone = map_case_contact(clients)

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
            contact_name=contact_name,
            contact_phone=contact_phone,
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
                    legal_position=await self._async_map_legal_position(party, case),
                    customer_type="11" if c.client_type == "natural" else "01",
                    id_number=c.id_number,
                )
            )

        # ── 合同信息 ──
        stamp_count = len(principal_parties) + 2
        attachment_paths = await resolve_filing_attachments_safe(contract_id)
        contract_info = ContractInfo(
            rec_type=self._map_fee_mode(contract),
            currency="RMB",
            contract_type="30",
            is_free="N",
            start_date=str(contract.start_date) if contract.start_date else "",
            end_date=str(contract.end_date) if contract.end_date else "",
            amount=str(int(contract.fixed_amount)) if contract.fixed_amount else "",
            stamp_count=stamp_count,
            attachment_paths=attachment_paths,
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
        file_paths: list[str] | None = None,
        project_id: str | None = None,
    ) -> None:
        """打开 OA 归档页面，填写案件编号和小结，保持浏览器打开。

        file_paths 非空时，选完案件后将对应文件上传到"案件业务卷宗"。
        project_id（律所ID/GUID）非空时直达带 keyid 的归档申请页（跳过查
        案件，填充逻辑不变）；None 时按 oa_case_number 查案件（备用方案）。
        """
        from apps.oa_filing.services.oa_scripts.jtn.archive import JtnArchiveScript

        script = JtnArchiveScript(account=str(credential.account), password=str(credential.password))
        session = await script.open_page(oa_case_number, description, file_paths or [], project_id=project_id)
        await _cleanup_stale_sessions()
        self._opened_sessions.append(session)
        _active_browser_sessions.append(session)

    async def open_invoice_page(
        self,
        credential: Any,
        oa_case_number: str,
    ) -> None:
        """打开 OA 发票页面，输入案件编号并跳转到开票页面，保持浏览器打开。"""
        from apps.oa_filing.services.oa_scripts.jtn.invoice import JtnInvoiceScript

        script = JtnInvoiceScript(account=str(credential.account), password=str(credential.password))
        session = await script.open_page(oa_case_number)
        await _cleanup_stale_sessions()
        self._opened_sessions.append(session)
        _active_browser_sessions.append(session)

    async def open_stamp_page(
        self,
        credential: Any,
        oa_case_number: str,
    ) -> None:
        """打开 OA 盖章页面，登录→搜索案件→填表，保持浏览器打开。"""
        from apps.oa_filing.services.oa_scripts.jtn.stamp import JtnStampScript

        script = JtnStampScript(account=str(credential.account), password=str(credential.password))
        session = await script.open_page(oa_case_number)
        await _cleanup_stale_sessions()
        self._opened_sessions.append(session)
        _active_browser_sessions.append(session)

    # ==================================================================
    # ConflictCheckAdapter
    # ==================================================================

    async def open_conflict_check_page(
        self,
        credential: Any,
        keyword: str,
    ) -> None:
        """打开 OA 利益冲突信息预检页面，填入当事人名称并搜索，保持浏览器打开。"""
        from apps.oa_filing.services.oa_scripts.jtn.conflict_check import JtnConflictCheckScript

        script = JtnConflictCheckScript(account=str(credential.account), password=str(credential.password))
        session = await script.open_page(keyword)
        await _cleanup_stale_sessions()
        self._opened_sessions.append(session)
        _active_browser_sessions.append(session)

    async def wait_open_browsers_closed(self) -> None:
        """等本次实例打开的半自动浏览器全部关闭，再逐个回收浏览器会话。

        事件循环一退出，Playwright 的 disconnected 事件就永远无法触发——此前
        靠 disconnected 回调里 asyncio.run(playwright.stop()) 收尾，在运行中的
        循环里必抛 RuntimeError 被吞，node driver 进程全部泄漏。调度器现在会在
        open_* 返回后调用本方法压住循环，直到浏览器关闭、资源回收完毕。
        会话回收统一走工厂的 close_browser_session（CloakBrowser 的
        browser.close() 已内嵌 Playwright driver 的停止）。
        """
        sessions, self._opened_sessions = self._opened_sessions, []

        async def _drain_one(session: BrowserSessionHandle) -> None:
            try:
                await session.wait_user_closed()
            except Exception:
                logger.debug("等待 OA 浏览器关闭时出错（继续回收会话）", exc_info=True)
            await close_browser_session(session)

        await asyncio.gather(*(_drain_one(s) for s in sessions))
        for session in sessions:
            try:
                _active_browser_sessions.remove(session)
            except ValueError:
                pass

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
    # CaseGuidLookupAdapter
    # ==================================================================

    async def lookup_case_guid(self, case_no: str, credential: Any) -> list[str]:
        """按案号查询案件 GUID（案件选择对话框 GET 搜索，纯 HTTP 只读）。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_guid import JtnCaseGuidScript

        script = JtnCaseGuidScript(account=str(credential.account), password=str(credential.password))
        return await script.lookup_case_guids(case_no)

    async def lookup_case_guid_by_name(self, case_name: str, credential: Any) -> list[str]:
        """按案名查询案件 GUID（同一对话框入口，project_name）。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_guid import JtnCaseGuidScript

        script = JtnCaseGuidScript(account=str(credential.account), password=str(credential.password))
        return await script.lookup_case_guids_by_name(case_name)

    async def lookup_case_guid_by_customer_name(self, customer_name: str, credential: Any) -> list[str]:
        """按客户名称查询案件 GUID（同一对话框入口，project_customer_name）。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_guid import JtnCaseGuidScript

        script = JtnCaseGuidScript(account=str(credential.account), password=str(credential.password))
        return await script.lookup_case_guids_by_customer_name(customer_name)

    async def fetch_project_detail(self, keyid: str, credential: Any) -> Any:
        """按 GUID 拉取案件详情（projectView 三 tab 一次 GET，纯 HTTP 只读，同一会话自愈链）。"""
        from apps.oa_filing.services.oa_scripts.jtn.case_guid import JtnCaseGuidScript

        script = JtnCaseGuidScript(account=str(credential.account), password=str(credential.password))
        return await script.fetch_project_detail(keyid)

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
            "labor_arbitration": "0304",
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
        """从我方当事人诉讼地位推断代理何方（按阶段映射，见 _WHICH_SIDE_* 注释）。"""
        case_party_model = django_apps.get_model("cases", "CaseParty")
        contract_party_model = django_apps.get_model("contracts", "ContractParty")
        our_client_ids = {
            cid
            async for cid in contract_party_model.objects.filter(contract_id=contract_id, role="PRINCIPAL")
            .values_list("client_id", flat=True)
            .aiterator()
        }
        party = await case_party_model.objects.filter(case=case, client_id__in=our_client_ids).afirst()
        return map_which_side_value(getattr(party, "legal_status", None) or "", self._map_case_stage(case))

    async def _async_map_legal_position(self, contract_party: Any, case: Any) -> str:
        """对方当事人诉讼地位 → OA 法律地位值（限本案当事人的诉讼地位，保守映射）。"""
        case_party_model = django_apps.get_model("cases", "CaseParty")
        case_party = await case_party_model.objects.filter(case=case, client_id=contract_party.client_id).afirst()
        status = getattr(case_party, "legal_status", None) or ""
        return _CONFLICT_RELATION_BY_STATUS.get(status, "02")

    def _map_fee_mode(self, contract: Any) -> str:
        """收费模式 → OA rec_type。"""
        mapping: dict[str | None, str] = {
            "FIXED": "01",
            "SEMI_RISK": "02",
            "FULL_RISK": "02",
            "CUSTOM": "01",
        }
        return mapping.get(contract.fee_mode, "01")

    async def _resolve_kindtype_sed(self, *, kindtype: str, cause_text: str) -> str:
        """运行时拉取业务子类选项并按案由匹配（ProCategoryGetList level=2）。

        子类清单无法离线枚举（随 OA 数据变动），运行时按 kindtype 拉取后用
        子类名称（去「纠纷/争议」后缀的核心词）匹配案由文本，长名优先；
        唯一选项直接采用，多选项未命中返回空串由用户在 OA 手选。
        失败不阻断立案。
        """
        if not kindtype:
            return ""
        import re as _re

        data = await self._fetch_kindtype_sed_options(kindtype)
        if not data:
            return ""
        if len(data) == 1:
            return str(data[0].get("id") or "")

        def _core(name: str) -> str:
            return _re.sub(r"(纠纷|争议|案件案由)$", "", name) or name

        for item in sorted(data, key=lambda d: len(str(d.get("sc_name") or "")), reverse=True):
            name = str(item.get("sc_name") or "")
            if name and (name in cause_text or _core(name) in cause_text):
                return str(item.get("id") or "")
        return ""

    async def _fetch_kindtype_sed_options(self, kindtype: str) -> list[dict[str, Any]]:
        """拉取业务子类选项；网关回调轮次自愈（单 client 内吃 Set-Cookie 重试）。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.constants import _PRO_CATEGORY_LIST_URL
        from apps.oa_filing.services.oa_scripts.jtn.http_session import (
            build_client,
            cached_cookies,
            http_login_cookies,
            is_login_url,
            is_sso_gateway_url,
        )

        cookies = cached_cookies(self._auth)
        if cookies is None:
            try:
                cookies = await http_login_cookies(self._auth)
            except Exception:
                return []
        try:
            async with build_client(cookies=cookies, timeout=15) as client:
                # 缓存里可能残留已被网关侧失效的 corplink_at/it（同名共存压过新值
                # 致回调死循环，case_guid 前置清理先例），先清再请求
                jar = client.cookies.jar
                for cookie in [c for c in jar if c.name in ("corplink_at", "corplink_it")]:
                    jar.clear(cookie.domain, cookie.path, cookie.name)
                for _round in range(3):
                    try:
                        response = await client.post(_PRO_CATEGORY_LIST_URL, data={"level": "2", "pid": kindtype})
                    except Exception:
                        return []
                    if is_sso_gateway_url(response.url) or is_login_url(response.url):
                        await asyncio.sleep(1)
                        continue
                    try:
                        payload = response.json()
                    except ValueError:
                        continue
                    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                        return [item for item in payload["data"] if isinstance(item, dict)]
                    return []
        except Exception:
            logger.warning("业务子类选项拉取失败（留空由用户手选）: kindtype=%s", kindtype, exc_info=True)
        return []

    def _map_kindtype(self, category: str, principal_parties: list[Any], cause_text: str = "") -> tuple[str, str]:
        """业务种类一级/二级。

        民事（03）按案由关键词映射 KindType03_xx，二级子类由
        _resolve_kindtype_sed 运行时拉取匹配；非诉（01/02）按委托方类型。
        """
        if category == "03":
            for keyword, code in _CIVIL_KINDTYPE_RULES:
                if keyword in cause_text:
                    return code, ""
            return "", ""
        if category not in ("01", "02"):
            return "", ""
        has_natural = any(
            getattr(p, "client", None) and getattr(p.client, "client_type", "") == "natural" for p in principal_parties
        )
        if category == "01":
            return ("KindType01_05", "") if has_natural else ("KindType01_01", "KindType01_0103")
        return ("KindType02_05", "") if has_natural else ("KindType02_01", "")
