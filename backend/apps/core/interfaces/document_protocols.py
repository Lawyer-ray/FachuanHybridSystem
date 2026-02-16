"""
跨模块 Protocol 兼容出口(Document,落在 protocols/automation_protocols.py)
"""

from apps.core.protocols import (
    IAutoNamerService,
    ICourtDocumentRecognitionService,
    ICourtDocumentService,
    IDocumentProcessingService,
)

__all__: list[str] = [
    "ICourtDocumentService",
    "IDocumentProcessingService",
    "IAutoNamerService",
    "ICourtDocumentRecognitionService",
]
