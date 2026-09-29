"""
OCR 服务模块

提供基于 PP-OCRv5 的高精度 OCR 识别能力.
支持本地 RapidOCR、macOS Vision（darwin）和 PaddleOCR API 引擎.
"""

from .adapter import OCRServiceAdapter
from .mac_vision import MacVisionOCREngine, is_mac_vision_available
from .ocr_service import OCRService, OCRTextResult, get_ocr_engine
from .paddleocr_api_service import PaddleOCRApiEngine, PaddleOCRApiResult

__all__ = [
    "MacVisionOCREngine",
    "OCRService",
    "OCRServiceAdapter",
    "OCRTextResult",
    "PaddleOCRApiEngine",
    "PaddleOCRApiResult",
    "get_ocr_engine",
    "is_mac_vision_available",
]
