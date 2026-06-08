"""Reminders Admin 测试 - ReminderAdmin"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.reminders.admin.reminder_admin import ReminderAdmin
from apps.reminders.models import Reminder
from apps.cases.models import Case
from apps.contracts.models import Contract

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestReminderAdmin:
    """ReminderAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ReminderAdmin(Reminder, AdminSite())
        assert "id" in admin_obj.list_display

    def test_search_fields(self) -> None:
        """search_fields 包含 content"""
        admin_obj = ReminderAdmin(Reminder, AdminSite())
        assert "content" in admin_obj.search_fields

    def test_ordering(self) -> None:
        """ReminderAdmin 应有排序配置"""
        admin_obj = ReminderAdmin(Reminder, AdminSite())
        assert admin_obj.ordering is not None

    def test_reminder_with_case(self) -> None:
        """提醒关联案件"""
        contract = Contract.objects.create(name="提醒测试合同", case_type="civil")
        case = Case.objects.create(name="提醒测试案件", contract=contract)
        reminder = Reminder.objects.create(
            case=case,
            reminder_type="hearing",
            content="开庭提醒",
            due_at=timezone.now() + timedelta(days=7),
        )
        assert reminder.case.name == "提醒测试案件"
        assert reminder.reminder_type == "hearing"

    def test_reminder_with_contract(self) -> None:
        """提醒关联合同"""
        contract = Contract.objects.create(name="合同提醒测试", case_type="civil")
        reminder = Reminder.objects.create(
            contract=contract,
            reminder_type="payment_deadline",
            content="缴费提醒",
            due_at=timezone.now() + timedelta(days=3),
        )
        assert reminder.contract.name == "合同提醒测试"
        assert reminder.reminder_type == "payment_deadline"
