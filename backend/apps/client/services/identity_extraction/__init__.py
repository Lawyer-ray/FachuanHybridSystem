"""证件信息提取服务模块。"""

from .data_classes import ExtractionResult, OCRExtractionError, OllamaExtractionError
from .extraction_service import IdentityExtractionService

__all__ = [
    "ExtractionResult",
    "IdentityExtractionService",
    "OCRExtractionError",
    "OllamaExtractionError",
]
