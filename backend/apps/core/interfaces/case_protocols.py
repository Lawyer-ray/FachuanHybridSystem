"""
跨模块 Protocol 兼容出口(Case)
"""

from apps.core.protocols import (
    ICaseChatService,
    ICaseFilingNumberService,
    ICaseLogService,
    ICaseNumberService,
    ICaseSearchService,
    ICaseService,
    ILitigationFeeCalculatorService,
)

__all__: list[str] = [
    "ICaseService",
    "ICaseSearchService",
    "ICaseNumberService",
    "ICaseFilingNumberService",
    "ICaseLogService",
    "ILitigationFeeCalculatorService",
    "ICaseChatService",
]
