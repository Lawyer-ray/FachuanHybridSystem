"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.cases.models import Case
from apps.core.security.access_context import AccessContext

if TYPE_CHECKING:
    from .case_full_create_service import CaseFullCreateService
    from .case_mutation_service import CaseMutationService


class CaseMutationFacade:
    def __init__(
        self,
        *,
        mutation_service: CaseMutationService | None = None,
        full_create_service: CaseFullCreateService | None = None,
    ) -> None:
        self._mutation_service = mutation_service
        self._full_create_service = full_create_service

    @property
    def mutation_service(self) -> CaseMutationService:
        if self._mutation_service is None:
            raise RuntimeError("CaseMutationFacade requires mutation_service")
        return self._mutation_service

    @property
    def full_create_service(self) -> CaseFullCreateService:
        if self._full_create_service is None:
            raise RuntimeError("CaseMutationFacade requires full_create_service")
        return self._full_create_service

    def create_case(
        self,
        *,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        return self.mutation_service.create_case(
            data=data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def create_case_ctx(self, *, data: dict[str, Any], ctx: AccessContext) -> Case:
        return self.create_case(
            data=data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def update_case(
        self,
        *,
        case_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Case:
        return self.mutation_service.update_case(
            case_id=case_id,
            data=data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def update_case_ctx(self, *, case_id: int, data: dict[str, Any], ctx: AccessContext) -> Case:
        return self.update_case(
            case_id=case_id,
            data=data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def delete_case(
        self,
        *,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        self.mutation_service.delete_case(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def delete_case_ctx(self, *, case_id: int, ctx: AccessContext) -> None:
        return self.delete_case(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def create_case_full(
        self, *, data: dict[str, Any], actor_id: int | None, user: Any | None = None
    ) -> dict[str, Any]:
        return self.full_create_service.create_case_full(data=data, actor_id=actor_id, user=user)

    def create_case_full_ctx(self, *, data: dict[str, Any], ctx: AccessContext) -> dict[str, Any]:
        actor_id = getattr(ctx.user, "id", None) if ctx.user else None
        return self.create_case_full(data=data, actor_id=actor_id, user=ctx.user)
