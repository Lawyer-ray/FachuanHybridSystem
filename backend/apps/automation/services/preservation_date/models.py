"""Database models."""

from __future__ import annotations

from typing import Any

"""
财产保全日期识别模块数据类定义

本模块定义了财产保全日期识别所需的所有数据类.
"""


from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PreservationMeasure:
    """
    财产保全措施

    表示从法院文书中识别到的单项保全措施信息.

    Attributes:
        measure_type: 保全类型(查封/冻结/扣押/轮候查封/轮候冻结等)
        property_description: 被保全财产的描述(如不动产地址、银行账号等)
        duration: 保全期限(如"三年"、"一年"等)
        start_date: 起算日期
        end_date: 到期日期
        is_pending: 是否为轮候状态
        pending_note: 轮候说明(如"自转为正式查封/冻结之日起计算")
        raw_text: 原始文本片段(供核对)
    """

    measure_type: str  # 保全类型
    property_description: str  # 财产描述
    duration: str | None = None  # 期限
    start_date: datetime | None = None  # 起算日期
    end_date: datetime | None = None  # 到期日期
    is_pending: bool = False  # 是否轮候
    pending_note: str | None = None  # 轮候说明
    raw_text: str | None = None  # 原始文本


@dataclass
class ReminderData:
    """
    Reminder 格式数据

    用于生成重要日期提醒的数据结构,兼容系统中的 Reminder 模型.

    Attributes:
        reminder_type: 提醒类型,固定为 "asset_preservation_expires"
        content: 提醒内容,描述保全措施详情
        due_at: 到期时间
        metadata: 扩展数据,存储保全措施类型、财产描述等信息
    """

    reminder_type: str = "asset_preservation_expires"
    content: str = ""
    due_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreservationExtractionResult:
    """
    提取结果

    表示财产保全日期识别的完整结果.

    Attributes:
        success: 是否成功
        measures: 识别到的保全措施列表
        reminders: 转换后的 Reminder 格式数据列表
        model_used: 使用的大模型名称
        extraction_method: 文本提取方式(pdf_direct/ocr)
        error: 错误信息
        raw_response: 大模型原始响应(调试用)
    """

    success: bool
    measures: list[PreservationMeasure] = field(default_factory=list)
    reminders: list[ReminderData] = field(default_factory=list)
    model_used: str = ""
    extraction_method: str = ""
    error: str | None = None
    raw_response: str | None = None  # 原始响应(调试用)
