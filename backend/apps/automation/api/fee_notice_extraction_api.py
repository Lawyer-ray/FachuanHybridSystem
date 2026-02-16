"""API endpoints."""

from __future__ import annotations

"""
交费通知书识别 API

提供交费通知书识别和费用提取的 API 端点.

Requirements: 1.1, 2.1, 5.1-5.5
"""

import logging
import uuid
from typing import Any, ClassVar

from django.http import HttpRequest
from ninja import File, Router, Schema
from ninja.files import UploadedFile

logger = logging.getLogger("apps.automation.api")

router = Router(tags=["交费通知书识别"])


# ============================================================
# 工厂函数
# ============================================================


def _get_extraction_service() -> Any:
    """
    工厂函数:创建交费通知书识别服务实例

    Returns:
        FeeNoticeExtractionService 实例
    """
    from apps.automation.services.fee_notice import FeeNoticeExtractionService

    return FeeNoticeExtractionService()


def _get_comparison_service() -> Any:
    """
    工厂函数:创建费用比对服务实例

    Returns:
        FeeComparisonService 实例
    """
    from apps.automation.services.fee_notice import FeeComparisonService

    return FeeComparisonService()


# ============================================================
# 请求/响应 Schema
# ============================================================


class FeeNoticeExtractionRequest(Schema):
    """费用提取请求"""

    debug: bool = False  # 是否输出调试信息


class FeeItemSchema(Schema):
    """费用项"""

    name: str  # 费用名称
    amount: float | None = None  # 金额
    source_text: str | None = None  # 来源文本(调试用)


class FeeNoticeSchema(Schema):
    """交费通知书信息"""

    file_name: str  # 来源文件名
    page_num: int  # 页码
    acceptance_fee: float | None = None  # 受理费/案件受理费
    application_fee: float | None = None  # 申请费(保全申请费等)
    preservation_fee: float | None = None  # 保全费
    execution_fee: float | None = None  # 执行费
    other_fee: float | None = None  # 其他诉讼费
    total_fee: float | None = None  # 总金额
    extraction_method: str  # 提取方式
    confidence: float  # 置信度
    debug_info: dict[str, Any] | None = None  # 调试信息


class FeeNoticeExtractionResponse(Schema):
    """费用提取响应"""

    success: bool
    notices: list[FeeNoticeSchema]  # 识别到的交费通知书列表
    total_files: int  # 处理的文件总数
    total_notices: int  # 识别到的通知书数量
    errors: ClassVar[list[dict[str, Any]]] = []  # 错误信息列表
    debug_logs: list[str] | None = None  # 调试日志


class CaseSearchResultSchema(Schema):
    """案件搜索结果"""

    id: int  # 案件ID
    name: str  # 案件名称
    case_number: str | None = None  # 案号
    cause_of_action: str | None = None  # 案由名称
    target_amount: float | None = None  # 诉讼标的金额


class CaseSearchResponse(Schema):
    """案件搜索响应"""

    success: bool
    cases: list[CaseSearchResultSchema]


class FeeComparisonRequest(Schema):
    """费用比对请求"""

    case_id: int  # 案件ID
    extracted_acceptance_fee: float | None = None  # 提取的受理费
    extracted_preservation_fee: float | None = None  # 提取的保全费


class FeeComparisonResponse(Schema):
    """费用比对响应"""

    success: bool
    case_name: str  # 案件名称
    case_number: str | None = None  # 案号
    cause_of_action: str | None = None  # 案由名称
    target_amount: float | None = None  # 诉讼标的金额
    # 提取金额
    extracted_acceptance_fee: float | None = None
    extracted_preservation_fee: float | None = None
    # 计算金额
    calculated_acceptance_fee: float | None = None
    calculated_acceptance_fee_half: float | None = None
    calculated_preservation_fee: float | None = None
    # 比对结果
    acceptance_fee_match: bool  # 受理费是否一致
    acceptance_fee_close: bool = False  # 受理费是否视为一致(差异在1元内)
    acceptance_fee_diff: float | None = None  # 受理费差异
    preservation_fee_match: bool  # 保全费是否一致
    preservation_fee_close: bool = False  # 保全费是否视为一致(差异在1元内)
    preservation_fee_diff: float | None = None  # 保全费差异
    # 提示信息
    message: str | None = None  # 提示信息(如案件信息不完整)


# ============================================================
# API 端点
# ============================================================


def extract_fee_notices(
    request: HttpRequest,
    files: list[UploadedFile] = File(...),  # type: ignore[type-arg]
    debug: bool = False,
) -> FeeNoticeExtractionResponse:
    """从上传的 PDF 文件中提取交费通知书信息"""
    service = _get_extraction_service()

    batch_id = uuid.uuid4().hex[:8]
    logger.info("开始处理交费通知书提取请求", extra={"batch_id": batch_id, "file_count": len(files), "debug": debug})

    saved_files, file_errors = service.save_uploaded_files(files, temp_dir_name="fee_notice", batch_id=batch_id)

    if not saved_files:
        return FeeNoticeExtractionResponse(  # type: ignore[call-arg]
            success=False,
            notices=[],
            total_files=len(files),
            total_notices=0,
            errors=file_errors,
            debug_logs=[] if debug else None,
        )

    result = service.extract_from_files(file_paths=[str(p) for p in saved_files], debug=debug)
    service.cleanup_temp_files(saved_files)

    all_errors = file_errors + result.errors
    notices: list[Any] = []

    logger.info(
        "交费通知书提取完成",
        extra={
            "batch_id": batch_id,
            "total_files": len(files),
            "total_notices": len(notices),
            "errors_count": len(all_errors),
        },
    )

    return FeeNoticeExtractionResponse(  # type: ignore[call-arg]
        success=len(all_errors) == 0 or len(notices) > 0,
        notices=notices,
        total_files=len(files),
        total_notices=len(notices),
        errors=all_errors,
        debug_logs=result.debug_logs if debug else None,
    )


