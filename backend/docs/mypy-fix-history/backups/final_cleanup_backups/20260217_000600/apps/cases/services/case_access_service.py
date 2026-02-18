"""
案件访问授权服务层
处理案件访问权限相关的业务逻辑
符合四层架构规范：业务逻辑、权限检查、依赖注入
"""
from typing import List, Optional, Set, Dict, Any
from django.db.models import QuerySet

from apps.core.exceptions import NotFoundError, ConflictError
from apps.core.interfaces import ICaseService, ServiceLocator
from apps.organization.middleware import invalidate_user_org_cache
from ..models import Case, CaseAccessGrant


class CaseAccessService:
    """
    案件访问授权服务

    职责：
    - 授权的 CRUD 操作
    - 权限检查
    - 缓存失效管理
    """

    def __init__(self, case_service: Optional[ICaseService] = None):
        """
        构造函数，支持依赖注入

        Args:
            case_service: 案件服务实例，None 时使用 ServiceLocator 获取
        """
        self._case_service = case_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载案件服务"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    def list_grants(
        self,
        case_id: Optional[int] = None,
        grantee_id: Optional[int] = None,
        user=None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> QuerySet:
        """
        获取授权列表

        Args:
            case_id: 案件 ID（可选，用于过滤）
            grantee_id: 被授权用户 ID（可选，用于过滤）
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

        Returns:
            授权查询集
        """
        qs = CaseAccessGrant.objects.all().order_by("-id").select_related("grantee", "case")

        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        if grantee_id is not None:
            qs = qs.filter(grantee_id=grantee_id)

        # 开放访问权限，返回全部
        if perm_open_access:
            return qs

        # 权限过滤：管理员可以看到全部
        if user and getattr(user, "is_admin", False):
            return qs

        return qs

    def get_grant(
        self,
        grant_id: int,
        user=None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> CaseAccessGrant:
        """
        获取单个授权

        Args:
            grant_id: 授权 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

        Returns:
            授权对象

        Raises:
            NotFoundError: 授权不存在
        """
        try:
            return CaseAccessGrant.objects.select_related("grantee", "case").get(id=grant_id)
        except CaseAccessGrant.DoesNotExist:
            raise NotFoundError(f"授权 {grant_id} 不存在")

    def create_grant(
        self,
        case_id: int,
        grantee_id: int,
        user=None,
    ) -> CaseAccessGrant:
        """
        创建授权（授予用户案件访问权限）

        Args:
            case_id: 案件 ID
            grantee_id: 被授权用户 ID
            user: 当前用户

        Returns:
            创建的授权对象

        Raises:
            NotFoundError: 案件不存在
            ConflictError: 授权已存在
        """
        # 验证案件存在
        if not Case.objects.filter(id=case_id).exists():
            raise NotFoundError(f"案件 {case_id} 不存在")

        # 检查是否已授权
        if CaseAccessGrant.objects.filter(case_id=case_id, grantee_id=grantee_id).exists():
            raise ConflictError("该用户已有此案件的访问权限")

        grant = CaseAccessGrant.objects.create(
            case_id=case_id,
            grantee_id=grantee_id,
        )

        # 使缓存失效
        invalidate_user_org_cache(grantee_id)

        return grant

    def update_grant(
        self,
        grant_id: int,
        data: Dict[str, Any],
        user=None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> CaseAccessGrant:
        """
        更新授权

        Args:
            grant_id: 授权 ID
            data: 更新数据字典
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

        Returns:
            更新后的授权对象

        Raises:
            NotFoundError: 授权不存在
        """
        grant = self.get_grant(grant_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

        for key, value in data.items():
            setattr(grant, key, value)
        grant.save()

        # 使缓存失效
        invalidate_user_org_cache(grant.grantee_id)

        return grant

    def delete_grant(
        self,
        grant_id: int,
        user=None,
        org_access: Optional[Dict[str, Any]] = None,
        perm_open_access: bool = False,
    ) -> Dict[str, bool]:
        """
        删除授权（通过授权 ID 撤销访问权限）

        Args:
            grant_id: 授权 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否开放访问权限

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 授权不存在
        """
        grant = self.get_grant(grant_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        grantee_id = grant.grantee_id
        grant.delete()

        # 使缓存失效
        invalidate_user_org_cache(grantee_id)

        return {"success": True}

    def get_grants_for_case(self, case_id: int, user=None) -> QuerySet:
        """
        获取案件的所有访问授权

        Args:
            case_id: 案件 ID
            user: 当前用户

        Returns:
            授权查询集
        """
        return CaseAccessGrant.objects.filter(case_id=case_id).select_related("grantee")

    def get_grants_for_user(self, user_id: int, user=None) -> QuerySet:
        """
        获取用户的所有案件访问授权

        Args:
            user_id: 用户 ID
            user: 当前用户

        Returns:
            授权查询集
        """
        return CaseAccessGrant.objects.filter(grantee_id=user_id).select_related("case")

    def get_accessible_case_ids(self, user_id: int, user=None) -> Set[int]:
        """
        获取用户可访问的案件 ID 集合

        Args:
            user_id: 用户 ID
            user: 当前用户

        Returns:
            案件 ID 集合
        """
        return set(
            CaseAccessGrant.objects
            .filter(grantee_id=user_id)
            .values_list("case_id", flat=True)
        )

    def grant_access(self, case_id: int, grantee_id: int, user=None) -> CaseAccessGrant:
        """
        授予用户案件访问权限（别名方法，保持向后兼容）

        Args:
            case_id: 案件 ID
            grantee_id: 被授权用户 ID
            user: 当前用户

        Returns:
            创建的授权对象

        Raises:
            NotFoundError: 案件不存在
            ConflictError: 授权已存在
        """
        return self.create_grant(case_id=case_id, grantee_id=grantee_id, user=user)

    def revoke_access(self, case_id: int, grantee_id: int, user=None) -> bool:
        """
        撤销用户案件访问权限

        Args:
            case_id: 案件 ID
            grantee_id: 被撤销用户 ID
            user: 当前用户

        Returns:
            是否成功

        Raises:
            NotFoundError: 授权不存在
        """
        try:
            grant = CaseAccessGrant.objects.get(case_id=case_id, grantee_id=grantee_id)
        except CaseAccessGrant.DoesNotExist:
            raise NotFoundError("授权记录不存在")

        grant.delete()

        # 使缓存失效
        invalidate_user_org_cache(grantee_id)

        return True

    def revoke_access_by_id(self, grant_id: int, user=None) -> bool:
        """
        通过授权 ID 撤销访问权限（别名方法，保持向后兼容）

        Args:
            grant_id: 授权 ID
            user: 当前用户

        Returns:
            是否成功

        Raises:
            NotFoundError: 授权不存在
        """
        self.delete_grant(grant_id, user=user)
        return True

    def batch_grant_access(
        self,
        case_id: int,
        grantee_ids: List[int],
        user=None,
    ) -> List[CaseAccessGrant]:
        """
        批量授予案件访问权限

        Args:
            case_id: 案件 ID
            grantee_ids: 被授权用户 ID 列表
            user: 当前用户

        Returns:
            创建的授权对象列表

        Raises:
            NotFoundError: 案件不存在
        """
        # 验证案件存在
        if not Case.objects.filter(id=case_id).exists():
            raise NotFoundError(f"案件 {case_id} 不存在")

        # 获取已存在的授权
        existing = set(
            CaseAccessGrant.objects
            .filter(case_id=case_id, grantee_id__in=grantee_ids)
            .values_list("grantee_id", flat=True)
        )

        # 创建新授权
        grants = []
        for grantee_id in grantee_ids:
            if grantee_id not in existing:
                grants.append(CaseAccessGrant(case_id=case_id, grantee_id=grantee_id))

        created = CaseAccessGrant.objects.bulk_create(grants)

        # 使缓存失效
        for grantee_id in grantee_ids:
            if grantee_id not in existing:
                invalidate_user_org_cache(grantee_id)

        return created
