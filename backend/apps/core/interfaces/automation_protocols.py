"""
跨模块 Protocol 兼容出口(Automation)
"""

from apps.core.protocols import (
    IAccountSelectionStrategy,
    IAutoLoginService,
    IAutomationService,
    IAutoTokenAcquisitionService,
    IBaoquanTokenService,
    IBrowserService,
    ICaptchaService,
    ICourtPleadingSignalsService,
    ICourtSMSService,
    ICourtTokenStoreService,
    IMonitorService,
    IOcrService,
    IPerformanceMonitorService,
    IPreservationQuoteService,
    ISecurityService,
    ITokenService,
    IValidatorService,
)

__all__: list[str] = [
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
]
