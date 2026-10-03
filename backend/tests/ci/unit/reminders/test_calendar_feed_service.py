"""Tests for apps.reminders.services.calendar_feed_service（calendar_feed_api 下沉的 ORM/渲染逻辑）."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.reminders.models import CalendarFeedToken, ReminderType
from apps.reminders.services.calendar_feed_service import CalendarFeedService
from apps.testing.factories import LawyerFactory


@pytest.mark.django_db
class TestFetchFeedData:
    def test_invalid_token_returns_none(self):
        assert CalendarFeedService().fetch_feed_data("no-such-token") is None

    def test_valid_token_returns_user_and_reminders(self):
        user = LawyerFactory()
        CalendarFeedToken.objects.create(user=user, token="tok-valid-123")

        result = CalendarFeedService().fetch_feed_data("tok-valid-123")

        assert result is not None
        feed_user, reminders = result
        assert feed_user.id == user.id
        assert reminders == []


@pytest.mark.django_db
class TestGetOrCreateToken:
    def test_creates_then_reuses(self):
        user = LawyerFactory()
        svc = CalendarFeedService()

        first = svc.get_or_create_token(user)
        second = svc.get_or_create_token(user)

        assert first.pk == second.pk
        assert first.token
        assert CalendarFeedToken.objects.filter(user=user).count() == 1


@pytest.mark.django_db
class TestRegenerateToken:
    def test_creates_when_missing(self):
        user = LawyerFactory()

        result = CalendarFeedService().regenerate_token(user)

        assert result.token
        assert CalendarFeedToken.objects.filter(user=user).count() == 1

    def test_replaces_existing_token(self):
        user = LawyerFactory()
        CalendarFeedToken.objects.create(user=user, token="old-token")

        result = CalendarFeedService().regenerate_token(user)

        assert result.token != "old-token"
        old = CalendarFeedToken.objects.get(user=user)
        assert old.token == result.token
        # 旧 token 立即失效
        assert CalendarFeedService().fetch_feed_data("old-token") is None
        assert CalendarFeedService().fetch_feed_data(result.token) is not None


class TestRenderIcsFeed:
    def _reminder(self, **overrides):
        defaults = {
            "id": 1,
            "due_at": timezone.now(),
            "content": "开庭提醒",
            "reminder_type": ReminderType.HEARING,
            "metadata": {},
            "contract_id": None,
            "contract": None,
            "case_id": None,
            "case": None,
            "case_log_id": None,
            "case_log": None,
            "is_completed": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_renders_vcalendar_with_event_and_alarm(self):
        ics = CalendarFeedService().render_ics_feed([self._reminder()], "张律师")

        text = ics.decode("utf-8")
        assert text.startswith("BEGIN:VCALENDAR")
        assert "法穿提醒 - 张律师" in text
        assert "开庭提醒" in text
        # 开庭提醒带提前 1 天的 DISPLAY 闹钟
        assert "BEGIN:VALARM" in text
        assert "ACTION:DISPLAY" in text

    def test_invalid_end_at_falls_back_to_one_hour(self):
        r = self._reminder(metadata={"end_at": "not-a-datetime"})

        ics = CalendarFeedService().render_ics_feed([r], "张律师")

        # end_at 解析失败时回退 due_at + 1h，仍渲染出完整事件
        assert b"BEGIN:VEVENT" in ics
        assert b"END:VALARM" in ics

    def test_non_hearing_has_no_alarm(self):
        r = self._reminder(reminder_type=ReminderType.OTHER)

        ics = CalendarFeedService().render_ics_feed([r], "张律师")

        assert b"BEGIN:VEVENT" in ics
        assert b"BEGIN:VALARM" not in ics
