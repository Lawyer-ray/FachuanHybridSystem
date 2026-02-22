"""
团队服务层
处理团队相关的业务逻辑
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.organization.dtos import TeamUpsertDTO
from apps.organization.models import LawFirm, Lawyer, Team, TeamType
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy

logger = logging.getLogger("apps.organization")


class TeamService:
    def __init__(self) -> None:
        self._access_policy = OrganizationAccessPolicy()

    def list_teams(
        self, law_firm_id: int | None = None, team_type: str | None = None, user: Lawyer | None = None
    ) -> "QuerySet[Team, Team]":
        qs = Team.objects.select_related("law_firm").all()

        # 权限过滤：非超级用户只能看到自己律所的团队
        if user and not user.is_superuser:
            if user.law_firm_id is not None:
                qs = qs.filter(law_firm_id=user.law_firm_id)
            else:
                qs = qs.none()

        if law_firm_id is not None:
            qs = qs.filter(law_firm_id=law_firm_id)
        if team_type is not None:
            qs = qs.filter(team_type=team_type)

        return qs

    def get_team(self, team_id: int, user: Lawyer | None = None) -> Team:
        """
        Raises:
            NotFoundError: 团队不存在
            PermissionDenied: 无权限访问
        """
        team = Team.objects.select_related("law_firm").filter(id=team_id).first()

        if not team:
            raise NotFoundError(message=_("团队不存在"), code="TEAM_NOT_FOUND")

        if user is not None and not self._access_policy.can_read_team(user, team):
            raise PermissionDenied(message=_("无权限访问该团队"), code="PERMISSION_DENIED")

        return team

    @transaction.atomic
    def create_team(self, data: TeamUpsertDTO, user: Lawyer | None = None) -> Team:
        """
        Raises:
            ValidationException: 团队类型无效
            NotFoundError: 律所不存在
            PermissionDenied: 权限不足
        """
        if not self._access_policy.can_create(user):
            logger.warning(
                "用户 %s 尝试创建团队但权限不足",
                user.id if user else None,
                extra={"user_id": user.id if user else None, "action": "create_team"},
            )
            raise PermissionDenied(message=_("无权限创建团队"), code="PERMISSION_DENIED")

        self._validate_team_type(data.team_type)

        law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
        if not law_firm:
            raise NotFoundError(message=_("律所不存在"), code="LAWFIRM_NOT_FOUND")

        team = Team.objects.create(name=data.name, team_type=data.team_type, law_firm=law_firm)

        logger.info(
            "团队创建成功", extra={"team_id": team.id, "user_id": user.id if user else None, "action": "create_team"}
        )

        return team

    @transaction.atomic
    def update_team(self, team_id: int, data: TeamUpsertDTO, user: Lawyer | None = None) -> Team:
        """
        Raises:
            NotFoundError: 团队或律所不存在
            ValidationException: 团队类型无效
            PermissionDenied: 权限不足
        """
        team = self.get_team(team_id, user)

        if not self._access_policy.can_update_team(user, team):
            logger.warning(
                "用户 %s 尝试更新团队 %s 但权限不足",
                user.id if user else None,
                team_id,
                extra={"user_id": user.id if user else None, "team_id": team_id, "action": "update_team"},
            )
            raise PermissionDenied(message=_("无权限更新该团队"), code="PERMISSION_DENIED")

        self._validate_team_type(data.team_type)

        law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
        if not law_firm:
            raise NotFoundError(message=_("律所不存在"), code="LAWFIRM_NOT_FOUND")

        team.name = data.name
        team.team_type = data.team_type
        team.law_firm = law_firm
        team.save(update_fields=["name", "team_type", "law_firm_id"])

        logger.info(
            "团队更新成功", extra={"team_id": team.id, "user_id": user.id if user else None, "action": "update_team"}
        )

        return team

    @transaction.atomic
    def delete_team(self, team_id: int, user: Lawyer | None = None) -> None:
        """
        Raises:
            NotFoundError: 团队不存在
            PermissionDenied: 权限不足
        """
        team = self.get_team(team_id, user)

        if not self._access_policy.can_delete_team(user, team):
            logger.warning(
                "用户 %s 尝试删除团队 %s 但权限不足",
                user.id if user else None,
                team_id,
                extra={"user_id": user.id if user else None, "team_id": team_id, "action": "delete_team"},
            )
            raise PermissionDenied(message=_("无权限删除该团队"), code="PERMISSION_DENIED")

        team.delete()

        logger.info(
            "团队删除成功", extra={"team_id": team_id, "user_id": user.id if user else None, "action": "delete_team"}
        )

    def _validate_team_type(self, team_type: str) -> None:
        if team_type not in TeamType.values:
            raise ValidationException(
                message=_("非法团队类型"),
                code="INVALID_TEAM_TYPE",
                errors={"team_type": str(_("团队类型必须是 %(valid_types)s 之一")) % {"valid_types": TeamType.values}},
            )
