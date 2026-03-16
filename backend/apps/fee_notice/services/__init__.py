"""
交费通知书识别服务模块

本模块提供从法院PDF文件中自动提取受理费金额的功能,包括:
- FeeNoticeDetector: 交费通知书检测器
- FeeAmountExtractor: 费用金额提取器
- FeeNoticeExtractionService: 主服务,协调整个识别流程
- FeeComparisonService: 费用比对服务

使用示例:
    from apps.fee_notice.services import FeeNoticeExtractionService

    service = FeeNoticeExtractionService()
    result = service.extract_from_files(file_paths, debug=True)
"""

from __future__ import annotations

from typing import Any

__all__ = [
    # 数据类
    "DetectionResult",
    "FeeAmountResult",
    "FeeNoticeInfo",
    "FeeNoticeExtractionResult",
    "CaseComparisonInfo",
    "CaseSearchResult",
    "FeeComparisonResult",
    "FeeCheckItem",
    "FeeCheckResult",
    # 服务类
    "FeeNoticeDetector",
    "FeeAmountExtractor",
    "FeeNoticeExtractionService",
    "FeeComparisonService",
    "FeeNoticeCheckService",
]


# 延迟导入,避免循环依赖
def __getattr__(name: str) -> Any:
    if name in (
        "DetectionResult",
        "FeeAmountResult",
        "FeeNoticeInfo",
        "FeeNoticeExtractionResult",
        "CaseComparisonInfo",
        "CaseSearchResult",
        "FeeComparisonResult",
    ):
        from .models import (
            CaseComparisonInfo,
            CaseSearchResult,
            DetectionResult,
            FeeAmountResult,
            FeeComparisonResult,
            FeeNoticeExtractionResult,
            FeeNoticeInfo,
        )

        return locals()[name]

    if name in ("FeeCheckItem", "FeeCheckResult"):
        from .check_service import FeeCheckItem, FeeCheckResult

        return locals()[name]

    if name == "FeeNoticeDetector":
        from .detector import FeeNoticeDetector

        return FeeNoticeDetector

    if name == "FeeAmountExtractor":
        from .extractor import FeeAmountExtractor

        return FeeAmountExtractor

    if name == "FeeNoticeExtractionService":
        from .extraction_service import FeeNoticeExtractionService

        return FeeNoticeExtractionService

    if name == "FeeComparisonService":
        from .comparison_service import FeeComparisonService

        return FeeComparisonService

    if name == "FeeNoticeCheckService":
        from .check_service import FeeNoticeCheckService

        return FeeNoticeCheckService

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
