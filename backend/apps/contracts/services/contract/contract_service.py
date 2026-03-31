"""合同服务层。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.contracts.models import Contract, ContractAssignment, ContractParty
from apps.contracts.services.party.contract_party_service import ContractPartyService
from apps.contracts.services.payment.contract_finance_mutation_service import ContractFinanceMutationService
from apps.core.config.business_config import BusinessConfig, business_config

from .contract_admin_mutation_service import ContractAdminMutationService
from .contract_mutation_facade import ContractMutationFacade
from .contract_service_query_mixin import ContractServiceQueryMixin
from .contract_validator import ContractValidator
from .contract_workflow_service import ContractWorkflowService
from .mutation import ContractMutationService

if TYPE_CHECKING:
    from apps.contracts.models import ContractPayment
    from apps.contracts.services.assignment.lawyer_assignment_service import LawyerAssignmentService
    from apps.contracts.services.payment.contract_payment_service import ContractPaymentService
    from apps.contracts.services.supplementary.supplementary_agreement_service import SupplementaryAgreementService
    from apps.core.interfaces import ICaseService

    from .contract_access_policy import ContractAccessPolicy
    from .query import ContractQueryFacade, ContractQueryService
    from .supplementary_agreement_query_service import SupplementaryAgreementQueryService


class ContractService(ContractServiceQueryMixin):
    """合同服务 — 封装合同相关的所有业务逻辑。"""

    def __init__(
        self,
        config: BusinessConfig | None = None,
        case_service: ICaseService | None = None,
        lawyer_assignment_service: LawyerAssignmentService | None = None,
        payment_service: ContractPaymentService | None = None,
        supplementary_agreement_service: SupplementaryAgreementService | None = None,
        query_service: ContractQueryService | None = None,
        access_policy: ContractAccessPolicy | None = None,
        query_facade: ContractQueryFacade | None = None,
        supplementary_agreement_query_service: SupplementaryAgreementQueryService | None = None,
    ) -> None:
        self.config = config or business_config
        self._case_service = case_service
        self._lawyer_assignment_service = lawyer_assignment_service
        self._payment_service = payment_service
        self._supplementary_agreement_service = supplementary_agreement_service
        self._supplementary_agreement_query_service = supplementary_agreement_query_service
        self._finance_mutation_service: ContractFinanceMutationService | None = None
        self._party_service: ContractPartyService | None = None
        self._workflow_service: ContractWorkflowService | None = None
        self._query_service = query_service
        self._access_policy = access_policy
        self._query_facade = query_facade
        self._mutation_service: ContractMutationService | None = None
        self._mutation_facade: ContractMutationFacade | None = None
        self._validator: ContractValidator | None = None
        self._admin_mutation_service: ContractAdminMutationService | None = None

    @property
    def query_service(self) -> ContractQueryService:
        if self._query_service is None:
            from .query import ContractQueryService

            self._query_service = ContractQueryService()
        return self._query_service

    @property
    def access_policy(self) -> ContractAccessPolicy:
        if self._access_policy is None:
            from .contract_access_policy import ContractAccessPolicy

            self._access_policy = ContractAccessPolicy()
        return self._access_policy

    @property
    def query_facade(self) -> ContractQueryFacade:
        if self._query_facade is None:
            from .query import ContractQueryFacade

            self._query_facade = ContractQueryFacade(
                query_service=self.query_service,
                access_policy=self.access_policy,
            )
        return self._query_facade

    @property
    def mutation_facade(self) -> ContractMutationFacade:
        if self._mutation_facade is None:
            self._mutation_facade = ContractMutationFacade(
                mutation_service=self.mutation_service,
                workflow_service=self.workflow_service,
                finance_mutation_service=self.finance_mutation_service,
                access_policy=self.access_policy,
                query_service=self.query_service,
                admin_mutation_service=self.admin_mutation_service,
            )
        return self._mutation_facade

    @property
    def admin_mutation_service(self) -> ContractAdminMutationService:
        if self._admin_mutation_service is None:
            self._admin_mutation_service = ContractAdminMutationService()
        return self._admin_mutation_service

    @property
    def validator(self) -> ContractValidator:
        if self._validator is None:
            self._validator = ContractValidator(self.config)
        return self._validator

    @property
    def case_service(self) -> ICaseService:
        """延迟获取案件服务。"""
        if self._case_service is None:
            raise RuntimeError("ContractService.case_service 未注入")
        return self._case_service

    @property
    def lawyer_assignment_service(self) -> LawyerAssignmentService:
        """延迟获取律师指派服务。"""
        if self._lawyer_assignment_service is None:
            raise RuntimeError("ContractService.lawyer_assignment_service 未注入")
        return self._lawyer_assignment_service

    @property
    def payment_service(self) -> ContractPaymentService:
        """延迟获取收款服务。"""
        if self._payment_service is None:
            from apps.contracts.services.payment.contract_payment_service import ContractPaymentService

            self._payment_service = ContractPaymentService()
        return self._payment_service

    @property
    def supplementary_agreement_service(self) -> SupplementaryAgreementService:
        """延迟获取补充协议服务。"""
        if self._supplementary_agreement_service is None:
            from apps.contracts.services.supplementary.supplementary_agreement_service import (
                SupplementaryAgreementService,
            )

            self._supplementary_agreement_service = SupplementaryAgreementService()
        return self._supplementary_agreement_service

    @property
    def supplementary_agreement_query_service(self) -> SupplementaryAgreementQueryService:
        if self._supplementary_agreement_query_service is None:
            from .supplementary_agreement_query_service import SupplementaryAgreementQueryService

            self._supplementary_agreement_query_service = SupplementaryAgreementQueryService()
        return self._supplementary_agreement_query_service

    @property
    def finance_mutation_service(self) -> ContractFinanceMutationService:
        if self._finance_mutation_service is None:
            self._finance_mutation_service = ContractFinanceMutationService(
                get_contract_internal=self._get_contract_internal,
                get_mutation_service=lambda: self.mutation_service,
                supplementary_agreement_service=self.supplementary_agreement_service,
                payment_service=self.payment_service,
            )
        return self._finance_mutation_service

    @property
    def party_service(self) -> ContractPartyService:
        if self._party_service is None:
            self._party_service = ContractPartyService()
        return self._party_service

    @property
    def workflow_service(self) -> ContractWorkflowService:
        if self._workflow_service is None:
            self._workflow_service = ContractWorkflowService(
                mutation_service=self.mutation_service,
                supplementary_agreement_service=self.supplementary_agreement_service,
                finance_mutation_service=self.finance_mutation_service,
                lawyer_assignment_service=self.lawyer_assignment_service,
                case_service=self.case_service,
            )
        return self._workflow_service

    @property
    def mutation_service(self) -> ContractMutationService:
        if self._mutation_service is None:
            self._mutation_service = ContractMutationService(
                validator=self.validator,
                lawyer_assignment_service=self.lawyer_assignment_service,
                case_service=self.case_service,
            )
        return self._mutation_service

    def create_contract(self, data: dict[str, Any]) -> Contract:
        return self.mutation_service.create_contract(data)

    def update_contract(self, contract_id: int, data: dict[str, Any]) -> Contract:
        return self.mutation_service.update_contract(contract_id, data)

    def delete_contract(self, contract_id: int) -> None:
        """删除合同。"""
        self.mutation_service.delete_contract(contract_id)

    def get_finance_summary(self, contract_id: int) -> dict[str, Any]:
        """获取合同财务汇总。"""
        return self.finance_mutation_service.get_finance_summary(contract_id)

    def add_party(self, contract_id: int, client_id: int) -> ContractParty:
        """添加合同当事人。"""
        return self.party_service.add_party(contract_id=contract_id, client_id=client_id)

    def remove_party(self, contract_id: int, client_id: int) -> None:
        """移除合同当事人。"""
        self.party_service.remove_party(contract_id=contract_id, client_id=client_id)

    def update_contract_lawyers(self, contract_id: int, lawyer_ids: list[int]) -> list[ContractAssignment]:
        """更新合同律师指派。"""
        return self.mutation_service.update_contract_lawyers(contract_id, lawyer_ids)

    def create_contract_with_cases(
        self,
        contract_data: dict[str, Any],
        cases_data: list[dict[str, Any]] | None = None,
        assigned_lawyer_ids: list[int] | None = None,
        payments_data: list[dict[str, Any]] | None = None,
        confirm_finance: bool = False,
        user: Any | None = None,
    ) -> Contract:
        """创建合同并关联案件(复合事务操作)。"""
        return self.workflow_service.create_contract_with_cases(
            contract_data=contract_data,
            cases_data=cases_data,
            assigned_lawyer_ids=assigned_lawyer_ids,
            payments_data=payments_data,
            confirm_finance=confirm_finance,
            user=user,
        )

    def update_contract_with_finance(
        self,
        contract_id: int,
        update_data: dict[str, Any],
        user: Any | None = None,
        confirm_finance: bool = False,
        new_payments: list[dict[str, Any]] | None = None,
    ) -> Contract:
        """更新合同(包含财务数据验证和二次确认)。"""
        return self.finance_mutation_service.update_contract_with_finance(
            contract_id=contract_id,
            update_data=update_data,
            user=user,
            confirm_finance=confirm_finance,
            new_payments=new_payments,
        )

    def add_payments(
        self,
        contract_id: int,
        payments_data: list[dict[str, Any]],
        user: Any | None = None,
        confirm: bool = True,
    ) -> list[ContractPayment]:
        """
        添加合同收款记录(委托给 ContractPaymentService)

        Args:
            contract_id: 合同 ID
            payments_data: 收款数据列表
            user: 当前用户对象
            confirm: 是否已确认(默认 True,表示已在上层确认)

        Returns:
            创建的收款记录列表

        Raises:
            PermissionDenied: 权限不足
            ValidationException: 数据验证失败
        """
        return self.finance_mutation_service.add_payments(
            contract_id=contract_id,
            payments_data=payments_data,
            user=user,
            confirm=confirm,
        )

    def get_all_parties(self, contract_id: int) -> list[dict[str, Any]]:
        from .usecases.get_contract_all_parties import GetContractAllPartiesUseCase

        return GetContractAllPartiesUseCase(self.query_service).execute(contract_id)
