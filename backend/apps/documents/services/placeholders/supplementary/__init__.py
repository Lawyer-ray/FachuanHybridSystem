"""
补充协议占位符服务模块

包含所有补充协议相关的占位符服务.
"""

# 导入所有补充协议占位符服务以触发自动注册
from .basic_service import SupplementaryAgreementBasicService
from .opposing_service import SupplementaryAgreementOpposingService
from .principal_service import SupplementaryAgreementPrincipalService
from .signature_service import SupplementaryAgreementSignatureService

__all__ = [
    "SupplementaryAgreementBasicService",
    "SupplementaryAgreementOpposingService",
    "SupplementaryAgreementPrincipalService",
    "SupplementaryAgreementSignatureService",
]
