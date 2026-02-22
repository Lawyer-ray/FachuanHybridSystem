"""
团队服务层
处理团队相关的业务逻辑
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
import logging
from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy

from apps.organization.models import LawFirm, Lawyer, Team, TeamType

logger = logging.getLogger("apps.organization")


class TeamService:
    """
    团队服务

    职责：
    1. 封装团队相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 验证业务规则
    """

    def __init__(self) -> None:
        """初始化服务"""
        self._access_policy = OrganizationAccessPolicy()

    def list_teams(
        self, law_firm_id: int | None = None, team_type: str | None = None, user: Lawyer | None = None
    ) -> "QuerySet[Team, Team]":
        """
        列表查询团队

        Args:
            law_firm_id: 律所 ID 过滤
            team_type: 团队类型过滤
            user: 当前用户

        Returns:
            团队查询集
        """
        qs = Team.objects.select_related("law_firm").all()

        # 权限过滤：非超级用户只能看到自己律所的团队
        if user and not user.is_superuser:
            qs = qs.filter(law_firm_id=user.law_firm_id)

        # 业务过滤
        if law_firm_id is not None:
            qs = qs.filter(law_firm_id=law_firm_id)
        if team_type is not None:
            qs = qs.filter(team_type=team_type)

        return qs

    def get_team(self, team_id: int, user: Lawyer | None = None) -> Team:
        """
        获取团队详情

        Args:
            team_id: 团队 ID
            user: 当前用户

        Returns:
            团队对象

        Raises:
            NotFoundError: 团队不存在
            PermissionDenied: 无权限访问
        """
        team = Team.objects.select_related("law_firm").filter(id=team_id).first()

        if not team:
            raise NotFoundError(message=_("团队不存在"), code="TEAM_NOT_FOUND")

        # 权限检查（user is None 时为公开接口，允许访问）
        if user is not None and not self._access_policy.can_read_team(user, team):
            raise PermissionDenied(message=_("无权限访问该团队"), code="PERMISSION_DENIED")

        return cast(Team, team)

    @transaction.atomic
    def create_team(self, data: Any, user: Lawyer | None = None) -> Team:
        """
        创建团队

        Args:
            data: 创建数据
            user: 当前用户

        Returns:
            创建的团队对象

        Raises:
            ValidationException: 团队类型无效
            NotFoundError: 律所不存在
            PermissionDenied: 权限不足
        """
        # 1. 权限检查
        if not self._access_policy.can_create(user):
            logger.warning(
                f"用户 {getattr(user, 'id', None)} 尝试创建团队但权限不足",
                extra={"user_id": getattr(user, "id", None), "action": "create_team"},
            )
            raise PermissionDenied(message=_("无权限创建团队"), code="PERMISSION_DENIED")

        # 2. 验证团队类型
        self._validate_team_type(data.team_type)

        # 3. 验证律所存在
        law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
        if not law_firm:
            raise NotFoundError(message=_("律所不存在"), code="LAWFIRM_NOT_FOUND")

        # 4. 创建团队
        team = Team.objects.create(name=data.name, team_type=data.team_type, law_firm=law_firm)

        # 5. 记录日志
        logger.info(
            "团队创建成功", extra={"team_id": team.id, "user_id": getattr(user, "id", None), "action": "create_team"}
        )

        return team

    @transaction.atomic
    def update_team(self, team_id: int, data: Any, user: Lawyer | None = None) -> Team:
        """
        更新团队

        Args:
            team_id: 团队 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的团队对象

        Raises:
            NotFoundError: 团队或律所不存在
            ValidationException: 团队类型无效
            PermissionDenied: 权限不足
        """
        # 1. 获取团队
        team = self.get_team(team_id, user)

        # 2. 权限检查
        if not self._access_policy.can_update_team(user, team):
            logger.warning(
                f"用户 {getattr(user, 'id', None)} 尝试更新团队 {team_id} 但权限不足",
                extra={"user_id": getattr(user, "id", None), "team_id": team_id, "action": "update_team"},
            )
            raise PermissionDenied(message=_("无权限更新该团队"), code="PERMISSION_DENIED")

        # 3. 验证团队类型
        self._validate_team_type(data.team_type)

        # 4. 验证律所存在
        law_firm = LawFirm.objects.filter(id=data.law_firm_id).first()
        if not law_firm:
            raise NotFoundError(message=_("律所不存在"), code="LAWFIRM_NOT_FOUND")

        # 5. 更新团队
        team.name = data.name
        team.team_type = data.team_type
        team.law_firm = law_firm
        team.save()

        # 6. 记录日志
        logger.info(
            "团队更新成功", extra={"team_id": team.id, "user_id": getattr(user, "id", None), "action": "update_team"}
        )

        return team

    @transaction.atomic
    def delete_team(self, team_id: int, user: Lawyer | None = None) -> None:
        """
        删除团队

        Args:
            team_id: 团队 ID
            user: 当前用户

        Raises:
            NotFoundError: 团队不存在
            PermissionDenied: 权限不足
        """
        # 1. 获取团队
        team = self.get_team(team_id, user)

        # 2. 权限检查
        if not self._access_policy.can_delete_team(user, team):
            logger.warning(
                f"用户 {getattr(user, 'id', None)} 尝试删除团队 {team_id} 但权限不足",
                extra={"user_id": getattr(user, "id", None), "team_id": team_id, "action": "delete_team"},
            )
            raise PermissionDenied(message=_("无权限删除该团队"), code="PERMISSION_DENIED")

        # 3. 删除团队
        team.delete()

        # 4. 记录日志
        logger.info(
            "团队删除成功", extra={"team_id": team_id, "user_id": getattr(user, "id", None), "action": "delete_team"}
        )

    # ========== 私有方法（业务逻辑封装） ==========

    def _validate_team_type(self, team_type: str) -> None:
        """
        验证团队类型

        Args:
            team_type: 团队类型

        Raises:
            ValidationException: 团队类型无效
        """
        valid_types = [TeamType.LAWYER, TeamType.BIZ]
        if team_type not in valid_types:
            raise ValidationException(
                message=_("非法团队类型"),
                code="INVALID_TEAM_TYPE",
                errors={"team_type": f"团队类型必须是 {valid_types} 之一"},
            )
