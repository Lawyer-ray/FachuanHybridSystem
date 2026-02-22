"""
数据传输对象 (DTO)
用于跨模块传递数据,避免直接依赖其他模块的 Model

从原单文件实现演进为领域分包:apps.core.dto.*
本文件仅作为向后兼容的聚合导出层.
"""

from .dto import (
    AccountCredentialDTO,
    CaseDTO,
    CasePartyDTO,
    CaseSearchResultDTO,
    CaseTemplateBindingDTO,
    ClientDTO,
    ClientIdentityDocDTO,
    ContractDTO,
    ConversationHistoryDTO,
    CourtPleadingSignalsDTO,
    DocumentTemplateDTO,
    EvidenceItemDigestDTO,
    GenerationTaskDTO,
    LawFirmDTO,
    LawyerDTO,
    LoginAttemptResult,
    PartyRoleDTO,
    PropertyClueDTO,
    ReminderDTO,
    ReminderTypeDTO,
    SupplementaryAgreementDTO,
    TeamDTO,
    TokenAcquisitionResult,
)

__all__: list[str] = [
    "AccountCredentialDTO",
    "CaseDTO",
    "CasePartyDTO",
    "CaseSearchResultDTO",
    "CaseTemplateBindingDTO",
    "ClientDTO",
    "ClientIdentityDocDTO",
    "ContractDTO",
    "ConversationHistoryDTO",
    "CourtPleadingSignalsDTO",
    "DocumentTemplateDTO",
    "EvidenceItemDigestDTO",
    "GenerationTaskDTO",
    "LawFirmDTO",
    "LawyerDTO",
    "LoginAttemptResult",
    "PartyRoleDTO",
    "PropertyClueDTO",
    "ReminderDTO",
    "ReminderTypeDTO",
    "SupplementaryAgreementDTO",
    "TeamDTO",
    "TokenAcquisitionResult",
]
