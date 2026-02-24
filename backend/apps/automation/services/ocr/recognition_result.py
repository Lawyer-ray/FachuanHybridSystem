from __future__ import annotations

from dataclasses import dataclass

from .invoice_parser import ParsedInvoice


@dataclass
class RecognitionResult:
    """发票识别结果数据类
    
    用于表示单个发票文件的识别结果，包含文件名、成功状态、
    解析后的发票数据或错误信息。
    
    Attributes:
        filename: 原始文件名
        success: 识别是否成功
        data: 识别成功时的解析结果（ParsedInvoice 对象）
        error: 识别失败时的错误信息
    """

    filename: str
    success: bool
    data: ParsedInvoice | None = None
    error: str | None = None
