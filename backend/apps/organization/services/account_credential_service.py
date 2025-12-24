"""
账号凭证服务层
处理账号凭证相关的业务逻辑
"""
from typing import Optional, Dict, Any
from decimal import Decimal
from django.db import transaction
from django.db.models import QuerySet, Q

from apps.core.exceptions import (
    ValidationException,
    NotFoundError,
    PermissionDenied,
)
from ..models import AccountCredential, Lawyer
import logging

logger = logging.getLogger("apps.organization")


class AccountCredentialService:
    """
    账号凭证服务

    职责：
    1. 封装账号凭证相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    """

    def __init__(self):
        """初始化服务"""
        pass

    def _get_base_queryset(self) -> QuerySet[AccountCredential]:
        """获取带预加载的基础查询集"""
        return AccountCredential.objects.select_related("lawyer", "lawyer__law_firm")

    def _is_superuser(self, user) -> bool:
        """检查用户是否为超级用户"""
        if user is None:
            return False
        return getattr(user, "is_superuser", False)

    def _get_user_law_firm_id(self, user) -> Optional[int]:
        """获取用户所属律所 ID"""
        if user is None:
            return None
        return getattr(user, "law_firm_id", None)

    def _check_credential_access(self, user, credential: AccountCredential) -> bool:
        """
        检查用户是否有权限访问指定凭证

        Args:
            user: 当前用户
            credential: 凭证对象

        Returns:
            是否有权限
        """
        # 超级用户可以访问所有凭证
        if self._is_superuser(user):
            return True

        # 获取用户所属律所
        user_law_firm_id = self._get_user_law_firm_id(user)
        if user_law_firm_id is None:
            return False

        # 检查凭证所属律师的律所是否与用户相同
        credential_law_firm_id = getattr(credential.lawyer, "law_firm_id", None)
        return user_law_firm_id == credential_law_firm_id

    def _check_lawyer_access(self, user, lawyer: Lawyer) -> bool:
        """
        检查用户是否有权限访问指定律师

        Args:
            user: 当前用户
            lawyer: 律师对象

        Returns:
            是否有权限
        """
        # 超级用户可以访问所有律师
        if self._is_superuser(user):
            return True

        # 获取用户所属律所
        user_law_firm_id = self._get_user_law_firm_id(user)
        if user_law_firm_id is None:
            return False

        # 检查律师的律所是否与用户相同
        lawyer_law_firm_id = getattr(lawyer, "law_firm_id", None)
        return user_law_firm_id == lawyer_law_firm_id

    def list_credentials(
        self,
        lawyer_id: Optional[int] = None,
        lawyer_name: Optional[str] = None,
        user=None,
    ) -> QuerySet[AccountCredential]:
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
        if not self._is_superuser(user):
            user_law_firm_id = self._get_user_law_firm_id(user)
            if user_law_firm_id is not None:
                qs = qs.filter(lawyer__law_firm_id=user_law_firm_id)
            else:
                # 用户没有关联律所，返回空查询集
                qs = qs.none()

        if lawyer_id is not None:
            qs = qs.filter(lawyer_id=lawyer_id)

        if lawyer_name:
            # 支持按 real_name 或 username 模糊匹配
            qs = qs.filter(
                Q(lawyer__real_name__icontains=lawyer_name) |
                Q(lawyer__username__icontains=lawyer_name)
            )

        return qs

    def get_credential(self, credential_id: int, user=None) -> AccountCredential:
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
            raise NotFoundError(
                message="凭证不存在",
                code="CREDENTIAL_NOT_FOUND"
            )

        # 权限检查
        if not self._check_credential_access(user, credential):
            raise PermissionDenied(
                message="无权限访问该凭证",
                code="CREDENTIAL_ACCESS_DENIED"
            )

        return credential

    @transaction.atomic
    def create_credential(
        self,
        lawyer_id: int,
        site_name: str,
        account: str,
        password: str,
        url: Optional[str] = None,
        user=None,
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
            raise NotFoundError(
                message="律师不存在",
                code="LAWYER_NOT_FOUND"
            )

        # 权限检查：验证用户是否有权限为该律师创建凭证
        if not self._check_lawyer_access(user, lawyer):
            raise PermissionDenied(
                message="无权限为该律师创建凭证",
                code="CREDENTIAL_CREATE_DENIED"
            )

        credential = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name=site_name,
            url=url or "",
            account=account,
            password=password,
        )

        logger.info(
            f"凭证创建成功",
            extra={
                "credential_id": credential.id,
                "lawyer_id": lawyer_id,
                "site_name": site_name,
                "action": "create_credential"
            }
        )

        return credential

    @transaction.atomic
    def update_credential(
        self,
        credential_id: int,
        data: Dict[str, Any],
        user=None,
    ) -> AccountCredential:
        """
        更新凭证

        Args:
            credential_id: 凭证 ID
            data: 更新数据
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
            if hasattr(credential, key):
                setattr(credential, key, value)

        credential.save()

        logger.info(
            f"凭证更新成功",
            extra={
                "credential_id": credential_id,
                "action": "update_credential"
            }
        )

        return credential

    @transaction.atomic
    def delete_credential(self, credential_id: int, user=None) -> None:
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

        logger.info(
            f"凭证删除成功",
            extra={
                "credential_id": credential_id,
                "action": "delete_credential"
            }
        )

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
            raise NotFoundError(
                message="凭证不存在",
                code="CREDENTIAL_NOT_FOUND"
            )
        return credential

    @transaction.atomic
    def update_login_success(self, credential_id: int) -> None:
        """
        更新登录成功统计

        Args:
            credential_id: 凭证 ID

        Raises:
            NotFoundError: 凭证不存在
        """
        from django.utils import timezone

        credential = self._get_credential_internal(credential_id)
        credential.last_login_success_at = timezone.now()
        credential.login_success_count += 1
        credential.save(update_fields=['last_login_success_at', 'login_success_count'])

        logger.info(
            f"登录成功统计已更新",
            extra={
                "credential_id": credential_id,
                "login_success_count": credential.login_success_count,
                "action": "update_login_success"
            }
        )

    @transaction.atomic
    def update_login_failure(self, credential_id: int) -> None:
        """
        更新登录失败统计

        Args:
            credential_id: 凭证 ID

        Raises:
            NotFoundError: 凭证不存在
        """
        credential = self._get_credential_internal(credential_id)
        credential.login_failure_count += 1
        credential.save(update_fields=['login_failure_count'])

        logger.info(
            f"登录失败统计已更新",
            extra={
                "credential_id": credential_id,
                "login_failure_count": credential.login_failure_count,
                "action": "update_login_failure"
            }
        )
