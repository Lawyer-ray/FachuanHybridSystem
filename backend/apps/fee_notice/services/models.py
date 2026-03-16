"""Database models."""

from __future__ import annotations

from typing import Any

"""
交费通知书识别模块数据类定义

本模块定义了交费通知书识别和费用比对所需的所有数据类.
"""


from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class DetectionResult:
    """交费通知书检测结果"""

    is_fee_notice: bool  # 是否为交费通知书
    page_num: int  # 页码
    confidence: float  # 置信度 0-1
    matched_keywords: list[str]  # 匹配到的关键词
    raw_text: str = ""  # 原始文本(调试用)


@dataclass
class FeeAmountResult:
    """费用金额提取结果"""

    acceptance_fee: Decimal | None = None  # 受理费/案件受理费
    application_fee: Decimal | None = None  # 申请费(保全申请费等)
    preservation_fee: Decimal | None = None  # 保全费
    execution_fee: Decimal | None = None  # 执行费
    other_fee: Decimal | None = None  # 其他诉讼费
    total_fee: Decimal | None = None  # 总金额
    table_format: str = "unknown"  # 表格格式: horizontal/vertical/unknown
    debug_info: dict[str, Any] = field(default_factory=dict[str, Any])  # 调试信息


@dataclass
class FeeNoticeInfo:
    """单份交费通知书信息"""

    file_name: str  # 来源文件名
    file_path: str  # 文件路径
    page_num: int  # 页码
    detection: DetectionResult  # 检测结果
    amounts: FeeAmountResult  # 金额提取结果
    extraction_method: str  # 提取方式: pdf_direct/ocr


@dataclass
class FeeNoticeExtractionResult:
    """整体提取结果"""

    notices: list[FeeNoticeInfo]  # 所有识别到的通知书
    total_files: int  # 处理的文件数
    total_pages: int  # 处理的页面数
    errors: list[dict[str, Any]]  # 错误列表
    debug_logs: list[str] = field(default_factory=list)  # 调试日志


@dataclass
class CaseComparisonInfo:
    """案件比对信息"""

    case_id: int  # 案件ID
    case_name: str  # 案件名称
    case_number: str | None = None  # 案号
    cause_of_action_id: int | None = None  # 案由ID
    cause_of_action_name: str | None = None  # 案由名称
    target_amount: Decimal | None = None  # 诉讼标的金额
    preservation_amount: Decimal | None = None  # 保全金额
    is_complete: bool = False  # 信息是否完整(有案由和金额)
    incomplete_reason: str | None = None  # 信息不完整的原因


@dataclass
class CaseSearchResult:
    """案件搜索结果"""

    id: int  # 案件ID
    name: str  # 案件名称
    case_number: str | None = None  # 案号
    cause_of_action: str | None = None  # 案由名称
    target_amount: Decimal | None = None  # 诉讼标的金额


@dataclass
class FeeComparisonResult:
    """费用比对结果"""

    case_info: CaseComparisonInfo  # 案件信息
    # 提取金额
    extracted_acceptance_fee: Decimal | None = None
    extracted_preservation_fee: Decimal | None = None
    # 计算金额
    calculated_acceptance_fee: Decimal | None = None
    calculated_acceptance_fee_half: Decimal | None = None
    calculated_preservation_fee: Decimal | None = None
    # 比对结果
    acceptance_fee_match: bool = False  # 受理费是否一致
    acceptance_fee_close: bool = False  # 受理费是否视为一致(差异在容差范围内)
    acceptance_fee_diff: Decimal | None = None  # 受理费差异
    preservation_fee_match: bool = False  # 保全费是否一致
    preservation_fee_close: bool = False  # 保全费是否视为一致
    preservation_fee_diff: Decimal | None = None  # 保全费差异
    # 提示信息
    can_compare: bool = True  # 是否可以比对
    message: str | None = None  # 提示信息
