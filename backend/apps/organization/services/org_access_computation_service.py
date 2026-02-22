"""Business logic services."""

from __future__ import annotations

from apps.core.interfaces import ICaseService
from apps.organization.models import Lawyer


class OrgAccessComputationService:
    def __init__(self, *, case_service: ICaseService) -> None:
        self._case_service = case_service

    def compute(self, user: Lawyer) -> dict[str, object]:
        lawyers: set[int] = set()
        team_ids: set[int] = set()

        teams = user.lawyer_teams.prefetch_related("lawyers").all()
        for team in teams:
            team_ids.add(team.id)
            for member in team.lawyers.all():
                lawyers.add(member.id)

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
