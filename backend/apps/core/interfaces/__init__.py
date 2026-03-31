"""
跨模块接口定义
通过接口解耦模块间的直接依赖
"""

from __future__ import annotations

# Document DTOs
# Contract DTOs
# Case DTOs
# DTOs
from apps.core.dto import (
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

# Case Extended Protocols
# Document Generation Protocols
# Common Protocols (跨模块依赖所需)
# Organization Protocols
# Automation Protocols
# Document Protocols
# Contract Protocols
# Case Protocols
from apps.core.protocols import (
    IAccountSelectionStrategy,
    IAutoLoginService,
    IAutomationService,
    IAutoNamerService,
    IAutoTokenAcquisitionService,
    IBaoquanTokenService,
    IBrowserService,
    IBusinessConfigService,
    ICaptchaService,
    ICaseAssignmentService,
    ICaseChatService,
    ICaseFilingNumberService,
    ICaseLogService,
    ICaseMaterialService,
    ICaseNumberService,
    ICaseSearchService,
    ICaseService,
    ICauseCourtQueryService,
    IClientService,
    IContractAssignmentQueryService,
    IContractFolderBindingService,
    IContractGenerationService,
    IContractPaymentService,
    IContractService,
    IConversationHistoryService,
    ICourtDocumentRecognitionService,
    ICourtDocumentService,
    ICourtPleadingSignalsService,
    ICourtSMSService,
    ICourtTokenStoreService,
    IDocumentProcessingService,
    IDocumentService,
    IDocumentTemplateBindingService,
    IEvidenceListPlaceholderService,
    IEvidenceQueryService,
    IGenerationTaskService,
    ILawFirmService,
    ILawyerService,
    ILitigationFeeCalculatorService,
    ILLMService,
    IMonitorService,
    IOcrService,
    IOrganizationService,
    IPerformanceMonitorService,
    IPermissionService,
    IPreservationQuoteService,
    IReminderService,
    ISecurityService,
    ISupplementaryAgreementGenerationService,
    ISystemConfigService,
    ITokenService,
    IValidatorService,
)

# Service Locator and Event Bus
from .service_locator import EventBus, Events, ServiceLocator

__all__ = [
    # DTOs
    "LoginAttemptResult",
    "TokenAcquisitionResult",
    "AccountCredentialDTO",
    "LawyerDTO",
    "LawFirmDTO",
    "TeamDTO",
    "ClientDTO",
    "ClientIdentityDocDTO",
    "PropertyClueDTO",
    "ContractDTO",
    "CaseDTO",
    "ConversationHistoryDTO",
    "ReminderDTO",
    "ReminderTypeDTO",
    # Case DTOs
    "CaseSearchResultDTO",
    "CaseTemplateBindingDTO",
    "CasePartyDTO",
    # Contract DTOs
    "PartyRoleDTO",
    "SupplementaryAgreementDTO",
    # Document DTOs
    "DocumentTemplateDTO",
    "EvidenceItemDigestDTO",
    "GenerationTaskDTO",
    # Automation DTOs
    "CourtPleadingSignalsDTO",
    # Case Protocols
    "ICaseService",
    "ICaseSearchService",
    "ICaseLogService",
    "ICaseNumberService",
    "ICaseFilingNumberService",
    "ILitigationFeeCalculatorService",
    "ICaseChatService",
    "ICaseAssignmentService",
    "ICaseMaterialService",
    # Contract Protocols
    "IContractService",
    "IContractAssignmentQueryService",
    "IContractFolderBindingService",
    "IContractPaymentService",
    # Document Protocols
    "ICourtDocumentService",
    "IDocumentProcessingService",
    "IAutoNamerService",
    "ICourtDocumentRecognitionService",
    "IDocumentService",
    "IDocumentTemplateBindingService",
    "IEvidenceQueryService",
    "IGenerationTaskService",
    "IContractGenerationService",
    "ISupplementaryAgreementGenerationService",
    # Automation Protocols
    "IAutoTokenAcquisitionService",
    "IAccountSelectionStrategy",
    "IAutoLoginService",
    "ITokenService",
    "ICourtTokenStoreService",
    "IBaoquanTokenService",
    "IBrowserService",
    "ICaptchaService",
    "IOcrService",
    "IMonitorService",
    "ISecurityService",
    "IValidatorService",
    "IPreservationQuoteService",
    "IAutomationService",
    "ICourtSMSService",
    "ICourtPleadingSignalsService",
    "IPerformanceMonitorService",
    # Organization Protocols
    "IOrganizationService",
    "ILawyerService",
    "ILawFirmService",
    "IClientService",
    "IPermissionService",
    # Common Protocols
    "ISystemConfigService",
    "ICauseCourtQueryService",
    "IBusinessConfigService",
    "IReminderService",
    "ILLMService",
    "IConversationHistoryService",
    "IEvidenceListPlaceholderService",
    # Service Locator and Event Bus
    "ServiceLocator",
    "EventBus",
    "Events",
]
