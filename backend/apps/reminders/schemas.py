"""API schemas and serializers."""

from datetime import datetime
from typing import Any

from ninja import Schema
from pydantic import Field, field_validator, model_validator

from apps.core.api.schemas import SchemaMixin

from .models import Reminder, ReminderType
from .services.validators import _CONTENT_MAX_LENGTH


def _validate_positive_id(value: int | None) -> int | None:
    if value is not None and (isinstance(value, bool) or value <= 0):
        raise ValueError("ID 必须为正整数")
    return value


def _validate_content_not_blank(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("提醒事项不能为空")
    return normalized


class ReminderIn(Schema):
    contract_id: int | None = None
    case_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType
    content: str = Field(max_length=_CONTENT_MAX_LENGTH)
    due_at: datetime
    metadata: dict[str, Any] | None = None

    _validate_ids = field_validator("contract_id", "case_id", "case_log_id")(_validate_positive_id)
    _validate_content = field_validator("content")(_validate_content_not_blank)

    @model_validator(mode="after")
    def validate_binding_exclusivity(self) -> "ReminderIn":
        selected_count = sum(target_id is not None for target_id in (self.contract_id, self.case_id, self.case_log_id))
        if selected_count > 1:
            raise ValueError("合同、案件、案件日志最多只能绑定一个")
        return self


class ReminderUpdate(Schema):
    contract_id: int | None = None
    case_id: int | None = None
    case_log_id: int | None = None
    reminder_type: ReminderType | None = None
    content: str | None = Field(None, max_length=_CONTENT_MAX_LENGTH)
    due_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    _validate_ids = field_validator("contract_id", "case_id", "case_log_id")(_validate_positive_id)
    _validate_content = field_validator("content")(_validate_content_not_blank)


class ReminderOut(SchemaMixin, Schema):
    id: int
    contract: int | None = None
    case: int | None = None
    case_log: int | None = None
    reminder_type: str
    reminder_type_label: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    due_at: str
    created_at: str
    updated_at: str

    @staticmethod
    def resolve_contract(obj: Reminder) -> int | None:
        return obj.contract_id

    @staticmethod
    def resolve_case(obj: Reminder) -> int | None:
        return obj.case_id

    @staticmethod
    def resolve_case_log(obj: Reminder) -> int | None:
        return obj.case_log_id

    @staticmethod
    def resolve_reminder_type_label(obj: Reminder) -> str:
        return SchemaMixin._get_display(obj, "reminder_type") or ""

    @staticmethod
    def resolve_due_at(obj: Reminder) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.due_at) or ""

    @staticmethod
    def resolve_created_at(obj: Reminder) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.created_at) or ""

    @staticmethod
    def resolve_updated_at(obj: Reminder) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.updated_at) or ""


class ParsedReminderOut(Schema):
    """从文本解析出的提醒条目。"""

    content: str
    reminder_type: str
    reminder_type_label: str
    due_at: str
    source_text: str


class ParseReminderIn(Schema):
    """解析提醒请求。"""

    text: str


class ReminderTypeItem(Schema):
    value: str
    label: str


def list_reminder_types() -> list[ReminderTypeItem]:
    return [ReminderTypeItem(value=value, label=str(label)) for value, label in ReminderType.choices]


class TargetOptionItem(Schema):
    id: int
    name: str
    target_type: str
    target_type_label: str


class TargetOptionGroup(Schema):
    key: str
    label: str
    items: list[TargetOptionItem]


class TargetOptionsOut(Schema):
    items: list[TargetOptionItem]
    groups: list[TargetOptionGroup]


# ─── 日历视图 ───────────────────────────────────────────────────────────────


class CalendarEventItemOut(Schema):
    """日历上的一条事件（同一庭审的多条同步已合并成一条）。"""

    id: int
    kind: str
    kind_label: str
    #: 主标题：优先关联对象名，取不到才退回 content
    title: str
    #: content 原文（title 用了案名时仍保留，便于核对）
    content: str
    day: str
    time: str
    time_range: str
    place: str
    person: str
    case_no: str
    hearing_type: str
    target_type: str
    target_name: str
    case_id: int | None = None
    is_today: bool = False
    is_overdue: bool = False
    #: 合并了几条原始 reminder（同一庭审被多次同步时 >1）
    members: int = 1
    #: 合并前各 reminder 的 id
    member_ids: list[int] = Field(default_factory=list)


class CalendarStatsOut(Schema):
    """工作台头部统计（基于合并后口径）。"""

    today: int = 0
    deadline_in_7days: int = 0
    month_court: int = 0


class CalendarMonthOut(Schema):
    """一个月的日历视图。"""

    year: int
    month: int
    stats: CalendarStatsOut = Field(default_factory=CalendarStatsOut)
    #: YYYY-MM-DD → 当日事件（已合并、已排序）
    days: dict[str, list[CalendarEventItemOut]] = Field(default_factory=dict)
