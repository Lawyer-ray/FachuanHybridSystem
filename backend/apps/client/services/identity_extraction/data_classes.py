"""
证件信息提取相关数据类
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractionResult:
    """证件信息提取结果"""

    doc_type: str  # 证件类型
    raw_text: str  # OCR 原始文本
    extracted_data: dict[str, Any]  # 提取的结构化数据
    confidence: float  # 置信度 (0-1)
    extraction_method: str  # 提取方式


class OCRExtractionError(Exception):
    """OCR 文字提取失败异常"""

    pass


class OllamaExtractionError(Exception):
    """Ollama 信息提取失败异常"""

    pass
