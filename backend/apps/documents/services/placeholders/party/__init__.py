"""
当事人占位符服务

提供委托人、对方当事人等信息格式化服务.
"""

from .opposing_party_service import OpposingPartyService
from .principal_info_service import PrincipalInfoService
from .principal_signature_service import PrincipalSignatureService

__all__ = [
    "OpposingPartyService",
    "PrincipalInfoService",
    "PrincipalSignatureService",
]
