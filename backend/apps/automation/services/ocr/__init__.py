"""
OCR 服务模块

提供基于 PP-OCRv5 的高精度 OCR 识别能力.
"""

from .adapter import OCRServiceAdapter
from .ocr_service import OCRService, OCRTextResult, get_ocr_engine
from .recognition_result import RecognitionResult

__all__ = [
    "OCRService",
    "OCRServiceAdapter",
    "OCRTextResult",
    "RecognitionResult",
    "get_ocr_engine",
]
