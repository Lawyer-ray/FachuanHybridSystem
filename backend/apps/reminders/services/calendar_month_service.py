"""按月取日历视图：查询 + 归一化 + 合并 + 统计。

与 calendar_view_service 的分工：
  - calendar_view_service：纯逻辑（归一化 / 合并 / 统计），可脱离 DB 单测
  - 本模块：ORM 查询与装配，产出「日 → 事件」与统计

首页工作台（GET /reminders/calendar）与 Django admin 日历共用此处，
保证两处口径永远一致。
"""

from __future__ import annotations

from calendar import Calendar as _Calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import QuerySet
from django.utils import timezone

from ..models import Reminder
from .calendar_view_service import (
    CalendarEventItem,
    CalendarStats,
    compute_stats,
    group_by_day,
    merge_events,
    to_event_item,
)


@dataclass
class MonthCalendarView:
    """一个月的日历视图。"""

    year: int
    month: int
    #: YYYY-MM-DD → 当日事件（已合并、已排序）
    days: dict[str, list[CalendarEventItem]] = field(default_factory=dict)
    #: 工作台统计（基于全局数据，不限于当月）
    stats: CalendarStats = field(default_factory=CalendarStats)
    #: 当月所有事件（合并后、按时间升序），admin 列表用
    events: list[CalendarEventItem] = field(default_factory=list)


class CalendarMonthService:
    """按月日历查询。stub 友好：查询与归一化都可注入替换。"""

    def __init__(self, *, tz: ZoneInfo | None = None, now: datetime | None = None) -> None:
        self._tz = tz or ZoneInfo("Asia/Shanghai")
        self._now = now or timezone.now()

    # ── 查询 ──────────────────────────────────────────────────────────────

    def query_month(self, *, year: int, month: int) -> QuerySet[Reminder]:
        """当月（本地时区）的提醒，按到期时间升序。"""
        month_start = date(year, month, 1)
        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)

        return (
            Reminder.objects.select_related("contract", "case", "case_log", "case_log__case")
            .filter(
                due_at__gte=timezone.make_aware(datetime.combine(month_start, datetime.min.time()), self._tz),
                due_at__lt=timezone.make_aware(datetime.combine(next_month_start, datetime.min.time()), self._tz),
            )
            .order_by("due_at", "id")
        )

    def query_all_upcoming(self, *, days_ahead: int = 60) -> QuerySet[Reminder]:
        """统计用：从今天起一段时间内的提醒（含已逾期的）。"""
        today = self._now.astimezone(self._tz).date()
        start = timezone.make_aware(datetime.combine(today, datetime.min.time()), self._tz) - timedelta(days=365)
        end = timezone.make_aware(datetime.combine(today, datetime.min.time()), self._tz) + timedelta(days=days_ahead)
        return (
            Reminder.objects.select_related("contract", "case", "case_log", "case_log__case")
            .filter(due_at__gte=start, due_at__lt=end)
            .order_by("due_at", "id")
        )

    # ── 归一化 ────────────────────────────────────────────────────────────

    def normalize(self, reminders: Any, *, today: date) -> list[CalendarEventItem]:
        """Reminder 集合 → 合并后的事件列表。"""
        raws = [to_event_item(r, today=today, now=self._now, tz=self._tz) for r in reminders]
        return merge_events(raws)

    # ── 月视图 ────────────────────────────────────────────────────────────

    def build_month(self, *, year: int, month: int) -> MonthCalendarView:
        """装配一个月的日历视图 + 全站统计。"""
        today = self._now.astimezone(self._tz).date()

        month_events = self.normalize(self.query_month(year=year, month=month), today=today)
        month_events = sorted(month_events, key=lambda e: (e.day, e.time, e.id))

        # 统计按更宽的时间窗算，保证「7 日内到期」跨月也准确
        stats_events = self.normalize(self.query_all_upcoming(), today=today)
        stats = compute_stats(stats_events, today=today)

        return MonthCalendarView(
            year=year,
            month=month,
            days=group_by_day(month_events),
            stats=stats,
            events=month_events,
        )

    # ── admin 用的周网格 ──────────────────────────────────────────────────

    def build_weeks(self, *, year: int, month: int, view: MonthCalendarView) -> list[list[dict[str, Any]]]:
        """按周一起点生成 6 周日历网格（admin 模板用）。

        非当月的格子不带事件（与 admin 原行为一致）。
        """
        today = self._now.astimezone(self._tz).date()
        weeks: list[list[dict[str, Any]]] = []
        for week_dates in _Calendar(firstweekday=0).monthdatescalendar(year, month):
            cells: list[dict[str, Any]] = []
            for day_date in week_dates:
                in_month = day_date.month == month
                key = day_date.strftime("%Y-%m-%d")
                cells.append(
                    {
                        "date": day_date,
                        "day": day_date.day,
                        "in_month": in_month,
                        "is_today": day_date == today,
                        "items": view.days.get(key, []) if in_month else [],
                    }
                )
            weeks.append(cells)
        return weeks
