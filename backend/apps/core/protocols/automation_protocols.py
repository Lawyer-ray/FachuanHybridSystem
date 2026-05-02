"""
自动化相关 Protocol 接口定义 — re-export facade

所有 Protocol 类按领域拆分到子模块，此处统一 re-export 以保持外部 import 路径不变。
"""

from .browser_protocols import IBrowserService, ICaptchaService, IOcrService
from .court_protocols import (
    IAutomationService,
    ICourtDocumentRecognitionService,
    ICourtDocumentService,
    ICourtSMSService,
)
from .processing_protocols import (
    IAutoNamerService,
    IDocumentProcessingService,
    IPerformanceMonitorService,
    IPreservationQuoteService,
)
from .token_protocols import (
    IAutoLoginService,
    IAutoTokenAcquisitionService,
    IBaoquanTokenService,
    ICourtPleadingSignalsService,
    ICourtTokenStoreService,
    ITokenService,
)

__all__ = [
    "IAutoLoginService",
    "IAutoNamerService",
    "IAutoTokenAcquisitionService",
    "IAutomationService",
    "IBaoquanTokenService",
    "IBrowserService",
    "ICaptchaService",
    "ICourtDocumentRecognitionService",
    "ICourtDocumentService",
    "ICourtPleadingSignalsService",
    "ICourtSMSService",
    "ICourtTokenStoreService",
    "IDocumentProcessingService",
    "IOcrService",
    "IPerformanceMonitorService",
    "IPreservationQuoteService",
    "ITokenService",
]
