"""Business logic services."""

from __future__ import annotations

from apps.organization.models import Lawyer, LawFirm, Team


class OrganizationAccessPolicy:
    def can_create(self, user: Lawyer | None) -> bool:
        return bool(user and user.is_authenticated and (user.is_superuser or user.is_admin or user.is_staff))

    def can_read_lawyer(self, user: Lawyer | None, lawyer: Lawyer) -> bool:
        if not user or not user.is_authenticated:
            return False
        return True

    def can_update_lawyer(self, user: Lawyer | None, lawyer: Lawyer) -> bool:
        if not user or not user.is_authenticated:
            return False
        return True

    def can_delete_lawyer(self, user: Lawyer | None, lawyer: Lawyer) -> bool:
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_superuser or user.is_staff or user.is_admin)

    def can_read_lawfirm(self, user: Lawyer | None, lawfirm: LawFirm) -> bool:
        if not user or not user.is_authenticated:
            return False
        return True

    def can_update_lawfirm(self, user: Lawyer | None, lawfirm: LawFirm) -> bool:
        if not user or not user.is_authenticated:
            return False
        return True

    def can_delete_lawfirm(self, user: Lawyer | None, lawfirm: LawFirm) -> bool:
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_superuser)

    def can_read_team(self, user: Lawyer | None, team: Team) -> bool:
        if not user or not user.is_authenticated:
            return False
        return True

    def can_update_team(self, user: Lawyer | None, team: Team) -> bool:
        if not user or not user.is_authenticated:
            return False
        return True

    def can_delete_team(self, user: Lawyer | None, team: Team) -> bool:
        return self.can_update_team(user=user, team=team)
