"""Business logic services."""

from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Q, QuerySet

from apps.core.exceptions import PermissionDenied
from apps.core.security import OrgAllowedLawyersMixin

from .repos.contract_access_repo import ContractAccessRepo

if TYPE_CHECKING:
    from apps.contracts.models import Contract
    from apps.core.security.access_context import AccessContext


class ContractAccessPolicy(OrgAllowedLawyersMixin):
    def __init__(self, contract_access_repo: ContractAccessRepo | None = None) -> None:
        self._contract_access_repo = contract_access_repo

    @property
    def contract_access_repo(self) -> ContractAccessRepo:
        if self._contract_access_repo is None:
            self._contract_access_repo = ContractAccessRepo()
        return self._contract_access_repo

    def has_access(
        self,
        contract_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool = False,
        contract: Optional["Contract"] = None,
    ) -> bool:
        if perm_open_access:
            return True
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_admin", False):
            return True

        user_id = getattr(user, "id", None)
        allowed_lawyers = self.get_allowed_lawyer_ids(user, org_access)

        if contract is not None:
            if allowed_lawyers and contract.assignments.filter(lawyer_id__in=list(allowed_lawyers)).exists():
                return True
            if user_id and contract.cases.filter(assignments__lawyer_id=user_id).exists():
                return True
            return False

        if self.contract_access_repo.has_assignment_access(contract_id=contract_id, lawyer_ids=allowed_lawyers):
            return True

        if user_id and self.contract_access_repo.has_case_assignment_access(contract_id=contract_id, user_id=user_id):
            return True

        return False

    def ensure_access(
        self,
        *,
        contract_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool = False,
        contract: Optional["Contract"] = None,
        message: str = "无权限访问该合同",
    ) -> None:
        if self.has_access(
            contract_id=contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            contract=contract,
        ):
            return
        raise PermissionDenied(message=message, code="PERMISSION_DENIED")

    def can_create_contract(self, user: Any | None) -> bool:
        return bool(user and getattr(user, "is_authenticated", False))

    def filter_queryset(
        self,
        qs: QuerySet["Contract", "Contract"],
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool = False,
    ) -> QuerySet["Contract", "Contract"]:
        if perm_open_access:
            return qs

        if not user or not getattr(user, "is_authenticated", False):
            return qs.none()

        if getattr(user, "is_admin", False):
            return qs

        user_id = getattr(user, "id", None)
        allowed_lawyers = self.get_allowed_lawyer_ids(user, org_access)
        if not allowed_lawyers and not user_id:
            return qs.none()

        return qs.filter(
            Q(assignments__lawyer_id__in=list(allowed_lawyers)) | Q(cases__assignments__lawyer_id=user_id)
        ).distinct()

    def has_access_ctx(self, *, contract_id: int, ctx: "AccessContext", contract: Optional["Contract"] = None) -> bool:
        return self.has_access(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            contract=contract,
        )

    def ensure_access_ctx(
        self,
        *,
        contract_id: int,
        ctx: "AccessContext",
        contract: Optional["Contract"] = None,
        message: str = "无权限访问该合同",
    ) -> None:
        return self.ensure_access(
            contract_id=contract_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
            contract=contract,
            message=message,
        )

    def filter_queryset_ctx(
        self, qs: QuerySet["Contract", "Contract"], ctx: "AccessContext"
    ) -> QuerySet["Contract", "Contract"]:
        return self.filter_queryset(
            qs=qs, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access
        )
