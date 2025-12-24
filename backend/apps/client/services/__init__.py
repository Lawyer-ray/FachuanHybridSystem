"""
Client Services Module
客户模块服务层
"""
from .client_service import ClientService, ClientServiceAdapter
from .property_clue_service import PropertyClueService
from .client_identity_doc_service import ClientIdentityDocService
from .client_admin_service import ClientAdminService

__all__ = [
    "ClientService", 
    "ClientServiceAdapter", 
    "PropertyClueService",
    "ClientIdentityDocService",
    "ClientAdminService"
]
