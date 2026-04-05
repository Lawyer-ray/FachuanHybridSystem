"""案件当事人服务 — API 层入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db import transaction
from django.db.models import QuerySet

from apps.cases.models import CaseParty
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.interfaces import IClientService, IContractService

if TYPE_CHECKING:
    from .case_party_mutation_facade import CasePartyMutationFacade
    from .case_party_query_facade import CasePartyQueryFacade


class CasePartyService:
    def __init__(
        self,
        client_service: IClientService | None = None,
        contract_service: IContractService | None = None,
    ) -> None:
        self._client_service = client_service
        self._contract_service = contract_service
        self._access_policy: CaseAccessPolicy | None = None
        self._query_facade: CasePartyQueryFacade | None = None
        self._mutation_facade: CasePartyMutationFacade | None = None

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    @property
    def query_facade(self) -> CasePartyQueryFacade:
        if self._query_facade is None:
            from .case_party_query_facade import CasePartyQueryFacade

            self._query_facade = CasePartyQueryFacade(access_policy=self.access_policy)
        return self._query_facade

    @property
    def mutation_facade(self) -> CasePartyMutationFacade:
        if self._mutation_facade is None:
            from .case_party_mutation_facade import CasePartyMutationFacade
            from .case_party_mutation_service import CasePartyMutationService
            from .case_party_query_service import CasePartyQueryService

            if self._client_service is None:
                raise RuntimeError("CasePartyService.client_service 未注入")
            if self._contract_service is None:
                raise RuntimeError("CasePartyService.contract_service 未注入")

            self._mutation_facade = CasePartyMutationFacade(
                mutation_service=CasePartyMutationService(
                    client_service=self._client_service,
                    contract_service=self._contract_service,
                ),
                query_service=CasePartyQueryService(),
                access_policy=self.access_policy,
            )
        return self._mutation_facade

    def get_available_legal_statuses(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[dict[str, str]]:
        return self.query_facade.get_available_legal_statuses(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def list_parties(
        self,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[CaseParty, CaseParty]:
        return cast(
            QuerySet[CaseParty, CaseParty],
            self.query_facade.list_parties(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def get_party(
        self,
        party_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseParty:
        return cast(  # type: ignore[redundant-cast]
            CaseParty,
            self.query_facade.get_party(
                party_id=party_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def create_party(
        self,
        case_id: int,
        client_id: int,
        legal_status: str | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseParty:
        return cast(  # type: ignore[redundant-cast]
            CaseParty,
            self.mutation_facade.create_party(
                case_id=case_id,
                client_id=client_id,
                legal_status=legal_status,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def update_party(
        self,
        party_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseParty:
        return cast(  # type: ignore[redundant-cast]
            CaseParty,
            self.mutation_facade.update_party(
                party_id=party_id,
                data=data,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def delete_party(
        self,
        party_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        return cast(  # type: ignore[redundant-cast]
            dict[str, bool],
            self.mutation_facade.delete_party(
                party_id=party_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def create_party_internal(self, case_id: int, client_id: int, legal_status: str | None = None) -> bool:
        return self.mutation_facade.create_party_internal(
            case_id=case_id,
            client_id=client_id,
            legal_status=legal_status,
        )
