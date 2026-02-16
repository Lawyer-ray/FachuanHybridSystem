"""
证件信息提取服务模块
"""

from .data_classes import ExtractionResult, OCRExtractionError, OllamaExtractionError
from .extraction_service import IdentityExtractionService
from .prompts import get_prompt_for_doc_type, get_supported_doc_types

__all__ = [
    "ExtractionResult",
    "IdentityExtractionService",
    "OCRExtractionError",
    "OllamaExtractionError",
    "get_prompt_for_doc_type",
    "get_supported_doc_types",
]
