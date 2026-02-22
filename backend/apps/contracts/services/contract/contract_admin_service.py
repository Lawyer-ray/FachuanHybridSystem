"""合同 Admin 服务 - 处理 Admin 层的复杂业务逻辑"""

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional, cast

from django.db.models import Sum
from django.utils import timezone

from apps.core.enums import CaseStage
from apps.core.interfaces import CaseDTO

if TYPE_CHECKING:
    from .contract_admin_document_service import ContractAdminDocumentService
    from .contract_admin_mutation_service import ContractAdminMutationService
    from .contract_admin_query_service import ContractAdminQueryService
    from .contract_display_service import ContractDisplayService
    from .contract_progress_service import ContractProgressService
    from apps.contracts.services.assignment.filing_number_service import FilingNumberService

from apps.contracts.models import Contract

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
        display_service: Optional["ContractDisplayService"] = None,
        filing_number_service: Optional["FilingNumberService"] = None,
        document_service: Optional["ContractAdminDocumentService"] = None,
        query_service: Optional["ContractAdminQueryService"] = None,
        mutation_service: Optional["ContractAdminMutationService"] = None,
        progress_service: Optional["ContractProgressService"] = None,
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
    def display_service(self) -> "ContractDisplayService":
        """
        延迟加载合同显示服务

        使用 @property 实现延迟加载,避免循环依赖.
        只有在首次访问时才创建服务实例.

        Returns:
            ContractDisplayService: 合同显示服务实例
        """
        if self._display_service is None:
            from .contract_display_service import ContractDisplayService

            self._display_service = ContractDisplayService()
        return self._display_service

    @property
    def filing_number_service(self) -> "FilingNumberService":
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
    def document_service(self) -> "ContractAdminDocumentService":
        if self._document_service is None:
            from .contract_admin_document_service import ContractAdminDocumentService

            self._document_service = ContractAdminDocumentService()
        return self._document_service

    @property
    def query_service(self) -> "ContractAdminQueryService":
        if self._query_service is None:
            from .contract_admin_query_service import ContractAdminQueryService

            self._query_service = ContractAdminQueryService()
        return self._query_service

    @property
    def mutation_service(self) -> "ContractAdminMutationService":
        if self._mutation_service is None:
            from .contract_admin_mutation_service import ContractAdminMutationService

            self._mutation_service = ContractAdminMutationService(filing_number_service=self.filing_number_service)
        return self._mutation_service

    @property
    def progress_service(self) -> "ContractProgressService":
        if self._progress_service is None:
            from .contract_progress_service import ContractProgressService

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
            has_contract_template = contract_template_display not in ["无匹配模板", "查询失败"]
        except Exception as exc:
            logger.error(f"检查合同 {cast(int, contract.pk)} 的文书模板失败: {exc!s}", exc_info=True)
            has_contract_template = False

        try:
            folder_template_display = self.display_service.get_matched_folder_templates(contract)
            has_folder_template = folder_template_display not in ["无匹配模板", "查询失败"]
        except Exception as exc:
            logger.error(f"检查合同 {cast(int, contract.pk)} 的文件夹模板失败: {exc!s}", exc_info=True)
            has_folder_template = False

        payment_progress = self.progress_service.get_payment_progress(contract)
        invoice_summary = self.progress_service.get_invoice_summary(contract)

        related_cases = self.query_service.get_related_cases(cast(int, contract.pk))

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
            "supplementary_agreements": supplementary_agreements,
            "has_supplementary_agreements": has_supplementary_agreements,
            "payment_progress": payment_progress,
            "invoice_summary": invoice_summary,
            "related_cases": related_cases,
        }

    def handle_contract_filing_change(self, contract_id: int, is_archived: bool) -> str | None:
        return self.mutation_service.handle_contract_filing_change(contract_id, is_archived)
