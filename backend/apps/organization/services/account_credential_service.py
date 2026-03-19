"""
账号凭证服务层
处理账号凭证相关的业务逻辑
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, PermissionDenied
from apps.organization.dtos import AccountCredentialCreateDTO, AccountCredentialUpdateDTO
from apps.organization.models import AccountCredential, Lawyer
from apps.organization.services.organization_access_policy import OrganizationAccessPolicy

logger = logging.getLogger("apps.organization")


class AccountCredentialService:
    SITE_URL_MAPPING: ClassVar[dict[str, str]] = {
        "court_zxfw": "zxfw.court.gov.cn",
    }

    def __init__(self) -> None:
        self._access_policy = OrganizationAccessPolicy()

    def _get_base_queryset(self) -> QuerySet[AccountCredential, AccountCredential]:
        return AccountCredential.objects.select_related("lawyer", "lawyer__law_firm")

    def list_all_credentials(self) -> QuerySet[AccountCredential, AccountCredential]:
        """返回不带权限过滤的凭证查询集，供跨模块适配器读取。"""
        return self._get_base_queryset()

    def list_credentials(
        self,
        lawyer_id: int | None = None,
        lawyer_name: str | None = None,
        user: Lawyer | None = None,
    ) -> QuerySet[AccountCredential, AccountCredential]:
        qs = self._get_base_queryset()

        # 权限过滤：非超级用户只能看到同一律所的凭证
        if user is None or not user.is_superuser:
            law_firm_id = user.law_firm_id if user else None
            if law_firm_id is not None:
                qs = qs.filter(lawyer__law_firm_id=law_firm_id)
            else:
                qs = qs.none()

        if lawyer_id is not None:
            qs = qs.filter(lawyer_id=lawyer_id)

        if lawyer_name:
            # 支持按 real_name 或 username 模糊匹配
            qs = qs.filter(Q(lawyer__real_name__icontains=lawyer_name) | Q(lawyer__username__icontains=lawyer_name))

        return qs

    def get_credential(self, credential_id: int, user: Lawyer | None = None) -> AccountCredential:
        """
        获取单个凭证

        Raises:
            NotFoundError: 凭证不存在
            PermissionDenied: 无权限访问该凭证
        """
        credential = self.get_credential_by_id(credential_id)

        # 权限检查：复用 OrganizationAccessPolicy 的律师读取权限
        if not self._access_policy.can_read_lawyer(user=user, lawyer=credential.lawyer):
            raise PermissionDenied(message=_("无权限访问该凭证"), code="CREDENTIAL_ACCESS_DENIED")

        return credential

    @transaction.atomic
    def create_credential(
        self,
        data: AccountCredentialCreateDTO,
        user: Lawyer | None = None,
    ) -> AccountCredential:
        """
        创建凭证

        Raises:
            NotFoundError: 律师不存在
            PermissionDenied: 无权限为该律师创建凭证
        """
        # 验证律师存在
        lawyer = Lawyer.objects.select_related("law_firm").filter(id=data.lawyer_id).first()
        if lawyer is None:
            raise NotFoundError(message=_("律师不存在"), code="LAWYER_NOT_FOUND")

        # 权限检查：验证用户是否有权限为该律师创建凭证
        if not self._access_policy.can_read_lawyer(user=user, lawyer=lawyer):
            raise PermissionDenied(message=_("无权限为该律师创建凭证"), code="CREDENTIAL_CREATE_DENIED")

        credential = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name=data.site_name,
            url=data.url or "",
            account=data.account,
            password=data.password,
        )

        logger.info(
            "凭证创建成功",
            extra={
                "credential_id": credential.id,
                "lawyer_id": data.lawyer_id,
                "site_name": data.site_name,
                "action": "create_credential",
            },
        )

        return credential

    @transaction.atomic
    def update_credential(
        self,
        credential_id: int,
        data: AccountCredentialUpdateDTO,
        user: Lawyer | None = None,
    ) -> AccountCredential:
        """
        更新凭证

        Raises:
            NotFoundError: 凭证不存在
            PermissionDenied: 无权限修改该凭证
        """
        credential = self.get_credential(credential_id, user)

        updated_fields: list[str] = []
        if data.site_name is not None:
            credential.site_name = data.site_name
            updated_fields.append("site_name")
        if data.url is not None:
            credential.url = data.url
            updated_fields.append("url")
        if data.account is not None:
            credential.account = data.account
            updated_fields.append("account")
        if data.password is not None:
            credential.password = data.password
            updated_fields.append("password")

        if updated_fields:
            credential.save(update_fields=updated_fields)

        logger.info("凭证更新成功", extra={"credential_id": credential_id, "action": "update_credential"})

        return credential

    @transaction.atomic
    def delete_credential(self, credential_id: int, user: Lawyer | None = None) -> None:
        """
        删除凭证

        Raises:
            NotFoundError: 凭证不存在
            PermissionDenied: 无权限删除该凭证
        """
        # get_credential 已包含权限检查
        credential = self.get_credential(credential_id, user)
        credential.delete()

        logger.info("凭证删除成功", extra={"credential_id": credential_id, "action": "delete_credential"})

    def get_credential_by_id(self, credential_id: int) -> AccountCredential:
        """根据ID获取凭证（无权限检查，供Adapter调用）

        Raises:
            NotFoundError: 凭证不存在
        """
        credential = self._get_base_queryset().filter(id=credential_id).first()
        if credential is None:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")
        return credential

    def update_login_success(self, credential_id: int) -> None:
        updated = AccountCredential.objects.filter(id=credential_id).update(
            login_success_count=F("login_success_count") + 1,
            last_login_success_at=timezone.now(),
        )
        if not updated:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")
        logger.info("登录成功统计已更新", extra={"credential_id": credential_id, "action": "update_login_success"})

    def update_login_failure(self, credential_id: int) -> None:
        updated = AccountCredential.objects.filter(id=credential_id).update(
            login_failure_count=F("login_failure_count") + 1,
        )
        if not updated:
            raise NotFoundError(message=_("凭证不存在"), code="CREDENTIAL_NOT_FOUND")
        logger.info("登录失败统计已更新", extra={"credential_id": credential_id, "action": "update_login_failure"})

    def filter_by_ids_and_site(
        self,
        credential_ids: list[int],
        site_name: str,
    ) -> QuerySet[AccountCredential, AccountCredential]:
        return self._get_base_queryset().filter(
            id__in=credential_ids,
            site_name=site_name,
        )

    def get_credentials_by_site(self, site_name: str) -> QuerySet[AccountCredential, AccountCredential]:
        url_keyword = self.SITE_URL_MAPPING.get(site_name, site_name)
        return (
            self._get_base_queryset()
            .filter(Q(site_name=site_name) | Q(url__icontains=url_keyword))
            .order_by("-last_login_success_at")
        )

    def get_credential_by_account(self, account: str, site_name: str) -> AccountCredential:
        """根据账号和站点获取凭证（无权限检查，内部使用）。

        Raises:
            NotFoundError: 凭证不存在
        """
        credential = self._get_base_queryset().filter(account=account, site_name=site_name).first()
        if credential is None:
            raise NotFoundError(
                message=_("账号凭证不存在"),
                code="CREDENTIAL_NOT_FOUND",
            )
        return credential

    def list_sites_for_lawyer(self, lawyer_id: int) -> list[str]:
        return list(
            self._get_base_queryset().filter(lawyer_id=lawyer_id).values_list("site_name", flat=True).distinct()
        )
