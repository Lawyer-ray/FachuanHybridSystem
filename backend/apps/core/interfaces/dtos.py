"""
跨模块 DTO 兼容出口
"""

from apps.core.dtos import (
    AccountCredentialDTO,
    CaseDTO,
    ClientDTO,
    ContractDTO,
    LawFirmDTO,
    LawyerDTO,
    LoginAttemptResult,
    TokenAcquisitionResult,
)

__all__: list[str] = [
    "LoginAttemptResult",
    "TokenAcquisitionResult",
    "AccountCredentialDTO",
    "LawyerDTO",
    "LawFirmDTO",
    "ClientDTO",
    "ContractDTO",
    "CaseDTO",
]
