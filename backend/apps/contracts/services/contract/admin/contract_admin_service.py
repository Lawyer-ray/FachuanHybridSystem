"""合同 Admin 服务 - 处理 Admin 层的复杂业务逻辑"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractStatus
from apps.core.interfaces import CaseDTO
from apps.core.models.enums import CaseStage

if TYPE_CHECKING:
    from apps.contracts.services.assignment.filing_number_service import FilingNumberService

    from ..query import ContractDisplayService, ContractProgressService
    from .contract_admin_document_service import ContractAdminDocumentService
    from .contract_admin_mutation_service import ContractAdminMutationService
    from .contract_admin_query_service import ContractAdminQueryService

logger = logging.getLogger("apps.contracts")


class ContractAdminService:
    """
    合同 Admin 服务

    职责:
    - 处理 Admin 层的复杂业务逻辑
    - 使用 ServiceLocator 获取跨模块服务
    - 通过依赖注入模式接收其他服务

    Requirements: 2.3, 4.1, 4.2
    """

    def __init__(
        self,
        display_service: ContractDisplayService | None = None,
        filing_number_service: FilingNumberService | None = None,
        document_service: ContractAdminDocumentService | None = None,
        query_service: ContractAdminQueryService | None = None,
        mutation_service: ContractAdminMutationService | None = None,
        progress_service: ContractProgressService | None = None,
    ) -> None:
        """
        初始化合同 Admin 服务

        Args:
            display_service: 合同显示服务实例(可选,用于依赖注入)
                           如果不提供,将延迟加载
            filing_number_service: 建档编号服务实例(可选,用于依赖注入)
                                 如果不提供,将延迟加载
        """
        self._display_service = display_service
        self._filing_number_service = filing_number_service
        self._document_service = document_service
        self._query_service = query_service
        self._mutation_service = mutation_service
        self._progress_service = progress_service

    @property
    def display_service(self) -> ContractDisplayService:
        """
        延迟加载合同显示服务

        使用 @property 实现延迟加载,避免循环依赖.
        只有在首次访问时才创建服务实例.

        Returns:
            ContractDisplayService: 合同显示服务实例
        """
        if self._display_service is None:
            from ..query import ContractDisplayService

            self._display_service = ContractDisplayService()
        return self._display_service

    @property
    def filing_number_service(self) -> FilingNumberService:
        """
        延迟加载建档编号服务

        使用 @property 实现延迟加载,避免循环依赖.
        只有在首次访问时才创建服务实例.

        Returns:
            FilingNumberService: 建档编号服务实例
        """
        if self._filing_number_service is None:
            from apps.contracts.services.assignment.filing_number_service import FilingNumberService

            self._filing_number_service = FilingNumberService()
        return self._filing_number_service

    @property
    def document_service(self) -> ContractAdminDocumentService:
        if self._document_service is None:
            from .contract_admin_document_service import ContractAdminDocumentService

            self._document_service = ContractAdminDocumentService()
        return self._document_service

    @property
    def query_service(self) -> ContractAdminQueryService:
        if self._query_service is None:
            from .contract_admin_query_service import ContractAdminQueryService

            self._query_service = ContractAdminQueryService()
        return self._query_service

    @property
    def mutation_service(self) -> ContractAdminMutationService:
        if self._mutation_service is None:
            from .contract_admin_mutation_service import ContractAdminMutationService

            self._mutation_service = ContractAdminMutationService(filing_number_service=self.filing_number_service)
        return self._mutation_service

    @property
    def progress_service(self) -> ContractProgressService:
        if self._progress_service is None:
            from ..query import ContractProgressService

            self._progress_service = ContractProgressService()
        return self._progress_service

    def generate_contract_document(self, contract_id: int) -> dict[str, Any]:
        return self.document_service.generate_contract_document(contract_id)

    def generate_supplementary_agreement(self, contract_id: int, agreement_id: int) -> dict[str, Any]:
        return self.document_service.generate_supplementary_agreement(contract_id, agreement_id)

    def duplicate_contract(self, contract_id: int) -> Contract:
        return self.mutation_service.duplicate_contract(contract_id)

    def can_create_case(self, contract_id: int) -> bool:
        return self.query_service.can_create_case(contract_id)

    def create_case_from_contract(
        self,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseDTO:
        return self.mutation_service.create_case_from_contract(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def renew_advisor_contract(self, contract_id: int) -> Contract:
        return self.mutation_service.renew_advisor_contract(contract_id)

    def generate_advisor_contract_name(self, principal_names: list[str], start_date: date, end_date: date) -> str:
        """生成常法顾问合同名称（委托给 ContractAdminMutationService）"""
        return self.mutation_service.generate_advisor_contract_name(principal_names, start_date, end_date)

    def get_related_cases(self, contract_id: int) -> list[dict[str, Any]]:
        return self.query_service.get_related_cases(contract_id)

    def get_contract_detail_context(self, contract_id: int) -> dict[str, Any]:
        contract = self.query_service.get_contract_detail(contract_id)

        show_representation_stages = contract.case_type in [
            "civil",
            "criminal",
            "administrative",
            "labor",
        ]

        stage_labels = dict(CaseStage.choices)
        representation_stages_display = []
        if contract.representation_stages:
            for stage in contract.representation_stages:
                representation_stages_display.append(stage_labels.get(stage, stage))

        payments = contract.payments.all()
        total_payment_amount = payments.aggregate(total=Sum("amount"))["total"] or 0

        today = timezone.now()
        soon_due_date = today + timedelta(days=7)

        supplementary_agreements = contract.supplementary_agreements.all().order_by("-created_at")
        has_supplementary_agreements = supplementary_agreements.exists()

        try:
            contract_template_display = self.display_service.get_matched_document_template(contract)
            has_contract_template = contract_template_display not in [str(_("无匹配模板")), str(_("查询失败"))]
            contract_templates_list = self.display_service.get_matched_document_templates_list(contract)
        except Exception as exc:
            logger.error("检查合同 %s 的文书模板失败: %s", contract.pk, exc, exc_info=True)
            has_contract_template = False
            contract_template_display = str(_("查询失败"))
            contract_templates_list = []

        try:
            folder_template_display = self.display_service.get_matched_folder_templates(contract)
            has_folder_template = folder_template_display not in [str(_("无匹配模板")), str(_("查询失败"))]
            folder_templates_list = self.display_service.get_matched_folder_templates_list(contract)
        except Exception as exc:
            logger.error("检查合同 %s 的文件夹模板失败: %s", contract.pk, exc, exc_info=True)
            has_folder_template = False
            folder_template_display = str(_("查询失败"))
            folder_templates_list = []

        payment_progress = self.progress_service.get_payment_progress(contract)
        invoice_summary = self.progress_service.get_invoice_summary(contract)

        related_cases = self.query_service.get_related_cases(contract.pk)

        finalized_materials = contract.finalized_materials.all()
        finalized_materials_grouped: dict[str, list[Any]] = {}
        for material in finalized_materials:
            finalized_materials_grouped.setdefault(material.category, []).append(material)

        from apps.contracts.services.contract.integrations import InvoiceUploadService

        invoices_by_payment = InvoiceUploadService().list_invoices_by_contract(contract.pk)

        # 获取客户回款记录
        from apps.contracts.services.client_payment import ClientPaymentRecordService

        client_payment_service = ClientPaymentRecordService()
        client_payments = client_payment_service.get_contract_payment_records(contract.pk)
        total_client_payment = client_payment_service.calculate_total_amount(contract.pk)

        # 归档检查清单数据
        from apps.contracts.services.archive.wiring import build_archive_checklist_service

        archive_checklist_service = build_archive_checklist_service()
        archive_checklist = archive_checklist_service.get_checklist_with_status(contract)

        # 构建 archive_item_code → template_subtype 映射，供归档材料预览按钮使用
        archive_code_to_template: dict[str, str] = {}
        for item in archive_checklist.get("items", []):
            if item.get("template"):
                archive_code_to_template[item["code"]] = item["template"]

        # 判断是否可归档（已结案状态）
        can_archive = contract.status == ContractStatus.CLOSED

        return {
            "contract": contract,
            "show_representation_stages": show_representation_stages,
            "representation_stages_display": representation_stages_display,
            "payments": payments,
            "total_payment_amount": total_payment_amount,
            "today": today,
            "soon_due_date": soon_due_date,
            "has_contract_template": has_contract_template,
            "has_folder_template": has_folder_template,
            "contract_template_display": contract_template_display,
            "folder_template_display": folder_template_display,
            "contract_templates_list": contract_templates_list,
            "folder_templates_list": folder_templates_list,
            "supplementary_agreements": supplementary_agreements,
            "has_supplementary_agreements": has_supplementary_agreements,
            "payment_progress": payment_progress,
            "invoice_summary": invoice_summary,
            "related_cases": related_cases,
            "finalized_materials": finalized_materials,
            "finalized_materials_grouped": finalized_materials_grouped,
            "invoices_by_payment": invoices_by_payment,
            "client_payments": client_payments,
            "total_client_payment": total_client_payment,
            "archive_checklist": archive_checklist,
            "archive_code_to_template": archive_code_to_template,
            "can_archive": can_archive,
        }

    def handle_contract_filing_change(self, contract_id: int, is_filed: bool) -> str | None:
        return self.mutation_service.handle_contract_filing_change(contract_id, is_filed)
