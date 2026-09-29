"""Tests for ReminderService covering CRUD, validation, and normalization."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.reminders.models import Reminder
from apps.reminders.services.reminder_service import ReminderService
from apps.reminders.services.validators import (
    normalize_content,
    normalize_due_at,
    normalize_metadata,
    normalize_reminder_type,
    normalize_target_id,
)

# ── validators ──


class TestNormalizeTargetId:
    def test_none(self):
        assert normalize_target_id(None, field_name="contract_id") is None

    def test_positive_int(self):
        assert normalize_target_id(42, field_name="contract_id") == 42

    def test_zero_raises(self):
        with pytest.raises(ValidationException, match="必须为正整数"):
            normalize_target_id(0, field_name="contract_id")

    def test_negative_raises(self):
        with pytest.raises(ValidationException, match="必须为正整数"):
            normalize_target_id(-1, field_name="contract_id")

    def test_string_int(self):
        # String is not int, so it raises
        with pytest.raises(ValidationException):
            normalize_target_id("10", field_name="contract_id")

    def test_invalid_string_raises(self):
        with pytest.raises(ValidationException):
            normalize_target_id("abc", field_name="contract_id")


class TestNormalizeContent:
    def test_valid_content(self):
        result = normalize_content("提醒内容")
        assert result == "提醒内容"

    def test_empty_raises(self):
        with pytest.raises(ValidationException):
            normalize_content("")

    def test_whitespace_stripped(self):
        result = normalize_content("  内容  ")
        assert result == "内容"


class TestNormalizeReminderType:
    def test_valid_type(self):
        result = normalize_reminder_type("hearing")
        assert result == "hearing"

    def test_empty_raises(self):
        with pytest.raises(ValidationException, match="不能为空"):
            normalize_reminder_type("")

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationException, match="无效的提醒类型"):
            normalize_reminder_type("nonexistent_type")


class TestNormalizeDueAt:
    def test_valid_datetime(self):
        dt = timezone.now()
        result = normalize_due_at(dt)
        assert result == dt

    def test_none_raises(self):
        with pytest.raises(ValidationException, match="格式不正确"):
            normalize_due_at(None)

    def test_naive_datetime_made_aware(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)
        result = normalize_due_at(naive)
        assert timezone.is_aware(result)


class TestNormalizeMetadata:
    def test_none_returns_empty(self):
        assert normalize_metadata(None) == {}

    def test_dict_passes(self):
        meta = {"key": "value"}
        result = normalize_metadata(meta)
        assert result == meta

    def test_non_dict_raises(self):
        with pytest.raises(ValidationException, match="JSON 对象"):
            normalize_metadata("not a dict")


# ── ReminderService ──


class TestReminderServiceList:
    @pytest.mark.django_db
    def test_list_all(self):
        svc = ReminderService()
        result = svc.list_reminders()
        assert result is not None

    @pytest.mark.django_db
    def test_list_with_contract_id(self):
        svc = ReminderService()
        result = svc.list_reminders(contract_id=1)
        assert result is not None

    @pytest.mark.django_db
    def test_list_with_case_id(self):
        svc = ReminderService()
        result = svc.list_reminders(case_id=1)
        assert result is not None

    @pytest.mark.django_db
    def test_list_multi_filter_raises(self):
        svc = ReminderService()
        with pytest.raises(ValidationException, match="不能同时"):
            svc.list_reminders(contract_id=1, case_id=2)


class TestReminderServiceGet:
    @pytest.mark.django_db
    def test_get_nonexistent_raises(self):
        svc = ReminderService()
        with pytest.raises(NotFoundError):
            svc.get_reminder(999999)


class TestReminderServiceDelete:
    @pytest.mark.django_db
    def test_delete_nonexistent_raises(self):
        svc = ReminderService()
        with pytest.raises(NotFoundError):
            svc.delete_reminder(999999)


class TestReminderServiceSetCompleted:
    """批量完成：落库 / 幂等 / 不变量 / simple_history 审计。"""

    @pytest.mark.django_db
    def test_marks_batch_and_records_user(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="completer")
        r1 = Reminder.objects.create(reminder_type="hearing", content="庭1", due_at=timezone.now())
        r2 = Reminder.objects.create(reminder_type="hearing", content="庭2", due_at=timezone.now())

        updated = ReminderService().set_completed([r1.id, r2.id], completed=True, user=user)

        assert updated == 2
        for rid in (r1.id, r2.id):
            fresh = Reminder.objects.get(id=rid)
            assert fresh.is_completed is True
            assert fresh.completed_at is not None
            assert fresh.completed_by_id == user.id

    @pytest.mark.django_db
    def test_records_history_per_save(self):
        """逐条 save 而非 bulk update：simple_history 只在 save() 记历史。"""
        r = Reminder.objects.create(reminder_type="hearing", content="庭", due_at=timezone.now())
        assert r.history.count() == 1  # create

        ReminderService().set_completed([r.id], completed=True)

        assert r.history.count() == 2
        latest = r.history.latest()
        assert latest.is_completed is True

    @pytest.mark.django_db
    def test_unset_clears_fields(self):
        r = Reminder.objects.create(reminder_type="hearing", content="庭", due_at=timezone.now())
        ReminderService().set_completed([r.id], completed=True)

        updated = ReminderService().set_completed([r.id], completed=False)

        assert updated == 1
        fresh = Reminder.objects.get(id=r.id)
        assert fresh.is_completed is False
        assert fresh.completed_at is None
        assert fresh.completed_by_id is None

    @pytest.mark.django_db
    def test_skips_unknown_ids_silently(self):
        r = Reminder.objects.create(reminder_type="hearing", content="庭", due_at=timezone.now())

        updated = ReminderService().set_completed([r.id, 999999], completed=True)

        assert updated == 1
        assert Reminder.objects.get(id=r.id).is_completed is True

    @pytest.mark.django_db
    def test_empty_or_invalid_ids_raise(self):
        with pytest.raises(ValidationException, match="不能为空"):
            ReminderService().set_completed([], completed=True)
        with pytest.raises(ValidationException, match="不能为空"):
            ReminderService().set_completed([0, -1], completed=True)

    @pytest.mark.django_db
    def test_list_reminders_by_ids(self):
        r1 = Reminder.objects.create(reminder_type="hearing", content="庭1", due_at=timezone.now())
        r2 = Reminder.objects.create(reminder_type="hearing", content="庭2", due_at=timezone.now())

        found = ReminderService().list_reminders_by_ids([r1.id, r2.id, 999999, 0])

        assert {r.id for r in found} == {r1.id, r2.id}
