"""
组织服务适配器
实现IOrganizationService接口，提供跨模块调用的统一入口
"""
from typing import Optional, List, Dict, Any
from django.db import models
from apps.core.interfaces import IOrganizationService, AccountCredentialDTO
from .account_credential_service import AccountCredentialService


class OrganizationServiceAdapter(IOrganizationService):
    """
    组织服务适配器
    
    实现IOrganizationService接口，提供跨模块调用的统一入口
    """
    
    def __init__(self, account_credential_service: Optional[AccountCredentialService] = None):
        """
        初始化适配器
        
        Args:
            account_credential_service: 账号凭证服务（可选，用于依赖注入）
        """
        self._account_credential_service = account_credential_service
    
    @property
    def account_credential_service(self) -> AccountCredentialService:
        """延迟加载账号凭证服务"""
        if self._account_credential_service is None:
            self._account_credential_service = AccountCredentialService()
        return self._account_credential_service
    
    def get_law_firm(self, law_firm_id: int) -> Optional[Dict[str, Any]]:
        """
        获取律所信息

        Args:
            law_firm_id: 律所 ID

        Returns:
            律所信息字典，不存在时返回 None
        """
        # TODO: 实现律所信息获取逻辑
        # 这里暂时返回None，后续可以通过LawFirmService实现
        return None

    def get_team(self, team_id: int) -> Optional[Dict[str, Any]]:
        """
        获取团队信息

        Args:
            team_id: 团队 ID

        Returns:
            团队信息字典，不存在时返回 None
        """
        # TODO: 实现团队信息获取逻辑
        # 这里暂时返回None，后续可以通过TeamService实现
        return None

    def get_lawyers_in_organization(self, organization_id: int) -> List[AccountCredentialDTO]:
        """
        获取组织内的所有律师

        Args:
            organization_id: 组织 ID

        Returns:
            律师 DTO 列表
        """
        # TODO: 实现组织内律师获取逻辑
        # 这里暂时返回空列表，后续可以通过LawyerService实现
        return []

    def get_all_credentials_internal(self) -> List[AccountCredentialDTO]:
        """
        内部方法：获取所有账号凭证
        
        Returns:
            所有账号凭证的 DTO 列表
        """
        # 直接从数据库获取所有凭证，绕过权限检查
        from ..models import AccountCredential
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
    
    def get_credentials_by_site_internal(self, site_name: str) -> List[AccountCredentialDTO]:
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
        from ..models import AccountCredential
        from django.db.models import Q
        
        # 站点名称到URL关键字的映射
        SITE_URL_MAPPING = {
            'court_zxfw': 'zxfw.court.gov.cn',
        }
        
        # 构建查询条件
        url_keyword = SITE_URL_MAPPING.get(site_name, site_name)
        
        credentials = AccountCredential.objects.filter(
            Q(site_name=site_name) | Q(url__icontains=url_keyword)
        ).select_related("lawyer", "lawyer__law_firm").order_by(
            '-is_preferred', '-last_login_success_at'
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
        from ..models import AccountCredential
        from apps.core.exceptions import NotFoundError
        
        credential = AccountCredential.objects.filter(
            account=account, site_name=site_name
        ).select_related("lawyer", "lawyer__law_firm").first()
        
        if not credential:
            raise NotFoundError(
                message=f"账号凭证不存在: {account}@{site_name}",
                code="CREDENTIAL_NOT_FOUND",
                errors={"account": account, "site_name": site_name}
            )
        return AccountCredentialDTO.from_model(credential)
    
    def update_login_success_internal(self, credential_id: int) -> None:
        """
        内部方法：更新登录成功统计（无权限检查）
        
        Args:
            credential_id: 凭证 ID
        """
        from ..models import AccountCredential
        from django.utils import timezone
        
        AccountCredential.objects.filter(id=credential_id).update(
            login_success_count=models.F('login_success_count') + 1,
            last_login_success_at=timezone.now()
        )
    
    def update_login_failure_internal(self, credential_id: int) -> None:
        """
        内部方法：更新登录失败统计（无权限检查）
        
        Args:
            credential_id: 凭证 ID
        """
        from ..models import AccountCredential
        from django.db.models import F
        
        AccountCredential.objects.filter(id=credential_id).update(
            login_failure_count=F('login_failure_count') + 1
        )