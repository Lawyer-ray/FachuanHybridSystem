"""案件导入服务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import Contract
from apps.core.enums import CaseType
from apps.oa_filing.models import CaseImportPhase, CaseImportSession, CaseImportStatus
from apps.oa_filing.services.oa_scripts.jtn_case_import import (
    JtnCaseImportScript,
    OACaseData,
    OACaseCustomerData,
    OACaseInfoData,
    OAConflictData,
)

if TYPE_CHECKING:
    from apps.organization.models import AccountCredential

logger = logging.getLogger("apps.oa_filing.case_import_service")


# ============================================================
# 数据结构
# ============================================================
@dataclass
class CasePreviewResult:
    """案件预览结果。"""

    case_no: str
    status: str  # matched / unmatched / error
    existing_contract_id: int | None = None
    customer_names: list[str] | None = None
    error_message: str = ""


@dataclass
class CaseImportResult:
    """单条案件导入结果。"""

    case_no: str
    status: str  # created / updated / skipped / error
    contract_id: int | None = None
    message: str = ""
    customer_ids: list[int] | None = None
    conflict_warnings: list[str] | None = None


# ============================================================
# 服务类
# ============================================================
class CaseImportService:
    """案件导入服务。"""

    def __init__(self, session: CaseImportSession) -> None:
        self._session = session
        self._credential: AccountCredential | None = None

    @property
    def credential(self) -> AccountCredential:
        """获取OA凭证。"""
        if self._credential is None:
            assert self._session.credential is not None
            self._credential = self._session.credential
        return self._credential

    def parse_excel(self, file_path: str) -> list[str]:
        """解析Excel文件，提取案件编号列表。

        Args:
            file_path: Excel文件路径

        Returns:
            案件编号列表
        """
        import pandas as pd

        # 直接读取"案件编号"列
        df = pd.read_excel(file_path, header=1)  # 第二行是表头
        case_nos = df["案件编号"].dropna().tolist()
        case_nos = [str(c).strip() for c in case_nos if str(c).strip()]

        logger.info("从Excel解析出 %d 个案件编号", len(case_nos))
        return case_nos

    def preview_cases(self, case_nos: list[str]) -> list[CasePreviewResult]:
        """预览案件，查找哪些已存在，哪些需要从OA导入。

        Args:
            case_nos: 案件编号列表

        Returns:
            预览结果列表
        """
        results: list[CasePreviewResult] = []

        for case_no in case_nos:
            try:
                # 在Backend中查找已存在的合同
                existing_contracts = Contract.objects.filter(
                    law_firm_oa_case_number=case_no
                ).prefetch_related("contract_parties__client")

                if existing_contracts.exists():
                    # 已存在，获取客户名称
                    customer_names: list[str] = []
                    for contract in existing_contracts:
                        for cp in contract.contract_parties.select_related("client").all():
                            if cp.client:
                                customer_names.append(cp.client.name)

                    results.append(
                        CasePreviewResult(
                            case_no=case_no,
                            status="matched",
                            existing_contract_id=existing_contracts.first().id if existing_contracts else None,
                            customer_names=list(set(customer_names)),
                        )
                    )
                else:
                    # 需要从OA导入
                    results.append(
                        CasePreviewResult(
                            case_no=case_no,
                            status="unmatched",
                        )
                    )

            except Exception as exc:
                logger.warning("预览案件异常 %s: %s", case_no, exc)
                results.append(
                    CasePreviewResult(
                        case_no=case_no,
                        status="error",
                        error_message=str(exc),
                    )
                )

        return results

    def run_import(
        self,
        case_nos: list[str],
        *,
        matched_case_nos: list[str] | None = None,
        headless: bool = True,
    ) -> list[CaseImportResult]:
        """执行导入流程。

        Args:
            case_nos: 要导入的案件编号列表
            matched_case_nos: 已匹配的案件编号列表（只更新不新建）
            headless: 是否无头模式运行Playwright

        Returns:
            导入结果列表
        """
        import django

        logger.info(
            "开始导入案件，session_id=%d case_nos=%d headless=%s",
            self._session.id,
            len(case_nos),
            headless,
        )

        # 先关闭所有数据库连接，因为 Playwright 会创建 asyncio 事件循环
        django.db.connections.close_all()

        results: list[CaseImportResult] = []
        matched_set = set(matched_case_nos) if matched_case_nos else set()

        try:
            started_at = self._session.started_at or timezone.now()
            self._update_session(
                status=CaseImportStatus.IN_PROGRESS,
                phase=CaseImportPhase.DISCOVERING,
                started_at=started_at,
                total_count=len(case_nos),
                progress_message="正在连接OA系统",
            )

            # 创建Playwright脚本
            script = JtnCaseImportScript(
                account=self.credential.account,
                password=self.credential.password,
                headless=headless,
                progress_callback=self._handle_script_progress,
            )

            # 批量处理案件
            total = len(case_nos)
            success_count = 0
            skip_count = 0
            error_count = 0

            for index, case_no in enumerate(case_nos, start=1):
                self._update_session(
                    phase=CaseImportPhase.IMPORTING,
                    progress_message=f"正在导入案件 ({index}/{total}): {case_no}",
                )

                result = self._import_single_case(
                    case_no=case_no,
                    script=script,
                    should_exist=case_no in matched_set,
                )
                results.append(result)

                if result.status in ("created", "updated"):
                    success_count += 1
                elif result.status == "skipped":
                    skip_count += 1
                else:
                    error_count += 1

                # 每处理10条记录刷新一次会话
                if index % 10 == 0:
                    self._update_session(
                        success_count=success_count,
                        skip_count=skip_count,
                        error_count=error_count,
                    )

                logger.info("[%d/%d] 导入案件 %s: status=%s", index, total, case_no, result.status)

            # 更新最终状态
            self._update_session(
                success_count=success_count,
                skip_count=skip_count,
                error_count=error_count,
                status=CaseImportStatus.COMPLETED,
                phase=CaseImportPhase.COMPLETED,
                completed_at=timezone.now(),
                progress_message="导入完成",
                result_data={
                    "results": [
                        {
                            "case_no": r.case_no,
                            "status": r.status,
                            "contract_id": r.contract_id,
                            "message": r.message,
                        }
                        for r in results
                    ]
                },
            )

            logger.info(
                "案件导入完成，total=%d, success=%d, skipped=%d, error=%d",
                total,
                success_count,
                skip_count,
                error_count,
            )
            return results

        except Exception as exc:
            logger.exception("案件导入失败: %s", exc)
            self._update_session(
                status=CaseImportStatus.FAILED,
                phase=CaseImportPhase.FAILED,
                error_message=str(exc),
                completed_at=timezone.now(),
                progress_message="导入失败",
            )
            raise

    def _handle_script_progress(self, payload: dict[str, Any]) -> None:
        """处理Playwright脚本的进度回调。"""
        event = str(payload.get("event") or "")
        message = str(payload.get("message") or "").strip()

        if event == "searching":
            case_no = str(payload.get("case_no", ""))
            self._update_session(
                phase=CaseImportPhase.DISCOVERING,
                progress_message=f"正在搜索案件 {case_no}",
            )

    def _update_session(self, **fields: Any) -> None:
        """更新会话状态。"""
        if not fields:
            return
        fields["updated_at"] = timezone.now()
        CaseImportSession.objects.filter(pk=self._session.pk).update(**fields)
        for key, value in fields.items():
            if key != "updated_at":
                setattr(self._session, key, value)

    def _import_single_case(
        self,
        case_no: str,
        script: JtnCaseImportScript,
        should_exist: bool = False,
    ) -> CaseImportResult:
        """导入单条案件数据。"""
        try:
            # 从OA提取数据
            oa_data = script.search_case(case_no)
            if not oa_data:
                return CaseImportResult(
                    case_no=case_no,
                    status="error",
                    message="在OA系统中未找到该案件",
                )

            # 检查利益冲突
            conflict_warnings = self._check_conflicts(oa_data.conflicts)

            # 创建/更新案件和合同
            contract_id = self._create_or_update_case(oa_data)

            if contract_id:
                return CaseImportResult(
                    case_no=case_no,
                    status="created" if not should_exist else "updated",
                    contract_id=contract_id,
                    message="导入成功",
                    conflict_warnings=conflict_warnings,
                )
            else:
                return CaseImportResult(
                    case_no=case_no,
                    status="error",
                    message="创建/更新合同失败",
                    conflict_warnings=conflict_warnings,
                )

        except Exception as exc:
            logger.warning("导入案件异常 %s: %s", case_no, exc)
            return CaseImportResult(
                case_no=case_no,
                status="error",
                message=str(exc),
            )

    def _check_conflicts(self, conflicts: list[OAConflictData]) -> list[str]:
        """检查利益冲突。"""
        warnings: list[str] = []
        # TODO: 实现实际的利益冲突检查逻辑
        for conflict in conflicts:
            warnings.append(f"利益冲突: {conflict.name}")
        return warnings

    def _assign_lawyer(self, contract: Contract, lawyer_name: str, is_primary: bool = False) -> None:
        """为合同指派律师。

        Args:
            contract: 合同实例
            lawyer_name: 律师姓名
            is_primary: 是否主办律师
        """
        from apps.contracts.models import ContractAssignment
        from apps.organization.models import Lawyer

        if not lawyer_name:
            return

        try:
            # 按姓名查找律师
            lawyer = Lawyer.objects.filter(real_name=lawyer_name).first()
            if not lawyer:
                # 尝试按用户名查找
                lawyer = Lawyer.objects.filter(username=lawyer_name).first()

            if lawyer:
                ContractAssignment.objects.get_or_create(
                    contract=contract,
                    lawyer=lawyer,
                    defaults={"is_primary": is_primary},
                )
                logger.info("为合同 %d 指派律师 %s (主办: %s)", contract.id, lawyer_name, is_primary)
            else:
                logger.warning("未找到律师: %s", lawyer_name)
        except Exception as exc:
            logger.warning("指派律师异常 %s: %s", lawyer_name, exc)

    def _create_or_update_case(self, oa_data: OACaseData) -> int | None:
        """创建或更新案件和合同。"""
        from apps.cases.models import Case
        from apps.client.models import Client
        from apps.contracts.models import ContractParty, ContractAssignment
        from apps.organization.models import Lawyer

        with transaction.atomic():
            # 1. 查找或创建客户
            customer_ids: list[int] = []
            for customer_data in oa_data.customers:
                client = self._get_or_create_client(customer_data)
                if client:
                    customer_ids.append(client.id)

            # 2. 获取案件信息
            case_info = oa_data.case_info
            case_name = case_info.case_name if case_info else None
            case_stage = case_info.case_stage if case_info else None

            # 构建OA详情页URL
            oa_detail_url = f"https://ims.jtn.com/projectView.aspx?keyid={oa_data.keyid}&FirstModel=PROJECT&SecondModel=PROJECT002"

            # 3. 查找或创建合同（先创建Contract，因为它不依赖Case）
            existing_contract = Contract.objects.filter(
                law_firm_oa_case_number=oa_data.case_no
            ).first()

            if existing_contract:
                # 更新现有合同
                if case_info:
                    if case_info.acceptance_date:
                        existing_contract.start_date = self._parse_date(case_info.acceptance_date)
                    if case_info.responsible_lawyer:
                        # 更新主办律师
                        self._assign_lawyer(existing_contract, case_info.responsible_lawyer, is_primary=True)
                existing_contract.law_firm_oa_url = oa_detail_url
                existing_contract.save()
                contract = existing_contract
            else:
                # 创建新合同
                contract = Contract.objects.create(
                    case_type=CaseType.CIVIL,  # 默认民商事
                    law_firm_oa_case_number=oa_data.case_no,
                    law_firm_oa_url=oa_detail_url,
                    name=case_name or f"OA案件 {oa_data.case_no}",
                    start_date=self._parse_date(case_info.acceptance_date) if case_info and case_info.acceptance_date else None,
                )
                # 添加主办律师
                if case_info and case_info.responsible_lawyer:
                    self._assign_lawyer(contract, case_info.responsible_lawyer, is_primary=True)

            # 4. 查找或创建案件（Case.contract 指向 Contract）
            existing_case = Case.objects.filter(
                contract=contract
            ).first()

            if existing_case:
                case = existing_case
            else:
                # 创建新案件，关联到合同
                case = Case.objects.create(
                    contract=contract,
                    name=case_name or f"OA案件 {oa_data.case_no}",
                    current_stage=case_stage or "一审",
                )

            # 5. 创建客户-合同关联
            for customer_id in customer_ids:
                client = Client.objects.get(pk=customer_id)
                # 创建 ContractParty（关联客户和合同）
                party, _ = ContractParty.objects.get_or_create(
                    contract=contract,
                    client=client,
                    defaults={"role": "PRINCIPAL"},  # 默认委托人的身份
                )

            # 6. 处理利益冲突当事人（添加到对方当事人）
            for conflict in oa_data.conflicts:
                # 尝试查找已存在的当事人
                existing_party = ContractParty.objects.filter(
                    contract=contract,
                    client__name=conflict.name
                ).first()
                if not existing_party:
                    # 创建冲突方为对方当事人
                    # 先尝试获取或创建这个冲突方作为Client
                    conflict_client = Client.objects.filter(name=conflict.name).first()
                    if not conflict_client:
                        conflict_client = Client.objects.create(
                            name=conflict.name,
                            client_type="natural",  # 默认自然人
                            is_our_client=False,  # 不是我方当事人
                        )
                    ContractParty.objects.get_or_create(
                        contract=contract,
                        client=conflict_client,
                        defaults={"role": "OPPOSING"},  # 对方当事人
                    )

            logger.info("创建/更新合同成功: contract_id=%d case_id=%d", contract.id, case.id)
            return contract.id

    def _get_or_create_client(self, customer_data: OACaseCustomerData) -> Client | None:
        """获取或创建客户。"""
        from apps.client.models import Client

        try:
            # 按名称查找
            client = Client.objects.filter(name=customer_data.name).first()
            if client:
                # 更新信息
                if not client.phone and customer_data.phone:
                    client.phone = customer_data.phone
                if not client.address and customer_data.address:
                    client.address = customer_data.address
                if not client.id_number and customer_data.id_number:
                    client.id_number = customer_data.id_number
                client.save()
                return client

            # 创建新客户
            return Client.objects.create(
                name=customer_data.name,
                client_type="legal" if customer_data.customer_type == "legal" else "natural",
                phone=customer_data.phone or "",
                address=customer_data.address or "",
                id_number=customer_data.id_number or "",
                legal_representative=customer_data.legal_representative or "",
                is_our_client=True,  # OA客户都是我方当事人
            )

        except Exception as exc:
            logger.warning("创建/更新客户异常 %s: %s", customer_data.name, exc)
            return None

    @staticmethod
    def _parse_date(date_str: str) -> Any:
        """解析日期字符串。"""
        from datetime import datetime

        if not date_str:
            return None

        # 清理字符串，只保留日期部分
        date_str = date_str.strip().split(" ")[0]  # 去掉时间部分

        # 尝试多种日期格式
        formats = [
            "%Y/%m/%d",
            "%Y-%m-%d",
            "%Y年%m月%d日",
            "%m/%d/%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        return None