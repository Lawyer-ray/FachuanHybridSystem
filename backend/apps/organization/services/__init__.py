"""
Organization Services Module
组织模块服务层
"""
from .lawyer_service import LawyerService, LawyerServiceAdapter
from .lawfirm_service import LawFirmService, LawFirmServiceAdapter
from .account_credential_service import AccountCredentialService
from .team_service import TeamService
from .auth_service import AuthService
from .account_credential_admin_service import AccountCredentialAdminService
from .organization_service_adapter import OrganizationServiceAdapter

__all__ = [
    "LawyerService",
    "LawyerServiceAdapter",
    "LawFirmService",
    "LawFirmServiceAdapter",
    "AccountCredentialService",
    "AccountCredentialAdminService",
    "TeamService",
    "AuthService",
    "OrganizationServiceAdapter",
]
