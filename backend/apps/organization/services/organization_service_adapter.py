"""
组织服务适配器
实现IOrganizationService接口，提供跨模块调用的统一入口
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models

from apps.core.interfaces import AccountCredentialDTO, IOrganizationService

from .account_credential_service import AccountCredentialService

if TYPE_CHECKING:
    from apps.core.dto.organization import LawyerDTO
    from apps.organization.services.lawfirm_service import LawFirmService
    from apps.organization.services.lawyer_service import LawyerService
    from apps.organization.services.team_service import TeamService


class OrganizationServiceAdapter(IOrganizationService):
    """
    组织服务适配器

    实现IOrganizationService接口，提供跨模块调用的统一入口
    """

    def __init__(self, account_credential_service: AccountCredentialService | None = None):
        """
        初始化适配器

        Args:
            account_credential_service: 账号凭证服务（可选，用于依赖注入）
        """
        self._account_credential_service = account_credential_service
        self._lawfirm_service: LawFirmService | None = None
        self._team_service: TeamService | None = None
        self._lawyer_service: LawyerService | None = None

    @property
    def account_credential_service(self) -> AccountCredentialService:
        """延迟加载账号凭证服务"""
        if self._account_credential_service is None:
            self._account_credential_service = AccountCredentialService()
        return self._account_credential_service

    @property
    def lawfirm_service(self) -> LawFirmService:
        """延迟加载律所服务"""
        if self._lawfirm_service is None:
            from apps.organization.services.lawfirm_service import LawFirmService

            self._lawfirm_service = LawFirmService()
        return self._lawfirm_service

    @property
    def team_service(self) -> TeamService:
        """延迟加载团队服务"""
        if self._team_service is None:
            from apps.organization.services.team_service import TeamService

            self._team_service = TeamService()
        return self._team_service

    @property
    def lawyer_service(self) -> LawyerService:
        """延迟加载律师服务"""
        if self._lawyer_service is None:
            from apps.organization.services.lawyer_service import LawyerService

            self._lawyer_service = LawyerService()
        return self._lawyer_service

    def get_law_firm(self, law_firm_id: int) -> dict[str, Any] | None:
        """
        获取律所信息

        Args:
            law_firm_id: 律所 ID

        Returns:
            律所信息字典，不存在时返回 None
        """
        lawfirm = self.lawfirm_service._get_lawfirm_internal(law_firm_id)
        if lawfirm is None:
            return None
        return {
            "id": lawfirm.id,
            "name": lawfirm.name,
            "address": lawfirm.address,
            "phone": lawfirm.phone,
            "social_credit_code": lawfirm.social_credit_code,
        }

    def get_team(self, team_id: int) -> dict[str, Any] | None:
        """
        获取团队信息

        Args:
            team_id: 团队 ID

        Returns:
            团队信息字典，不存在时返回 None
        """
        from apps.organization.models import Team

        team = Team.objects.select_related("law_firm").filter(id=team_id).first()
        if team is None:
            return None
        return {
            "id": team.id,
            "name": team.name,
            "team_type": team.team_type,
            "law_firm_id": team.law_firm_id,
            "law_firm_name": team.law_firm.name if team.law_firm else None,
        }

    def get_lawyers_in_organization(self, organization_id: int) -> list[LawyerDTO]:
        """
        获取组织内的所有律师

        Args:
            organization_id: 组织 ID（律所 ID）

        Returns:
            律师 DTO 列表
        """
        from apps.organization.models import Lawyer
        from apps.organization.services.dto_assemblers import LawyerDtoAssembler

        lawyers = Lawyer.objects.select_related("law_firm").filter(law_firm_id=organization_id)
        assembler = LawyerDtoAssembler()
        return [assembler.to_dto(lawyer) for lawyer in lawyers]

    def get_all_credentials_internal(self) -> list[AccountCredentialDTO]:
        """
        内部方法：获取所有账号凭证

        Returns:
            所有账号凭证的 DTO 列表
        """
        from apps.organization.models import AccountCredential

        credentials = AccountCredential.objects.select_related("lawyer", "lawyer__law_firm").all()
        return [AccountCredentialDTO.from_model(credential) for credential in credentials]

    def get_credential_internal(self, credential_id: int) -> AccountCredentialDTO:
        """
        内部方法：获取账号凭证（无权限检查）

        Args:
            credential_id: 凭证 ID

        Returns:
            账号凭证 DTO

        Raises:
            NotFoundError: 凭证不存在
        """
        credential = self.account_credential_service._get_credential_internal(credential_id)
        return AccountCredentialDTO.from_model(credential)

    def get_credentials_by_site_internal(self, site_name: str) -> list[AccountCredentialDTO]:
        """
        内部方法：根据站点名称获取所有凭证（无权限检查）

        支持两种匹配方式：
        1. 精确匹配 site_name
        2. URL 包含匹配（如 url 包含 zxfw.court.gov.cn）

        Args:
            site_name: 站点名称或URL关键字

        Returns:
            账号凭证 DTO 列表
        """
        from django.db.models import Q

        from apps.organization.models import AccountCredential

        SITE_URL_MAPPING = {
            "court_zxfw": "zxfw.court.gov.cn",
        }

        url_keyword = SITE_URL_MAPPING.get(site_name, site_name)

        credentials = (
            AccountCredential.objects.filter(Q(site_name=site_name) | Q(url__icontains=url_keyword))
            .select_related("lawyer", "lawyer__law_firm")
            .order_by("-is_preferred", "-last_login_success_at")
        )
        return [AccountCredentialDTO.from_model(c) for c in credentials]

    def get_credential_by_account_internal(self, account: str, site_name: str) -> AccountCredentialDTO:
        """
        内部方法：根据账号和站点获取凭证（无权限检查）

        Args:
            account: 账号名称
            site_name: 站点名称

        Returns:
            账号凭证 DTO

        Raises:
            NotFoundError: 凭证不存在
        """
        from apps.core.exceptions import NotFoundError

        from apps.organization.models import AccountCredential

        credential = (
            AccountCredential.objects.filter(account=account, site_name=site_name)
            .select_related("lawyer", "lawyer__law_firm")
            .first()
        )

        if not credential:
            raise NotFoundError(
                message=f"账号凭证不存在: {account}@{site_name}",
                code="CREDENTIAL_NOT_FOUND",
                errors={"account": account, "site_name": site_name},
            )
        return AccountCredentialDTO.from_model(credential)

    def update_login_success_internal(self, credential_id: int) -> None:
        """
        内部方法：更新登录成功统计（无权限检查）

        Args:
            credential_id: 凭证 ID
        """
        from django.utils import timezone

        from apps.organization.models import AccountCredential

        AccountCredential.objects.filter(id=credential_id).update(
            login_success_count=models.F("login_success_count") + 1, last_login_success_at=timezone.now()
        )

    def update_login_failure_internal(self, credential_id: int) -> None:
        """
        内部方法：更新登录失败统计（无权限检查）

        Args:
            credential_id: 凭证 ID
        """
        from django.db.models import F

        from apps.organization.models import AccountCredential

        AccountCredential.objects.filter(id=credential_id).update(login_failure_count=F("login_failure_count") + 1)

    def get_lawyer_by_id_internal(self, lawyer_id: int) -> LawyerDTO | None:
        """
        内部方法：根据 ID 获取律师信息（无权限检查）

        Args:
            lawyer_id: 律师 ID

        Returns:
            LawyerDTO，不存在返回 None
        """
        from apps.core.dto.organization import LawyerDTO as LawyerDTOClass
        from apps.organization.models import Lawyer

        try:
            lawyer = Lawyer.objects.select_related("law_firm").get(id=lawyer_id)
            return LawyerDTOClass.from_model(lawyer)
        except Lawyer.DoesNotExist:
            return None

    def get_default_lawyer_id_internal(self) -> int | None:
        """
        内部方法：获取默认律师 ID（取第一个 is_admin=True 的律师）

        Returns:
            默认律师 ID，不存在返回 None
        """
        from apps.organization.models import Lawyer

        lawyer = Lawyer.objects.filter(is_admin=True).first()
        return lawyer.id if lawyer else None
