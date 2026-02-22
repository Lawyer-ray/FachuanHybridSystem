"""
账号凭证服务层
处理账号凭证相关的业务逻辑
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
import logging
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.core.exceptions import NotFoundError, PermissionDenied

from apps.organization.models import AccountCredential, Lawyer

logger = logging.getLogger("apps.organization")


class AccountCredentialService:
    """
    账号凭证服务

    职责：
    1. 封装账号凭证相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    """

    def __init__(self) -> None:
        """初始化服务"""
        from apps.organization.services.organization_access_policy import OrganizationAccessPolicy

        self._access_policy = OrganizationAccessPolicy()

    def _get_base_queryset(self) -> "QuerySet[AccountCredential, AccountCredential]":
        """获取带预加载的基础查询集"""
        return AccountCredential.objects.select_related("lawyer", "lawyer__law_firm")

    def list_credentials(
        self,
        lawyer_id: int | None = None,
        lawyer_name: str | None = None,
        user: Any = None,
    ) -> "QuerySet[AccountCredential, AccountCredential]":
        """
        获取凭证列表

        Args:
            lawyer_id: 按律师 ID 过滤
            lawyer_name: 按律师姓名过滤（支持模糊匹配 real_name 或 username）
            user: 当前用户

        Returns:
            凭证查询集（根据用户权限过滤）
        """
        qs = self._get_base_queryset()

        # 权限过滤：非超级用户只能看到同一律所的凭证
        if not getattr(user, "is_superuser", False):
            user_law_firm_id = getattr(user, "law_firm_id", None) if user else None
            if user_law_firm_id is not None:
                qs = qs.filter(lawyer__law_firm_id=user_law_firm_id)
            else:
                # 用户没有关联律所，返回空查询集
                qs = qs.none()

        if lawyer_id is not None:
            qs = qs.filter(lawyer_id=lawyer_id)

        if lawyer_name:
            # 支持按 real_name 或 username 模糊匹配
            qs = qs.filter(Q(lawyer__real_name__icontains=lawyer_name) | Q(lawyer__username__icontains=lawyer_name))

        return qs

    def get_credential(self, credential_id: int, user: Any = None) -> AccountCredential:
        """
        获取单个凭证

        Args:
            credential_id: 凭证 ID
            user: 当前用户

        Returns:
            凭证对象

        Raises:
            NotFoundError: 凭证不存在
            PermissionDenied: 无权限访问该凭证
        """
        credential = self._get_base_queryset().filter(id=credential_id).first()

        if not credential:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")

        # 权限检查：复用 OrganizationAccessPolicy 的律师读取权限
        if not self._access_policy.can_read_lawyer(user=user, lawyer=credential.lawyer):
            raise PermissionDenied(message=_("无权限访问该凭证"), code="CREDENTIAL_ACCESS_DENIED")

        return credential

    @transaction.atomic
    def create_credential(
        self,
        lawyer_id: int,
        site_name: str,
        account: str,
        password: str,
        url: str | None = None,
        user: Any = None,
    ) -> AccountCredential:
        """
        创建凭证

        Args:
            lawyer_id: 律师 ID
            site_name: 网站名称
            account: 账号
            password: 密码
            url: URL
            user: 当前用户

        Returns:
            创建的凭证对象

        Raises:
            NotFoundError: 律师不存在
            PermissionDenied: 无权限为该律师创建凭证
        """
        # 验证律师存在
        lawyer = Lawyer.objects.select_related("law_firm").filter(id=lawyer_id).first()
        if not lawyer:
            raise NotFoundError(message=_("律师不存在"), code="LAWYER_NOT_FOUND")

        # 权限检查：验证用户是否有权限为该律师创建凭证
        if not self._access_policy.can_read_lawyer(user=user, lawyer=lawyer):
            raise PermissionDenied(message=_("无权限为该律师创建凭证"), code="CREDENTIAL_CREATE_DENIED")

        credential = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name=site_name,
            url=url or "",
            account=account,
            password=password,
        )

        logger.info(
            "凭证创建成功",
            extra={
                "credential_id": credential.id,
                "lawyer_id": lawyer_id,
                "site_name": site_name,
                "action": "create_credential",
            },
        )

        return credential

    _UPDATABLE_FIELDS: frozenset[str] = frozenset({"site_name", "url", "account", "password"})

    @transaction.atomic
    def update_credential(
        self,
        credential_id: int,
        data: dict[str, Any],
        user: Any = None,
    ) -> AccountCredential:
        """
        更新凭证

        Args:
            credential_id: 凭证 ID
            data: 更新数据（仅允许 site_name/url/account/password）
            user: 当前用户

        Returns:
            更新后的凭证对象

        Raises:
            NotFoundError: 凭证不存在
            PermissionDenied: 无权限修改该凭证
        """
        # get_credential 已包含权限检查
        credential = self.get_credential(credential_id, user)

        for key, value in data.items():
            if key in self._UPDATABLE_FIELDS:
                setattr(credential, key, value)

        credential.save()

        logger.info("凭证更新成功", extra={"credential_id": credential_id, "action": "update_credential"})

        return credential

    @transaction.atomic
    def delete_credential(self, credential_id: int, user: Any = None) -> None:
        """
        删除凭证

        Args:
            credential_id: 凭证 ID
            user: 当前用户

        Raises:
            NotFoundError: 凭证不存在
            PermissionDenied: 无权限删除该凭证
        """
        # get_credential 已包含权限检查
        credential = self.get_credential(credential_id, user)
        credential.delete()

        logger.info("凭证删除成功", extra={"credential_id": credential_id, "action": "delete_credential"})

    def _get_credential_internal(self, credential_id: int) -> AccountCredential:
        """
        内部方法：获取凭证，无权限检查

        供内部方法和 Adapter 调用

        Args:
            credential_id: 凭证 ID

        Returns:
            凭证对象

        Raises:
            NotFoundError: 凭证不存在
        """
        credential = self._get_base_queryset().filter(id=credential_id).first()
        if not credential:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")
        return credential

    @transaction.atomic
    def update_login_success(self, credential_id: int) -> None:
        """
        更新登录成功统计（使用 F() 表达式避免竞态条件）

        Args:
            credential_id: 凭证 ID
        """
        from django.db.models import F
        from django.utils import timezone

        updated = AccountCredential.objects.filter(id=credential_id).update(
            login_success_count=F("login_success_count") + 1,
            last_login_success_at=timezone.now(),
        )
        if not updated:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")

        logger.info(
            "登录成功统计已更新",
            extra={"credential_id": credential_id, "action": "update_login_success"},
        )

    @transaction.atomic
    def update_login_failure(self, credential_id: int) -> None:
        """
        更新登录失败统计（使用 F() 表达式避免竞态条件）

        Args:
            credential_id: 凭证 ID
        """
        from django.db.models import F

        updated = AccountCredential.objects.filter(id=credential_id).update(
            login_failure_count=F("login_failure_count") + 1,
        )
        if not updated:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")

        logger.info(
            "登录失败统计已更新",
            extra={"credential_id": credential_id, "action": "update_login_failure"},
        )

    def batch_mark_preferred(self, credential_ids: list[int]) -> int:
        """
        批量标记凭证为优先

        Args:
            credential_ids: 凭证 ID 列表

        Returns:
            更新的记录数
        """
        updated: int = AccountCredential.objects.filter(
            id__in=credential_ids,
        ).update(is_preferred=True)
        return updated

    def batch_unmark_preferred(self, credential_ids: list[int]) -> int:
        """
        批量取消凭证优先标记

        Args:
            credential_ids: 凭证 ID 列表

        Returns:
            更新的记录数
        """
        updated: int = AccountCredential.objects.filter(
            id__in=credential_ids,
        ).update(is_preferred=False)
        return updated

    def get_credential_by_id(self, credential_id: int) -> AccountCredential | None:
        """
        按 ID 获取凭证（无权限检查，内部使用）

        Args:
            credential_id: 凭证 ID

        Returns:
            凭证对象或 None
        """
        credential: AccountCredential | None = (
            self._get_base_queryset().filter(id=credential_id).first()
        )
        return credential

    def filter_by_ids_and_site(
        self,
        credential_ids: list[int],
        site_name: str,
    ) -> "QuerySet[AccountCredential, AccountCredential]":
        """
        按 ID 列表和站点名称过滤凭证

        Args:
            credential_ids: 凭证 ID 列表
            site_name: 站点名称

        Returns:
            过滤后的凭证查询集
        """
        return self._get_base_queryset().filter(
            id__in=credential_ids,
            site_name=site_name,
        )

    SITE_URL_MAPPING: dict[str, str] = {
        "court_zxfw": "zxfw.court.gov.cn",
    }

    def get_credentials_by_site(self, site_name: str) -> "QuerySet[AccountCredential, AccountCredential]":
        """
        根据站点名称获取凭证（无权限检查，内部使用）

        支持精确匹配 site_name 和 URL 包含匹配。

        Args:
            site_name: 站点名称或URL关键字

        Returns:
            凭证查询集
        """
        url_keyword = self.SITE_URL_MAPPING.get(site_name, site_name)
        return (
            self._get_base_queryset()
            .filter(Q(site_name=site_name) | Q(url__icontains=url_keyword))
            .order_by("-is_preferred", "-last_login_success_at")
        )

    def get_credential_by_account(self, account: str, site_name: str) -> AccountCredential:
        """
        根据账号和站点获取凭证（无权限检查，内部使用）

        Args:
            account: 账号名称
            site_name: 站点名称

        Returns:
            凭证对象

        Raises:
            NotFoundError: 凭证不存在
        """
        credential = self._get_base_queryset().filter(account=account, site_name=site_name).first()
        if not credential:
            raise NotFoundError(
                message=_(f"账号凭证不存在: {account}@{site_name}"),
                code="CREDENTIAL_NOT_FOUND",
            )
        return credential