def _convert_notice_to_schema(notice: Any, debug: bool) -> FeeNoticeSchema:
    """将提取结果转换为响应 Schema"""
    return FeeNoticeSchema(
        file_name=notice.file_name,
        page_num=notice.page_num,
        acceptance_fee=float(notice.amounts.acceptance_fee) if notice.amounts.acceptance_fee else None,
        application_fee=float(notice.amounts.application_fee) if notice.amounts.application_fee else None,
        preservation_fee=float(notice.amounts.preservation_fee) if notice.amounts.preservation_fee else None,
        execution_fee=float(notice.amounts.execution_fee) if notice.amounts.execution_fee else None,
        other_fee=float(notice.amounts.other_fee) if notice.amounts.other_fee else None,
        total_fee=float(notice.amounts.total_fee) if notice.amounts.total_fee else None,
        extraction_method=notice.extraction_method,
        confidence=notice.detection.confidence,
        debug_info=notice.amounts.debug_info if debug else None,
    )


@router.get("/cases/search", response=CaseSearchResponse)
def search_cases(request: HttpRequest, keyword: str = "") -> CaseSearchResponse:
    """
    搜索案件(用于下拉框)

    支持按案件名称或案号搜索,返回匹配的案件列表.

    Args:
        request: HTTP 请求
        keyword: 搜索关键词(案件名称或案号)

    Returns:
        CaseSearchResponse: 案件搜索结果

    Requirements: 8.1
    """
    service = _get_comparison_service()

    logger.info(
        "案件搜索请求",
        extra={
            "keyword": keyword,
            "action": "search_cases",
        },
    )

    # 调用服务搜索案件
    results = service.search_cases(keyword=keyword, limit=20)

    # 转换为响应格式
    cases: list[Any] = [
        CaseSearchResultSchema(
            id=result.id,
            name=result.name,
            case_number=result.case_number,
            cause_of_action=result.cause_of_action,
            target_amount=float(result.target_amount) if result.target_amount else None,
        )
        for result in results
    ]

    return CaseSearchResponse(
        success=True,
        cases=cases,
    )


@router.post("/compare", response=FeeComparisonResponse)
def compare_fee(request: HttpRequest, payload: FeeComparisonRequest) -> FeeComparisonResponse:
    """
    比对提取金额与系统计算金额

    将PDF提取的费用金额与系统根据案件信息计算的预期金额进行比对.

    Args:
        request: HTTP 请求
        payload: 费用比对请求,包含案件ID和提取的费用金额

    Returns:
        FeeComparisonResponse: 比对结果

    Requirements: 8.3, 8.4
    """
    from decimal import Decimal

    service = _get_comparison_service()

    logger.info(
        "费用比对请求",
        extra={
            "case_id": payload.case_id,
            "extracted_acceptance_fee": payload.extracted_acceptance_fee,
            "extracted_preservation_fee": payload.extracted_preservation_fee,
            "action": "compare_fee",
        },
    )

    # 转换 float 为 Decimal
    extracted_acceptance_fee = (
        Decimal(str(payload.extracted_acceptance_fee)) if payload.extracted_acceptance_fee is not None else None
    )
    extracted_preservation_fee = (
        Decimal(str(payload.extracted_preservation_fee)) if payload.extracted_preservation_fee is not None else None
    )

    # 调用服务进行比对
    result = service.compare_fee(
        case_id=payload.case_id,
        extracted_acceptance_fee=extracted_acceptance_fee,
        extracted_preservation_fee=extracted_preservation_fee,
    )

    # 转换 Decimal 为 float 用于 JSON 序列化
    def to_float(value: Decimal | None) -> float | None:
        return float(value) if value is not None else None

    return FeeComparisonResponse(
        success=True,
        case_name=result.case_info.case_name,
        case_number=result.case_info.case_number,
        cause_of_action=result.case_info.cause_of_action_name,
        target_amount=to_float(result.case_info.target_amount),
        # 提取金额
        extracted_acceptance_fee=to_float(result.extracted_acceptance_fee),
        extracted_preservation_fee=to_float(result.extracted_preservation_fee),
        # 计算金额
        calculated_acceptance_fee=to_float(result.calculated_acceptance_fee),
        calculated_acceptance_fee_half=to_float(result.calculated_acceptance_fee_half),
        calculated_preservation_fee=to_float(result.calculated_preservation_fee),
        # 比对结果
        acceptance_fee_match=result.acceptance_fee_match,
        acceptance_fee_close=result.acceptance_fee_close,
        acceptance_fee_diff=to_float(result.acceptance_fee_diff),
        preservation_fee_match=result.preservation_fee_match,
        preservation_fee_close=result.preservation_fee_close,
        preservation_fee_diff=to_float(result.preservation_fee_diff),
        # 提示信息
        message=result.message,
    )
