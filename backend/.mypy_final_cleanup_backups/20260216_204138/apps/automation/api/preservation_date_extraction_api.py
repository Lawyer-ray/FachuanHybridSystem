"""API endpoints."""

from __future__ import annotations

"""
财产保全日期识别 API

提供从法院文书中提取财产保全措施到期时间的 API 端点.

Requirements: 2.1, 4.5, 5.1
"""

import logging
from typing import Any, Dict

from django.http import HttpRequest
from ninja import File, Router, Schema
from ninja.files import UploadedFile

from apps.core.infrastructure.throttling import rate_limit_from_settings

logger = logging.getLogger("apps.automation.api")

router = Router(tags=["财产保全日期识别"])


# ============================================================
# 工厂函数
# ============================================================


def _get_extraction_service() -> Any:
    """
    工厂函数:创建财产保全日期识别服务实例

    Returns:
        PreservationDateExtractionService 实例
    """
    from apps.automation.services.preservation_date import PreservationDateExtractionService

    return PreservationDateExtractionService()


# ============================================================
# 请求/响应 Schema
# ============================================================


class PreservationMeasureSchema(Schema):
    """
    保全措施信息

    表示从法院文书中识别到的单项保全措施.
    """

    measure_type: str  # 保全类型:查封/冻结/扣押/轮候查封/轮候冻结
    property_description: str  # 财产描述
    duration: str | None = None  # 期限:如"三年"、"一年"
    start_date: str | None = None  # 起算日期
    end_date: str | None = None  # 到期日期
    is_pending: bool = False  # 是否为轮候状态
    pending_note: str | None = None  # 轮候说明
    raw_text: str | None = None  # 原始文本片段


class ReminderDataSchema(Schema):
    """
    Reminder 格式数据

    用于生成重要日期提醒的数据结构.
    """

    reminder_type: str  # 固定为 "asset_preservation_expires"
    content: str  # 提醒内容
    due_at: str  # 到期时间 ISO 格式
    metadata: dict[str, Any]  # 扩展数据


class PreservationDateExtractionResponse(Schema):
    """
    财产保全日期识别响应

    包含识别到的保全措施列表和转换后的 Reminder 格式数据.
    """

    success: bool
    measures: list[PreservationMeasureSchema]  # 识别到的保全措施列表
    reminders: list[ReminderDataSchema]  # Reminder 格式数据
    model_used: str  # 使用的模型名称
    extraction_method: str  # 文本提取方式
    error: str | None = None  # 错误信息
    raw_response: str | None = None  # 大模型原始响应(调试用)


# ============================================================
# API 端点
# ============================================================


@router.post("/extract", response=PreservationDateExtractionResponse)
@rate_limit_from_settings("UPLOAD", by_user=True)
def extract_preservation_dates(
    request: HttpRequest,
    file: UploadedFile = File(...),
) -> PreservationDateExtractionResponse:
    """
    从上传的 PDF 文件中提取财产保全日期

    接受单个 PDF 文件上传,识别其中的财产保全措施并提取到期时间.

    Args:
        request: HTTP 请求
        file: 上传的 PDF 文件

    Returns:
        PreservationDateExtractionResponse: 提取结果

    Requirements: 2.1, 4.5, 5.1
    """
    service = _get_extraction_service()

    # 验证文件格式
    if not file.name.lower().endswith(".pdf"):
        logger.warning(
            "不支持的文件格式",
            extra={
                "file_name": file.name,
                "action": "extract_preservation_dates",
            },
        )
        return PreservationDateExtractionResponse(
            success=False,
            measures=[],
            reminders=[],
            model_used="",
            extraction_method="",
            error="不支持的文件格式,仅支持 PDF 文件",
        )

    # 委托服务层处理文件保存、提取和清理
    result = service.extract_from_uploaded_file(
        file_content_chunks=file.chunks(),
        file_name=file.name,
    )

    # 转换结果为响应格式
    measures: list[Any] = [
        PreservationMeasureSchema(
            measure_type=measure.measure_type,
            property_description=measure.property_description,
            duration=measure.duration,
            start_date=measure.start_date.strftime("%Y-%m-%d") if measure.start_date else None,
            end_date=measure.end_date.strftime("%Y-%m-%d") if measure.end_date else None,
            is_pending=measure.is_pending,
            pending_note=measure.pending_note,
            raw_text=measure.raw_text,
        )
        for measure in result.measures
    ]

    reminders: list[Any] = [
        ReminderDataSchema(
            reminder_type=reminder.reminder_type,
            content=reminder.content,
            due_at=reminder.due_at.isoformat() if reminder.due_at else "",
            metadata=reminder.metadata,
        )
        for reminder in result.reminders
    ]

    logger.info(
        "财产保全日期提取完成",
        extra={
            "measures_count": len(measures),
            "reminders_count": len(reminders),
            "model_used": result.model_used,
            "extraction_method": result.extraction_method,
        },
    )

    return PreservationDateExtractionResponse(
        success=result.success,
        measures=measures,
        reminders=reminders,
        model_used=result.model_used,
        extraction_method=result.extraction_method,
        error=result.error,
        raw_response=result.raw_response,
    )
