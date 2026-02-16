"""
通用 Protocol 接口定义

包含:ISystemConfigService, ILLMService, IPromptVersionService, IBusinessConfigService,
      IMonitorService, ISecurityService, IValidatorService, IPermissionService,
      IReminderService, ICaseChatService, IAccountSelectionStrategy, IEvidenceListPlaceholderService
"""

from .common import (
    IAccountSelectionStrategy,
    IBusinessConfigService,
    ICaseChatService,
    ICauseCourtQueryService,
    IConversationHistoryService,
    IEvidenceListPlaceholderService,
    ILLMService,
    IMonitorService,
    IPermissionService,
    IPromptVersionService,
    IReminderService,
    ISecurityService,
    ISystemConfigService,
    IValidatorService,
)

__all__: list[str] = [
    "IAccountSelectionStrategy",
    "IBusinessConfigService",
    "ICaseChatService",
    "ICauseCourtQueryService",
    "IConversationHistoryService",
    "IEvidenceListPlaceholderService",
    "ILLMService",
    "IMonitorService",
    "IPermissionService",
    "IPromptVersionService",
    "IReminderService",
    "ISecurityService",
    "ISystemConfigService",
    "IValidatorService",
]
