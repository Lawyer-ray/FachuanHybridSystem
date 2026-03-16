"""
图片自动旋转模块

提供图片 EXIF 方向识别、旋转处理、PDF 页面提取和导出功能.
"""

from .auto_rename_service import AutoRenameService, ExtractionResult, RenameSuggestion
from .facade import ImageRotationService
from .orientation.service import OrientationDetectionService
from .pdf_extraction_service import PDFExtractionService

__all__ = [
    "AutoRenameService",
    "ExtractionResult",
    "ImageRotationService",
    "OrientationDetectionService",
    "PDFExtractionService",
    "RenameSuggestion",
]
