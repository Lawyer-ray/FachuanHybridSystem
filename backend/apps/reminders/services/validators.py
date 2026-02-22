"""Validation helpers for reminder services."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException
from apps.reminders.models import ReminderType


def normalize_target_id(value: int | None, *, field_name: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValidationException(_("%(field_name)s 必须为正整数") % {"field_name": field_name})
    return value


def validate_binding_exclusive(*, contract_id: int | None, case_log_id: int | None) -> None:
    has_contract = contract_id is not None
    has_case_log = case_log_id is not None
    if has_contract == has_case_log:
        raise ValidationException(_("必须且只能绑定合同或案件日志之一"))


def validate_fk_exists(*, contract_id: int | None, case_log_id: int | None) -> None:
    """校验外键引用的记录是否存在。"""
    if contract_id is not None:
        from apps.contracts.models import Contract

        if not Contract.objects.filter(id=contract_id).exists():
            raise ValidationException(_("合同 %(id)s 不存在") % {"id": contract_id})
    if case_log_id is not None:
        from apps.cases.models import CaseLog

        if not CaseLog.objects.filter(id=case_log_id).exists():
            raise ValidationException(_("案件日志 %(id)s 不存在") % {"id": case_log_id})


def normalize_reminder_type(reminder_type: str) -> str:
    value = str(reminder_type).strip()
    if not value:
        raise ValidationException(_("提醒类型不能为空"))
    if value not in ReminderType.values:
        raise ValidationException(_("无效的提醒类型"))
    return value


_CONTENT_MAX_LENGTH = 255


def normalize_content(content: str) -> str:
    value = str(content).strip()
    if not value:
        raise ValidationException(_("提醒事项不能为空"))
    if len(value) > _CONTENT_MAX_LENGTH:
        raise ValidationException(_("提醒事项不能超过 %(max)d 个字符") % {"max": _CONTENT_MAX_LENGTH})
    return value


def normalize_due_at(due_at: datetime) -> datetime:
    if not isinstance(due_at, datetime):
        raise ValidationException(_("到期时间格式不正确"))
    if timezone.is_naive(due_at):
        return timezone.make_aware(due_at)
    return due_at


def normalize_metadata(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValidationException(_("扩展数据必须为 JSON 对象"))
    return metadata
