"""Business logic services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from apps.cases.models import Case
from apps.core.security import DjangoPermsMixin

if TYPE_CHECKING:
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy

    from .case_party_query_service import CasePartyQueryService


class CasePartyQueryFacade(DjangoPermsMixin):
    def __init__(
        self,
        *,
        query_service: CasePartyQueryService | None = None,
        access_policy: CaseAccessPolicy | None = None,
    ) -> None:
        self._query_service = query_service
        self._access_policy = access_policy

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

    def list_parties(
        self,
        *,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[Case, Case]:
        qs = self.query_service.list_parties(case_id=case_id)
        if perm_open_access:
            return qs  # type: ignore[return-value]

        if case_id:
            self.access_policy.ensure_access(
                case_id=case_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            )
            return qs  # type: ignore[return-value]

        self.ensure_authenticated(user)
        if self.is_admin(user) or self.is_superuser(user):
            return qs  # type: ignore[return-value]

        allowed_case_ids = self.access_policy.filter_queryset(
            Case.objects.all(),
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        ).values_list("id", flat=True)
        return qs.filter(case_id__in=list(allowed_case_ids))  # type: ignore[return-value]

    def get_party(
        self,
        *,
        party_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> None:
        party = self.query_service.get_party(party_id=party_id)
        self.access_policy.ensure_access(
            case_id=party.case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return party  # type: ignore[return-value]

    def get_available_legal_statuses(
        self,
        *,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[dict[str, Any]]:
        self.access_policy.ensure_access(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return self.query_service.get_available_legal_statuses(case_id=case_id)
