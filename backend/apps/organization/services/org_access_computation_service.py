"""Business logic services."""

from __future__ import annotations

from apps.core.interfaces import ICaseService
from apps.organization.models import Lawyer


class OrgAccessComputationService:
    def __init__(self, *, case_service: ICaseService) -> None:
        self._case_service = case_service

    def compute(self, user: Lawyer) -> dict[str, object]:
        team_ids: set[int] = set(user.lawyer_teams.values_list("id", flat=True))

        from apps.organization.models import Lawyer as _Lawyer  # avoid circular at module level

        lawyers: set[int] = set(
            _Lawyer.objects.filter(lawyer_teams__id__in=team_ids).values_list("id", flat=True).distinct()
        ) if team_ids else set()

        if not lawyers:
            lawyers.add(user.id)

        extra_cases = self.get_user_extra_case_access(user.id)

        return {
            "lawyers": lawyers,
            "team_ids": team_ids,
            "extra_cases": extra_cases,
        }

    def get_user_extra_case_access(self, user_id: int) -> set[int]:
        if not user_id:
            return set()

        case_ids = self._case_service.get_user_extra_case_access(user_id)
        return set(case_ids or [])
