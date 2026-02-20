"""合同服务基础：初始化、依赖注入、查询"""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from apps.contracts.models import Contract
from apps.contracts.services._contract_helpers_mixin import ContractHelpersMixin
from apps.core import business_config
from apps.core.business_config import BusinessConfig
from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.core.permissions import AccessContext, PermissionMixin
from apps.core.querysets import ContractQuerySetManager

if TYPE_CHECKING:
    from apps.contracts.services.contract_payment_service import ContractPaymentService
    from apps.contracts.services.lawyer_assignment_service import LawyerAssignmentService
    from apps.contracts.services.supplementary_agreement_service import SupplementaryAgreementService
    from apps.core.interfaces import ICaseService

logger = logging.getLogger("apps.contracts")

__all__ = ["ContractServiceBase"]


class ContractServiceBase(ContractHelpersMixin, PermissionMixin):
    """合同服务基类：初始化与查询"""

    def __init__(
        self,
        config: BusinessConfig | None = None,
        case_service: ICaseService | None = None,
        lawyer_assignment_service: LawyerAssignmentService | None = None,
        payment_service: ContractPaymentService | None = None,
        supplementary_agreement_service: SupplementaryAgreementService | None = None,
    ):
        self.config = config or business_config # type: ignore
        self._case_service = case_service
        self._lawyer_assignment_service = lawyer_assignment_service
        self._payment_service = payment_service
        self._supplementary_agreement_service = supplementary_agreement_service

    @property
    def case_service(self) -> ICaseService:
        if self._case_service is None:
            from apps.core.dependencies.business_case import build_case_service_with_deps
            from apps.core.dependencies.business_client import build_client_service
            from apps.core.dependencies.business_contract import build_contract_query_service

            self._case_service = build_case_service_with_deps(
                contract_service=build_contract_query_service(),
                client_service=build_client_service(),
            )
        return self._case_service

    @property
    def lawyer_assignment_service(self) -> LawyerAssignmentService:
        if self._lawyer_assignment_service is None:
            from apps.contracts.services.lawyer_assignment_service import LawyerAssignmentService
            from apps.core.dependencies.business_organization import build_lawyer_service

            self._lawyer_assignment_service = LawyerAssignmentService(lawyer_service=build_lawyer_service())
        return self._lawyer_assignment_service

    @property
    def payment_service(self) -> ContractPaymentService:
        if self._payment_service is None:
            from apps.contracts.services.contract_payment_service import ContractPaymentService

            self._payment_service = ContractPaymentService()
        return self._payment_service

    @property
    def supplementary_agreement_service(self) -> SupplementaryAgreementService:
        if self._supplementary_agreement_service is None:
            from apps.contracts.services.supplementary_agreement_service import SupplementaryAgreementService
            from apps.core.dependencies.business_client import build_client_service

            self._supplementary_agreement_service = SupplementaryAgreementService(client_service=build_client_service())
        return self._supplementary_agreement_service

    def get_contract_queryset(self) -> QuerySet[Contract, Contract]:
        """获取带预加载的合同查询集"""
        return ContractQuerySetManager.with_standard_prefetch()

    def list_contracts(
        self,
        case_type: str | None = None,
        status: str | None = None,
        is_archived: bool | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Contract, Contract]:
        """获取合同列表（包含权限过滤）"""
        qs = self.get_contract_queryset().order_by("-id")

        if case_type:
            qs = qs.filter(case_type=case_type)
        if status:
            qs = qs.filter(status=status)
        if is_archived is not None:
            qs = qs.filter(is_archived=is_archived)

        ctx = AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        if self.has_open_access(ctx) or self.is_admin(ctx):
            return qs

        if user and getattr(user, "is_authenticated", False) and org_access:
            from django.db.models import Q

            user_id = getattr(user, "id", None)
            qs = qs.filter(
                Q(assignments__lawyer_id__in=list(org_access["lawyers"]))
                | Q(assignments__lawyer_id=user_id)
                | Q(cases__assignments__lawyer_id=user_id)
            ).distinct()

        return qs

    def _get_contract_internal(self, contract_id: int) -> Contract:
        """内部获取合同（无权限检查）"""
        try:
            return self.get_contract_queryset().get(id=contract_id)
        except Contract.DoesNotExist as e:
            raise NotFoundError(f"合同 {contract_id} 不存在") from e

    def get_contract(
        self,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        """获取单个合同（包含权限检查）"""
        contract = self._get_contract_internal(contract_id)

        ctx = AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        self.check_resource_access(
            ctx,
            resource_check=lambda c: self._check_contract_access(contract, c.user, c.org_access),
            error_message=_("无权限访问该合同"), # type: ignore
        )
        return contract
