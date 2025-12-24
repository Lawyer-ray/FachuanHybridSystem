"""
组织服务适配器
实现IOrganizationService接口，提供跨模块调用的统一入口
"""
from typing import Optional, List, Dict, Any
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