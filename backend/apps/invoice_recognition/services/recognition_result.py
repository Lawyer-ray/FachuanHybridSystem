from __future__ import annotations

from dataclasses import dataclass

from .invoice_parser import ParsedInvoice


@dataclass
class RecognitionResult:
    """发票识别结果数据类。"""

    filename: str
    success: bool
    data: ParsedInvoice | None = None
    error: str | None = None
