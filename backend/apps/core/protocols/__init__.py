"""
Protocol 接口定义模块

将 Protocol 接口按业务模块拆分,提高可维护性.
所有接口通过 apps.core.interfaces 重导出,保持向后兼容.
"""

from .automation_protocols import (
    IAutoLoginService,
    IAutomationService,
    IAutoNamerService,
    IAutoTokenAcquisitionService,
    IBaoquanTokenService,
    IBrowserService,
    ICaptchaService,
    ICourtDocumentRecognitionService,
    ICourtDocumentService,
    ICourtPleadingSignalsService,
    ICourtSMSService,
    ICourtTokenStoreService,
    IDocumentProcessingService,
    IOcrService,
    IPerformanceMonitorService,
    IPreservationQuoteService,
    ITokenService,
)
from .case_assignment_protocols import ICaseAssignmentService
from .case_material_protocols import ICaseMaterialService
from .case_protocols import (
    ICaseFilingNumberService,
    ICaseLogService,
    ICaseNumberService,
    ICaseSearchService,
    ICaseService,
    ILitigationFeeCalculatorService,
)
from .client_protocols import IClientService
from .common_protocols import (
    IAccountSelectionStrategy,
    IBusinessConfigService,
    ICaseChatService,
    ICauseCourtQueryService,
    IConversationHistoryService,
    IEvidenceListPlaceholderService,
    ILLMService,
    IMonitorService,
    IPermissionService,
    IReminderService,
    ISecurityService,
    ISystemConfigService,
    IValidatorService,
)
from .contract_protocols import (
    IContractAssignmentQueryService,
    IContractFolderBindingService,
    IContractPaymentService,
    IContractService,
)
from .document_protocols import (
    IContractGenerationService,
    IDocumentService,
    IDocumentTemplateBindingService,
    IEvidenceQueryService,
    IGenerationTaskService,
    ISupplementaryAgreementGenerationService,
)
from .organization_protocols import ILawFirmService, ILawyerService, IOrganizationService

__all__ = [
    # Case protocols
    "ICaseService",
    "ICaseSearchService",
    "ICaseNumberService",
    "ICaseFilingNumberService",
    "ICaseLogService",
    "ILitigationFeeCalculatorService",
    "ICaseAssignmentService",
    "ICaseMaterialService",
    # Client protocols
    "IClientService",
    # Contract protocols
    "IContractService",
    "IContractPaymentService",
    "IContractAssignmentQueryService",
    "IContractFolderBindingService",
    # Document protocols
    "IDocumentService",
    "IDocumentTemplateBindingService",
    "IEvidenceQueryService",
    "IGenerationTaskService",
    "IContractGenerationService",
    "ISupplementaryAgreementGenerationService",
    # Organization protocols
    "IOrganizationService",
    "ILawyerService",
    "ILawFirmService",
    # Automation protocols
    "IAutoTokenAcquisitionService",
    "IAutoLoginService",
    "ITokenService",
    "ICourtTokenStoreService",
    "IBaoquanTokenService",
    "IBrowserService",
    "ICaptchaService",
    "IOcrService",
    "IAutomationService",
    "ICourtSMSService",
    "ICourtDocumentService",
    "ICourtDocumentRecognitionService",
    "ICourtPleadingSignalsService",
    "IPreservationQuoteService",
    "IDocumentProcessingService",
    "IAutoNamerService",
    "IPerformanceMonitorService",
    # Common protocols
    "ISystemConfigService",
    "ILLMService",
    "IBusinessConfigService",
    "IMonitorService",
    "ISecurityService",
    "IValidatorService",
    "IPermissionService",
    "IReminderService",
    "ICaseChatService",
    "IAccountSelectionStrategy",
    "IEvidenceListPlaceholderService",
    "IConversationHistoryService",
    "ICauseCourtQueryService",
]
