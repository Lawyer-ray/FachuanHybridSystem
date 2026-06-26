"""OCR 相关类型定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OCRTextResult:
    """OCR 文本识别结果"""

    text: str  # 合并后的文本(用 | 分隔)
    raw_texts: list[str]  # 原始文本列表
