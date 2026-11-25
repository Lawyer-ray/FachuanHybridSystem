"""注册审批服务：待审批账号的查询 / 通过 / 拒绝。

背景（2026-11-25）：``AuthService.register`` 会把首位之后的用户创建成
``is_active=False`` 的「待审批」账号，注册响应也承诺「请等待管理员审批」，
但产品里从来没有审批入口——没有待审列表、没有激活 API、Django admin 里
也没有批量启用 action。结果是：注册成功、永远登不上、也没人能开通。

本服务补上这条闭环。审批动作只改 ``is_active`` 与归属律所，**不授予**
``is_admin`` / ``is_superuser``（那是 ``ALLOW_FIRST_USER_SUPERUSER`` 与
超管专属通道的职责，见 ``lawyer/mutation.py`` 的 ``_enforce_privilege_fields``）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import models, transaction

from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.core.security.admin_access import is_admin_user
from apps.organization.models import Lawyer

logger = logging.getLogger("apps.organization.approval")


class LawyerApprovalService:
    """注册审批：只有管理员可以查看 / 通过 / 拒绝待审批账号。"""

    def _ensure_admin(self, user: Any) -> None:
        if not is_admin_user(user):
            raise PermissionDenied(message="无权限审批注册申请", code="PERMISSION_DENIED")

    def _pending_queryset(self, user: Any) -> models.QuerySet[Lawyer]:
        """待审批 queryset：未激活账号，按权限收窄可见范围。"""
        qs = Lawyer.objects.filter(is_active=False).order_by("date_joined", "id")
        if getattr(user, "is_superuser", False):
            return qs
        # 律所管理员：只看「尚未归属律所」的申请，或本所范围内的，避免跨所抢人
        firm_id = getattr(user, "law_firm_id", None)
        if firm_id is None:
            return qs.filter(law_firm_id__isnull=True)
        return qs.filter(models.Q(law_firm_id__isnull=True) | models.Q(law_firm_id=firm_id))

    def list_pending(self, user: Any) -> list[Lawyer]:
        """列出待审批账号。"""
        self._ensure_admin(user)
        return list(self._pending_queryset(user))

    def _get_pending(self, lawyer_id: int, user: Any) -> Lawyer:
        lawyer = self._pending_queryset(user).filter(pk=lawyer_id).first()
        if lawyer is None:
            raise NotFoundError(message="待审批账号不存在或已被处理", code="LAWYER_NOT_FOUND")
        return lawyer

    @transaction.atomic
    def approve(
        self,
        lawyer_id: int,
        user: Any,
        *,
        law_firm_id: int | None = None,
        lawyer_team_ids: list[int] | None = None,
        biz_team_ids: list[int] | None = None,
    ) -> Lawyer:
        """通过审批：激活账号，并补上归属律所（默认继承审批人所在律所）。"""
        self._ensure_admin(user)
        lawyer = self._get_pending(lawyer_id, user)

        target_firm_id = law_firm_id if law_firm_id is not None else getattr(user, "law_firm_id", None)
        if target_firm_id is not None:
            lawyer.law_firm_id = target_firm_id
        lawyer.is_active = True
        lawyer.save(update_fields=["is_active", "law_firm_id"])

        if lawyer_team_ids is not None:
            lawyer.lawyer_teams.set(lawyer_team_ids)
        if biz_team_ids is not None:
            lawyer.biz_teams.set(biz_team_ids)

        logger.info(
            "注册申请已通过 lawyer_id=%s approver_id=%s",
            lawyer.pk,
            getattr(user, "pk", None),
            extra={"lawyer_id": lawyer.pk, "user_id": getattr(user, "pk", None), "action": "approve_lawyer"},
        )
        return lawyer

    @transaction.atomic
    def reject(self, lawyer_id: int, user: Any) -> None:
        """拒绝审批：删除这条待审批注册（释放用户名，便于本人重新注册）。"""
        self._ensure_admin(user)
        lawyer = self._get_pending(lawyer_id, user)
        logger.info(
            "注册申请被拒绝并删除 lawyer_id=%s username=%s approver_id=%s",
            lawyer.pk,
            lawyer.username,
            getattr(user, "pk", None),
            extra={"lawyer_id": lawyer.pk, "user_id": getattr(user, "pk", None), "action": "reject_lawyer"},
        )
        lawyer.delete()
