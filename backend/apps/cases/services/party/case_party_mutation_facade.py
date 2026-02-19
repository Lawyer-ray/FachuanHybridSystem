"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.core.security import DjangoPermsMixin

if TYPE_CHECKING:
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy

    from .case_party_mutation_service import CasePartyMutationService
    from .case_party_query_service import CasePartyQueryService


class CasePartyMutationFacade(DjangoPermsMixin):
    def __init__(
        self,
        *,
        mutation_service: CasePartyMutationService | None = None,
        query_service: CasePartyQueryService | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        self._mutation_service = mutation_service
        self._query_service = query_service
        self._access_policy = access_policy

    @property
    def mutation_service(self) -> CasePartyMutationService:
        if self._mutation_service is None:
            raise RuntimeError("CasePartyMutationFacade requires mutation_service")
        return self._mutation_service

    @property
    def query_service(self) -> CasePartyQueryService:
        if self._query_service is None:
            from .case_party_query_service import CasePartyQueryService

            self._query_service = CasePartyQueryService()
        return self._query_service

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            from apps.cases.services.case.case_access_policy import CaseAccessPolicy

            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    def create_party(
        self,
        *,
        case_id: int,
        client_id: int,
        legal_status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        if not perm_open_access:
            self.ensure_authenticated(user)
        self.access_policy.ensure_access(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.mutation_service.create_party(
            case_id=case_id, client_id=client_id, legal_status=legal_status, user=user
        )

    def update_party(
        self,
        *,
        party_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        if not perm_open_access:
            self.ensure_authenticated(user)
        party = self.query_service.get_party(party_id=party_id)
        self.access_policy.ensure_access(
            case_id=party.case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        new_case_id = data.get("case_id")
        if new_case_id and new_case_id != party.case_id:
            self.access_policy.ensure_access(
                case_id=new_case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            )
        return self.mutation_service.update_party(party_id=party_id, data=data, user=user)

    def delete_party(
        self,
        *,
        party_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        if not perm_open_access:
            self.ensure_authenticated(user)
        party = self.query_service.get_party(party_id=party_id)
        self.access_policy.ensure_access(
            case_id=party.case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.mutation_service.delete_party(party_id=party_id, user=user)

    def create_party_internal(self, *, case_id: int, client_id: int, legal_status: str | None = None) -> bool:
        return self.mutation_service.create_party_internal(
            case_id=case_id, client_id=client_id, legal_status=legal_status
        )
