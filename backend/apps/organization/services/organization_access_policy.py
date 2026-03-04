"""Organization access policy."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ForbiddenError
from apps.organization.models import LawFirm, Lawyer, Team


class OrganizationAccessPolicy:
    # ── helpers ──────────────────────────────────────────────────────────────

    def ensure_authenticated(self, user: Any) -> None:
        if not user or not getattr(user, "is_authenticated", False):
            raise ForbiddenError

    def _ensure(self, allowed: bool) -> None:
        if not allowed:
            raise ForbiddenError

    # ── create ────────────────────────────────────────────────────────────────

    def can_create(self, user: Any) -> bool:
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and (getattr(user, "is_superuser", False) or getattr(user, "is_admin", False))
        )

    def ensure_can_create(self, user: Any) -> None:
        self._ensure(self.can_create(user))

    # ── lawyer ────────────────────────────────────────────────────────────────

    def can_read_lawyer(self, user: Any, lawyer: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "law_firm_id", None) == getattr(lawyer, "law_firm_id", None)

    def ensure_can_read_lawyer(self, user: Any, lawyer: Any) -> None:
        self._ensure(self.can_read_lawyer(user, lawyer))

    def can_update_lawyer(self, user: Any, lawyer: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        if getattr(user, "id", None) == getattr(lawyer, "id", None):
            return True
        return (
            getattr(user, "is_admin", False)
            and getattr(user, "law_firm_id", None) == getattr(lawyer, "law_firm_id", None)
        )

    def ensure_can_update_lawyer(self, user: Any, lawyer: Any) -> None:
        self._ensure(self.can_update_lawyer(user, lawyer))

    def can_delete_lawyer(self, user: Any, lawyer: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            getattr(user, "is_admin", False)
            and getattr(user, "law_firm_id", None) == getattr(lawyer, "law_firm_id", None)
        )

    def ensure_can_delete_lawyer(self, user: Any, lawyer: Any) -> None:
        self._ensure(self.can_delete_lawyer(user, lawyer))

    # ── lawfirm ───────────────────────────────────────────────────────────────

    def can_read_lawfirm(self, user: Any, lawfirm: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "law_firm_id", None) == getattr(lawfirm, "id", None)

    def ensure_can_read_lawfirm(self, user: Any, lawfirm: Any) -> None:
        self._ensure(self.can_read_lawfirm(user, lawfirm))

    def can_update_lawfirm(self, user: Any, lawfirm: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            getattr(user, "is_admin", False)
            and getattr(user, "law_firm_id", None) == getattr(lawfirm, "id", None)
        )

    def ensure_can_update_lawfirm(self, user: Any, lawfirm: Any) -> None:
        self._ensure(self.can_update_lawfirm(user, lawfirm))

    def can_delete_lawfirm(self, user: Any, lawfirm: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superuser", False))

    def ensure_can_delete_lawfirm(self, user: Any, lawfirm: Any) -> None:
        self._ensure(self.can_delete_lawfirm(user, lawfirm))

    # ── team ──────────────────────────────────────────────────────────────────

    def can_read_team(self, user: Any, team: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "law_firm_id", None) == getattr(team, "law_firm_id", None)

    def ensure_can_read_team(self, user: Any, team: Any) -> None:
        self._ensure(self.can_read_team(user, team))

    def can_update_team(self, user: Any, team: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            getattr(user, "is_admin", False)
            and getattr(user, "law_firm_id", None) == getattr(team, "law_firm_id", None)
        )

    def ensure_can_update_team(self, user: Any, team: Any) -> None:
        self._ensure(self.can_update_team(user, team))

    def can_delete_team(self, user: Any, team: Any) -> bool:
        return self.can_update_team(user=user, team=team)

    def ensure_can_delete_team(self, user: Any, team: Any) -> None:
        self._ensure(self.can_delete_team(user, team))
