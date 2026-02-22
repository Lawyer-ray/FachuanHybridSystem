"""Business logic services."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import PermissionDenied


class OrganizationAccessPolicy:
    def ensure_authenticated(self, user: object | None) -> None:
        if not user or not getattr(user, "is_authenticated", False):
            raise PermissionDenied(_("用户未认证"))

    def can_create(self, user: object | None) -> bool:
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and (getattr(user, "is_superuser", False) or getattr(user, "is_admin", False))
        )

    def ensure_can_create(self, user: object | None) -> None:
        if not self.can_create(user):
            raise PermissionDenied(_("权限不足"))

    def can_read_lawyer(self, user: object | None, lawyer: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "law_firm_id", None) == getattr(lawyer, "law_firm_id", None)

    def ensure_can_read_lawyer(self, user: object | None, lawyer: object) -> None:
        if not self.can_read_lawyer(user=user, lawyer=lawyer):
            raise PermissionDenied(_("无权限访问"))

    def can_update_lawyer(self, user: object | None, lawyer: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        if getattr(user, "is_admin", False) and getattr(user, "law_firm_id", None) == getattr(
            lawyer, "law_firm_id", None
        ):
            return True
        return getattr(user, "id", None) == getattr(lawyer, "id", None)

    def ensure_can_update_lawyer(self, user: object | None, lawyer: object) -> None:
        if not self.can_update_lawyer(user=user, lawyer=lawyer):
            raise PermissionDenied(_("无权限更新"))

    def can_delete_lawyer(self, user: object | None, lawyer: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(
            getattr(user, "is_superuser", False)
            or (
                getattr(user, "is_admin", False)
                and getattr(user, "law_firm_id", None) == getattr(lawyer, "law_firm_id", None)
            )
        )

    def ensure_can_delete_lawyer(self, user: object | None, lawyer: object) -> None:
        if not self.can_delete_lawyer(user=user, lawyer=lawyer):
            raise PermissionDenied(_("无权限删除"))

    def can_read_lawfirm(self, user: object | None, lawfirm: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "law_firm_id", None) == getattr(lawfirm, "id", None)

    def ensure_can_read_lawfirm(self, user: object | None, lawfirm: object) -> None:
        if not self.can_read_lawfirm(user=user, lawfirm=lawfirm):
            raise PermissionDenied(_("无权限访问该律所"))

    def can_update_lawfirm(self, user: object | None, lawfirm: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(
            getattr(user, "is_superuser", False)
            or (getattr(user, "is_admin", False) and getattr(user, "law_firm_id", None) == getattr(lawfirm, "id", None))
        )

    def ensure_can_update_lawfirm(self, user: object | None, lawfirm: object) -> None:
        if not self.can_update_lawfirm(user=user, lawfirm=lawfirm):
            raise PermissionDenied(_("无权限更新该律所"))

    def can_delete_lawfirm(self, user: object | None, lawfirm: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_superuser", False))

    def ensure_can_delete_lawfirm(self, user: object | None, lawfirm: object) -> None:
        if not self.can_delete_lawfirm(user=user, lawfirm=lawfirm):
            raise PermissionDenied(_("无权限删除该律所"))

    def can_read_team(self, user: object | None, team: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return getattr(user, "law_firm_id", None) == getattr(team, "law_firm_id", None)

    def ensure_can_read_team(self, user: object | None, team: object) -> None:
        if not self.can_read_team(user=user, team=team):
            raise PermissionDenied(_("无权限访问该团队"))

    def can_update_team(self, user: object | None, team: object) -> bool:
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        return bool(
            getattr(user, "is_admin", False)
            and getattr(user, "law_firm_id", None) == getattr(team, "law_firm_id", None)
        )

    def ensure_can_update_team(self, user: object | None, team: object) -> None:
        if not self.can_update_team(user=user, team=team):
            raise PermissionDenied(_("无权限更新该团队"))

    def can_delete_team(self, user: object | None, team: object) -> bool:
        return self.can_update_team(user=user, team=team)

    def ensure_can_delete_team(self, user: object | None, team: object) -> None:
        if not self.can_delete_team(user=user, team=team):
            raise PermissionDenied(_("无权限删除该团队"))
