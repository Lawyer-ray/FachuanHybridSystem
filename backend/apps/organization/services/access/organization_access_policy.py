"""Organization access policy."""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ForbiddenError
from apps.core.security.admin_access import is_admin_user  # 解耦（2026-10-19）：管理员判定收敛 core
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
        # 解耦（2026-10-19）：管理员判定收敛到 core.security.admin_access.is_admin_user
        return bool(user and getattr(user, "is_authenticated", False) and is_admin_user(user))

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

    # ── credential（账号凭证）────────────────────────────────────────────
    #
    # 凭证是外部系统（一张网/威科/OA 等）的个人账号口令，敏感度高于普通律师
    # 资料，因此可见范围比 can_read_lawyer（同所）更窄：仅本人 + 同律师团队 +
    # 管理员。无团队的律师只能看到自己的凭证。
    #
    # 注意：不要用 can_read_lawyer 替代本方法——那会把可见面扩大到全所。

    def can_read_credential(self, user: Any, credential_owner: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if is_admin_user(user):
            return True
        if getattr(user, "id", None) == getattr(credential_owner, "id", None):
            return True
        # 同律师团队（lawyer_teams）内互相可见；无团队时 law 侧返回空集，即只有本人
        return self._is_same_lawyer_team(user, credential_owner)

    def _is_same_lawyer_team(self, user: Any, other: Any) -> bool:
        # getattr 容错：调用方可能传入不可用的轻量对象（如测试替身），
        # 无 lawyer_teams 时视为无团队，不回退到放宽口径。
        user_teams = getattr(user, "lawyer_teams", None)
        other_teams = getattr(other, "lawyer_teams", None)
        if user_teams is None or other_teams is None:
            return False
        user_team_ids = set(user_teams.values_list("id", flat=True))
        if not user_team_ids:
            return False
        other_team_ids = set(other_teams.values_list("id", flat=True))
        return bool(user_team_ids & other_team_ids)

    def ensure_can_read_credential(self, user: Any, credential_owner: Any) -> None:
        self._ensure(self.can_read_credential(user, credential_owner))

    def can_update_lawyer(self, user: Any, lawyer: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        if getattr(user, "id", None) == getattr(lawyer, "id", None):
            return True
        return getattr(user, "is_admin", False) and getattr(user, "law_firm_id", None) == getattr(
            lawyer, "law_firm_id", None
        )

    def ensure_can_update_lawyer(self, user: Any, lawyer: Any) -> None:
        self._ensure(self.can_update_lawyer(user, lawyer))

    def can_delete_lawyer(self, user: Any, lawyer: Any) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "is_admin", False) and getattr(user, "law_firm_id", None) == getattr(
            lawyer, "law_firm_id", None
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
        return getattr(user, "is_admin", False) and getattr(user, "law_firm_id", None) == getattr(lawfirm, "id", None)

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
        return getattr(user, "is_admin", False) and getattr(user, "law_firm_id", None) == getattr(
            team, "law_firm_id", None
        )

    def ensure_can_update_team(self, user: Any, team: Any) -> None:
        self._ensure(self.can_update_team(user, team))

    def can_delete_team(self, user: Any, team: Any) -> bool:
        return self.can_update_team(user=user, team=team)

    def ensure_can_delete_team(self, user: Any, team: Any) -> None:
        self._ensure(self.can_delete_team(user, team))
