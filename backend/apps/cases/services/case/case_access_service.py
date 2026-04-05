"""Business logic services."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case, CaseAccessGrant
from apps.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from apps.core.infrastructure import invalidate_user_access_context
from apps.core.interfaces import ICaseService
from apps.core.security import AccessContext, DjangoPermsMixin

from .wiring import get_case_service


class CaseAccessService(DjangoPermsMixin):
    """
    案件访问授权服务

    职责:
    - 授权的 CRUD 操作
    - 权限检查
    - 缓存失效管理
    """

    def __init__(self, case_service: ICaseService | None = None) -> None:
        """
        构造函数,支持依赖注入

            case_service: 案件服务实例,None 时使用 ServiceLocator 获取
        """
        self._case_service = case_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载案件服务"""
        if self._case_service is None:
            self._case_service = get_case_service()
        return self._case_service

    def list_grants(
        self,
        case_id: int | None = None,
        grantee_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        access_ctx: AccessContext | None = None,
    ) -> QuerySet[Case, Case]:
        """
        获取授权列表

            case_id: 案件 ID(可选,用于过滤)
            grantee_id: 被授权用户 ID(可选,用于过滤)
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

            授权查询集
        """
        qs = CaseAccessGrant.objects.all().order_by("-id").select_related("grantee", "case")
        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        if grantee_id is not None:
            qs = qs.filter(grantee_id=grantee_id)
        ctx = access_ctx or AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        if ctx.perm_open_access:
            return qs  # type: ignore[no-any-return]
        self.ensure_authenticated(ctx.user)
        if self.is_admin(ctx.user) or self.is_superuser(ctx.user):
            return qs  # type: ignore[no-any-return]
        user_id = self.get_user_id(ctx.user)
        if grantee_id is not None and grantee_id != user_id:
            raise ForbiddenError(_("无权限查看他人授权记录"))
        return qs.filter(grantee_id=user_id)  # type: ignore[no-any-return]

    def get_grant(
        self,
        grant_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        access_ctx: AccessContext | None = None,
    ) -> CaseAccessGrant:
        """
        获取单个授权

            grant_id: 授权 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

            授权对象

            NotFoundError: 授权不存在
        """
        try:
            grant = CaseAccessGrant.objects.select_related("grantee", "case").get(id=grant_id)
        except CaseAccessGrant.DoesNotExist:
            raise NotFoundError(_("授权 %(id)s 不存在") % {"id": grant_id}) from None
        ctx = access_ctx or AccessContext(user=user, org_access=org_access, perm_open_access=perm_open_access)
        if ctx.perm_open_access:
            return grant
        self.ensure_authenticated(ctx.user)
        if self.is_admin(ctx.user) or self.is_superuser(ctx.user):
            return grant
        if grant.grantee_id != self.get_user_id(ctx.user):
            raise ForbiddenError(_("无权限查看该授权记录"))
        return grant

    def create_grant(self, case_id: int, grantee_id: int, user: Any | None = None) -> CaseAccessGrant:
        """
        创建授权(授予用户案件访问权限)

            case_id: 案件 ID
            grantee_id: 被授权用户 ID
            user: 当前用户

            创建的授权对象

            NotFoundError: 案件不存在
            ConflictError: 授权已存在
        """
        self.ensure_admin(user)
        if not Case.objects.filter(id=case_id).exists():
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id})
        if CaseAccessGrant.objects.filter(case_id=case_id, grantee_id=grantee_id).exists():
            raise ConflictError(_("该用户已有此案件的访问权限"))
        grant = CaseAccessGrant.objects.create(case_id=case_id, grantee_id=grantee_id)
        invalidate_user_access_context(grantee_id)
        return grant

    def update_grant(
        self,
        grant_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        access_ctx: AccessContext | None = None,
    ) -> CaseAccessGrant:
        """
        更新授权

            grant_id: 授权 ID
            data: 更新数据字典
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

            更新后的授权对象

            NotFoundError: 授权不存在
        """
        self.ensure_admin(user)
        grant = self.get_grant(
            grant_id, user=user, org_access=org_access, perm_open_access=perm_open_access, access_ctx=access_ctx
        )
        for key, value in data.items():
            setattr(grant, key, value)
        grant.save()
        invalidate_user_access_context(grant.grantee_id)
        return grant

    def delete_grant(
        self,
        grant_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        access_ctx: AccessContext | None = None,
    ) -> dict[str, bool]:
        """
        删除授权(通过授权 ID 撤销访问权限)

            grant_id: 授权 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

            {"success": True}

            NotFoundError: 授权不存在
        """
        self.ensure_admin(user)
        grant = self.get_grant(
            grant_id, user=user, org_access=org_access, perm_open_access=perm_open_access, access_ctx=access_ctx
        )
        grantee_id = grant.grantee_id
        grant.delete()
        invalidate_user_access_context(grantee_id)
        return {"success": True}

    def get_grants_for_case(self, case_id: int, user: Any | None = None) -> QuerySet[Case, Case]:
        """
        获取案件的所有访问授权

            case_id: 案件 ID
            user: 当前用户

            授权查询集
        """
        self.ensure_admin(user)
        return CaseAccessGrant.objects.filter(case_id=case_id).select_related("grantee")  # type: ignore[no-any-return]

    def get_grants_for_user(self, user_id: int, user: Any | None = None) -> QuerySet[Case, Case]:
        """
        获取用户的所有案件访问授权

            user_id: 用户 ID
            user: 当前用户

            授权查询集
        """
        self.ensure_authenticated(user)
        if not (self.is_admin(user) or self.is_superuser(user)) and self.get_user_id(user) != user_id:
            raise ForbiddenError(_("无权限查看他人授权记录"))
        return CaseAccessGrant.objects.filter(grantee_id=user_id).select_related("case")  # type: ignore[no-any-return]

    def get_accessible_case_ids(self, user_id: int, user: Any | None = None) -> set[int]:
        """
        获取用户可访问的案件 ID 集合

            user_id: 用户 ID
            user: 当前用户

            案件 ID 集合
        """
        self.ensure_authenticated(user)
        if not (self.is_admin(user) or self.is_superuser(user)) and self.get_user_id(user) != user_id:
            raise ForbiddenError(_("无权限查看他人可访问案件"))
        return set(CaseAccessGrant.objects.filter(grantee_id=user_id).values_list("case_id", flat=True))

    def grant_access(self, case_id: int, grantee_id: int, user: Any | None = None) -> CaseAccessGrant:
        """
        授予用户案件访问权限(别名方法,保持向后兼容)

            case_id: 案件 ID
            grantee_id: 被授权用户 ID
            user: 当前用户

            创建的授权对象

            NotFoundError: 案件不存在
            ConflictError: 授权已存在
        """
        return self.create_grant(case_id=case_id, grantee_id=grantee_id, user=user)

    def revoke_access(self, case_id: int, grantee_id: int, user: Any | None = None) -> bool:
        """
        撤销用户案件访问权限

            case_id: 案件 ID
            grantee_id: 被撤销用户 ID
            user: 当前用户

            是否成功

            NotFoundError: 授权不存在
        """
        self.ensure_admin(user)
        try:
            grant = CaseAccessGrant.objects.get(case_id=case_id, grantee_id=grantee_id)
        except CaseAccessGrant.DoesNotExist:
            raise NotFoundError(_("授权记录不存在")) from None
        grant.delete()
        invalidate_user_access_context(grantee_id)
        return True

    def revoke_access_by_id(self, grant_id: int, user: Any | None = None) -> bool:
        """
        通过授权 ID 撤销访问权限(别名方法,保持向后兼容)

            grant_id: 授权 ID
            user: 当前用户

            是否成功

            NotFoundError: 授权不存在
        """
        self.ensure_admin(user)
        self.delete_grant(grant_id, user=user)
        return True

    def batch_grant_access(
        self, case_id: int, grantee_ids: list[int], user: Any | None = None
    ) -> list[CaseAccessGrant]:
        """
        批量授予案件访问权限

            case_id: 案件 ID
            grantee_ids: 被授权用户 ID 列表
            user: 当前用户

            创建的授权对象列表

            NotFoundError: 案件不存在
        """
        self.ensure_admin(user)
        if not Case.objects.filter(id=case_id).exists():
            raise NotFoundError(_("案件 %(id)s 不存在") % {"id": case_id})
        existing = set(
            CaseAccessGrant.objects.filter(case_id=case_id, grantee_id__in=grantee_ids).values_list(
                "grantee_id", flat=True
            )
        )
        grants = []
        for grantee_id in grantee_ids:
            if grantee_id not in existing:
                grants.append(CaseAccessGrant(case_id=case_id, grantee_id=grantee_id))
        created = CaseAccessGrant.objects.bulk_create(grants)
        for grantee_id in grantee_ids:
            if grantee_id not in existing:
                invalidate_user_access_context(grantee_id)
        return created  # type: ignore[no-any-return]
