"""Reminders Model 测试 - Reminder"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.reminders.models import Reminder, ReminderType
from apps.cases.models import Case
from apps.contracts.models import Contract


@pytest.mark.django_db
class TestReminderModel:
    """Reminder 模型测试"""

    def test_create_reminder_with_case(self) -> None:
        """创建提醒关联案件"""
        contract = Contract.objects.create(name="提醒模型测试合同", case_type="civil")
        case = Case.objects.create(name="提醒模型测试案件", contract=contract)
        reminder = Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.HEARING,
            content="开庭提醒",
            due_at=timezone.now() + timedelta(days=7),
        )
        assert reminder.content == "开庭提醒"
        assert reminder.reminder_type == ReminderType.HEARING

    def test_create_reminder_with_contract(self) -> None:
        """创建提醒关联合同"""
        contract = Contract.objects.create(name="合同提醒测试", case_type="civil")
        reminder = Reminder.objects.create(
            contract=contract,
            reminder_type=ReminderType.PAYMENT_DEADLINE,
            content="缴费提醒",
            due_at=timezone.now() + timedelta(days=3),
        )
        assert reminder.content == "缴费提醒"
        assert reminder.contract.name == "合同提醒测试"

    def test_reminder_type_choices(self) -> None:
        """提醒类型选项应完整"""
        assert ReminderType.HEARING == "hearing"
        assert ReminderType.ASSET_PRESERVATION_EXPIRES == "asset_preservation_expires"
        assert ReminderType.EVIDENCE_DEADLINE == "evidence_deadline"
        assert ReminderType.APPEAL_DEADLINE == "appeal_deadline"
        assert ReminderType.STATUTE_LIMITATIONS == "statute_limitations"
        assert ReminderType.PAYMENT_DEADLINE == "payment_deadline"
        assert ReminderType.SUBMISSION_DEADLINE == "submission_deadline"
        assert ReminderType.OTHER == "other"

    def test_reminder_with_metadata(self) -> None:
        """创建提醒包含元数据"""
        contract = Contract.objects.create(name="元数据提醒测试", case_type="civil")
        case = Case.objects.create(name="元数据提醒案件", contract=contract)
        metadata = {"source": "auto", "priority": "high"}
        reminder = Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.OTHER,
            content="元数据提醒",
            due_at=timezone.now() + timedelta(days=1),
            metadata=metadata,
        )
        assert reminder.metadata == metadata

    def test_reminder_include_in_important_time(self) -> None:
        """创建提醒包含重要时间标记"""
        contract = Contract.objects.create(name="重要时间提醒测试", case_type="civil")
        case = Case.objects.create(name="重要时间提醒案件", contract=contract)
        reminder = Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.HEARING,
            content="重要时间提醒",
            due_at=timezone.now() + timedelta(days=5),
            include_in_important_time=True,
        )
        assert reminder.include_in_important_time is True
