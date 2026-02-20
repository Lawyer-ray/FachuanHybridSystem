"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from apps.contracts.models import Contract
from apps.core.exceptions import PermissionDenied
from apps.core.security.access_context import AccessContext

if TYPE_CHECKING:
    from apps.contracts.services.payment.contract_finance_mutation_service import ContractFinanceMutationService
    from apps.core.interfaces import CaseDTO

    from .contract_access_policy import ContractAccessPolicy
    from .contract_admin_mutation_service import ContractAdminMutationService
    from .contract_workflow_service import ContractWorkflowService
    from .mutation import ContractMutationService
    from .query import ContractQueryService


class ContractMutationFacade:
    def __init__(
        self,
        *,
        mutation_service: ContractMutationService | None = None,
        workflow_service: ContractWorkflowService | None = None,
        finance_mutation_service: ContractFinanceMutationService | None = None,
        access_policy: ContractAccessPolicy | None = None,
        admin_mutation_service: ContractAdminMutationService | None = None,
        query_service: ContractQueryService | None = None,
    ) -> None:
        self._mutation_service = mutation_service
        self._workflow_service = workflow_service
        self._finance_mutation_service = finance_mutation_service
        self._access_policy = access_policy
        self._admin_mutation_service = admin_mutation_service
        self._query_service = query_service

    @property
    def mutation_service(self) -> ContractMutationService:
        if self._mutation_service is None:
            raise RuntimeError("ContractMutationFacade requires mutation_service")
        return self._mutation_service

    @property
    def workflow_service(self) -> ContractWorkflowService:
        if self._workflow_service is None:
            raise RuntimeError("ContractMutationFacade requires workflow_service")
        return self._workflow_service

    @property
    def finance_mutation_service(self) -> ContractFinanceMutationService:
        if self._finance_mutation_service is None:
            raise RuntimeError("ContractMutationFacade requires finance_mutation_service")
        return self._finance_mutation_service

    @property
    def query_service(self) -> ContractQueryService:
        if self._query_service is None:
            raise RuntimeError("ContractMutationFacade requires query_service")
        return self._query_service

    @property
    def access_policy(self) -> ContractAccessPolicy:
        if self._access_policy is None:
            from .contract_access_policy import ContractAccessPolicy

            self._access_policy = ContractAccessPolicy()
        return self._access_policy

    @property
    def admin_mutation_service(self) -> ContractAdminMutationService:
        if self._admin_mutation_service is None:
            from .contract_admin_mutation_service import ContractAdminMutationService

            self._admin_mutation_service = ContractAdminMutationService()
        return self._admin_mutation_service

    def _ensure_contract_write_access(
        self,
        *,
        contract_id: int,
        user: Any,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> None:
        self.access_policy.ensure_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            message=_("无权限操作该合同"),
        )

    def create_contract_with_cases(
        self,
        *,
        contract_data: dict[str, Any],
        cases_data: list[dict[str, Any]] | None = None,
        assigned_lawyer_ids: list[int] | None = None,
        payments_data: list[dict[str, Any]] | None = None,
        confirm_finance: bool = False,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        if not self.access_policy.can_create_contract(user):
            raise PermissionDenied(message=_("未登录用户无权限执行该操作"), code="PERMISSION_DENIED")
        return self.workflow_service.create_contract_with_cases(
            contract_data=contract_data,
            cases_data=cases_data,
            assigned_lawyer_ids=assigned_lawyer_ids,
            payments_data=payments_data,
            confirm_finance=confirm_finance,
            user=user,
        )

    def create_contract_with_cases_ctx(
        self,
        *,
        contract_data: dict[str, Any],
        ctx: AccessContext,
        cases_data: list[dict[str, Any]] | None = None,
        assigned_lawyer_ids: list[int] | None = None,
        payments_data: list[dict[str, Any]] | None = None,
        confirm_finance: bool = False,
    ) -> Contract:
        return self.create_contract_with_cases(
            contract_data=contract_data,
            cases_data=cases_data,
            assigned_lawyer_ids=assigned_lawyer_ids,
            payments_data=payments_data,
            confirm_finance=confirm_finance,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def update_contract_with_finance(
        self,
        *,
        contract_id: int,
        update_data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        confirm_finance: bool = False,
        new_payments: list[dict[str, Any]] | None = None,
    ) -> Contract:
        self._ensure_contract_write_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.finance_mutation_service.update_contract_with_finance(
            contract_id=contract_id,
            update_data=update_data,
            user=user,
            confirm_finance=confirm_finance,
            new_payments=new_payments,
        )

    def update_contract_with_finance_ctx(
        self,
        *,
        contract_id: int,
        update_data: dict[str, Any],
        ctx: AccessContext,
        confirm_finance: bool = False,
        new_payments: list[dict[str, Any]] | None = None,
    ) -> Contract:
        return self.update_contract_with_finance(
            contract_id=contract_id,
            update_data=update_data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            confirm_finance=confirm_finance,
            new_payments=new_payments,
        )

    def update_contract_lawyers(
        self,
        *,
        contract_id: int,
        lawyer_ids: list[int],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        self._ensure_contract_write_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        self.mutation_service.update_contract_lawyers(contract_id, lawyer_ids)
        return cast(Contract, self.query_service.get_contract_internal(contract_id))

    def update_contract_lawyers_ctx(
        self,
        *,
        contract_id: int,
        lawyer_ids: list[int],
        ctx: AccessContext,
    ) -> Contract:
        return self.update_contract_lawyers(
            contract_id=contract_id,
            lawyer_ids=lawyer_ids,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def delete_contract(
        self,
        *,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        self._ensure_contract_write_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        self.mutation_service.delete_contract(contract_id)

    def delete_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> None:
        return self.delete_contract(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def duplicate_contract(
        self,
        *,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        self._ensure_contract_write_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.admin_mutation_service.duplicate_contract(contract_id)

    def duplicate_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> Contract:
        return self.duplicate_contract(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def renew_advisor_contract(
        self,
        *,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Contract:
        self._ensure_contract_write_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.admin_mutation_service.renew_advisor_contract(contract_id)

    def renew_advisor_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> Contract:
        return self.renew_advisor_contract(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def create_case_from_contract(
        self,
        *,
        contract_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseDTO:
        self._ensure_contract_write_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.admin_mutation_service.create_case_from_contract(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def create_case_from_contract_ctx(self, *, contract_id: int, ctx: AccessContext) -> CaseDTO:
        return self.create_case_from_contract(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
