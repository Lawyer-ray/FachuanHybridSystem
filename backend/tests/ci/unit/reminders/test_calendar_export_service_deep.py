"""CalendarExportService 深度覆盖测试。

覆盖 _query_reminders 的过滤矩阵（月份边界/类型/scope/status）、
export_reminders 真实渲染循环、以及 _reminder_to_vevent 的
naive end_at 补时区、case_log 描述、location 防注入（"missing value"）
与 ICS 文本注入防护分支。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.reminders.models import Reminder
from apps.reminders.services.calendar_export_service import CalendarExportService
from apps.testing.factories import CaseFactory, CaseLogFactory, ContractFactory


def _reminder(**kwargs) -> Reminder:
    """在当前时间附近创建一条提醒，默认挂在案件上。"""
    defaults = {
        "reminder_type": "hearing",
        "content": "默认提醒",
        "due_at": timezone.now() + timedelta(days=1),
    }
    defaults.update(kwargs)
    return Reminder.objects.create(**defaults)


@pytest.mark.django_db
class TestQueryReminders:
    def test_month_window_filters_in_out(self) -> None:
        now = timezone.now()
        _reminder(due_at=now, content="本月内")
        _reminder(due_at=now + timedelta(days=45), content="下月外")

        rows = CalendarExportService()._query_reminders(
            year=now.year, month=now.month, reminder_type="", scope="all", status="all"
        )
        contents = [r.content for r in rows]
        assert "本月内" in contents
        assert "下月外" not in contents

    def test_december_window_spans_next_year(self) -> None:
        now = timezone.now()
        # 构造 12 月窗口：把提醒钉在「今年 12 月 15 日 ± 当天时刻」上不现实，
        # 改用相对 now 推算，仅在 now 落于 11 月后才可能跨界；直接构造绝对日期更稳。
        import datetime as dt

        dec_date = timezone.make_aware(dt.datetime(now.year, 12, 10, 12, 0))
        jan_date = timezone.make_aware(dt.datetime(now.year + 1, 1, 10, 12, 0))
        _reminder(due_at=dec_date, content="12月提醒")
        _reminder(due_at=jan_date, content="次年1月提醒")

        rows = CalendarExportService()._query_reminders(
            year=now.year, month=12, reminder_type="", scope="all", status="all"
        )
        contents = [r.content for r in rows]
        assert "12月提醒" in contents
        assert "次年1月提醒" not in contents

    def test_valid_type_filter_applied(self) -> None:
        now = timezone.now()
        _reminder(due_at=now, reminder_type="hearing", content="开庭")
        _reminder(due_at=now, reminder_type="deadline", content="期限")

        rows = CalendarExportService()._query_reminders(
            year=now.year, month=now.month, reminder_type="hearing", scope="all", status="all"
        )
        assert [r.content for r in rows] == ["开庭"]

    def test_invalid_type_filter_ignored(self) -> None:
        now = timezone.now()
        _reminder(due_at=now, content="任意类型")

        rows = CalendarExportService()._query_reminders(
            year=now.year, month=now.month, reminder_type="not-a-type", scope="all", status="all"
        )
        assert [r.content for r in rows] == ["任意类型"]

    def test_scope_filters(self) -> None:
        now = timezone.now()
        contract = ContractFactory()
        case = CaseFactory()
        case_log = CaseLogFactory()
        _reminder(due_at=now, contract=contract, content="合同提醒")
        _reminder(due_at=now, case=case, content="案件提醒")
        _reminder(due_at=now, case_log=case_log, content="日志提醒")

        svc = CalendarExportService()
        contract_rows = svc._query_reminders(
            year=now.year, month=now.month, reminder_type="", scope="contract", status="all"
        )
        case_rows = svc._query_reminders(year=now.year, month=now.month, reminder_type="", scope="case", status="all")
        log_rows = svc._query_reminders(
            year=now.year, month=now.month, reminder_type="", scope="case_log", status="all"
        )
        assert [r.content for r in contract_rows] == ["合同提醒"]
        assert [r.content for r in case_rows] == ["案件提醒"]
        assert [r.content for r in log_rows] == ["日志提醒"]

    def test_status_filters_overdue_upcoming(self) -> None:
        now = timezone.now()
        _reminder(due_at=now - timedelta(days=1), content="已过期")
        _reminder(due_at=now + timedelta(days=1), content="未到期")

        svc = CalendarExportService()
        overdue = svc._query_reminders(year=now.year, month=now.month, reminder_type="", scope="all", status="overdue")
        upcoming = svc._query_reminders(
            year=now.year, month=now.month, reminder_type="", scope="all", status="upcoming"
        )
        assert [r.content for r in overdue] == ["已过期"]
        assert [r.content for r in upcoming] == ["未到期"]

    def test_result_ordered_by_due_at(self) -> None:
        now = timezone.now()
        _reminder(due_at=now + timedelta(days=2), content="晚")
        _reminder(due_at=now, content="早")

        rows = CalendarExportService()._query_reminders(
            year=now.year, month=now.month, reminder_type="", scope="all", status="all"
        )
        assert [r.content for r in rows] == ["早", "晚"]


@pytest.mark.django_db
class TestExportRemindersRealLoop:
    def test_export_renders_real_reminders(self) -> None:
        now = timezone.now()
        case = CaseFactory()
        _reminder(case=case, due_at=now, content="导出用开庭提醒", metadata={"courtroom": "第五法庭"})

        data = CalendarExportService().export_reminders(year=now.year, month=now.month)
        text = data.decode("utf-8")
        assert "BEGIN:VEVENT" in text
        assert "导出用开庭提醒" in text
        assert "第五法庭" in text
        # 查询过滤生效：下月提醒不进导出
        _reminder(case=case, due_at=now + timedelta(days=60), content="下月不导出")
        data_again = CalendarExportService().export_reminders(year=now.year, month=now.month)
        assert "下月不导出" not in data_again.decode("utf-8")

    def test_reminder_without_due_at_skipped_in_loop(self) -> None:
        # due_at 为 None 的提醒在 _reminder_to_vevent 返回 None，导出循环跳过不炸
        now = timezone.now()
        _reminder(due_at=now, content="有日期")
        from types import SimpleNamespace

        svc = CalendarExportService()
        assert svc._reminder_to_vevent(SimpleNamespace(due_at=None)) is None  # type: ignore[arg-type]

        data = svc.export_reminders(year=now.year, month=now.month)
        assert b"VCALENDAR" in data


@pytest.mark.django_db
class TestReminderToVeventEdgeBranches:
    def _base(self, **overrides):
        from types import SimpleNamespace

        now = timezone.now()
        defaults = {
            "id": 77,
            "due_at": now,
            "content": "分支提醒",
            "reminder_type": "hearing",
            "metadata": {},
            "contract_id": None,
            "contract": None,
            "case_id": None,
            "case": None,
            "case_log_id": None,
            "case_log": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_naive_end_at_gets_tz_attached(self) -> None:
        import datetime as dt

        naive_end = (timezone.localtime() + timedelta(hours=3)).replace(tzinfo=None)
        vevent = CalendarExportService()._reminder_to_vevent(
            self._base(metadata={"end_at": naive_end.isoformat()})  # type: ignore[arg-type]
        )
        assert vevent is not None
        dtend = vevent.get("dtend")
        assert dtend is not None

    def test_case_log_id_appends_description(self) -> None:
        case = CaseFactory()
        case_log = CaseLogFactory(case=case)
        vevent = CalendarExportService()._reminder_to_vevent(
            self._base(case_log_id=case_log.id, case_log=case_log)  # type: ignore[arg-type]
        )
        assert vevent is not None
        desc = str(vevent.get("description", ""))
        assert f"案件日志: #{case_log.id}" in desc

    def test_location_missing_value_not_emitted(self) -> None:
        """icalendar 缺值哨兵 "missing value" 不得写进 LOCATION（防脏数据）。"""
        vevent = CalendarExportService()._reminder_to_vevent(
            self._base(metadata={"courtroom": "missing value"})  # type: ignore[arg-type]
        )
        assert vevent is not None
        assert vevent.get("location") is None

    def test_ics_text_injection_is_escaped(self) -> None:
        """summary 含 CRLF/ BEGIN:VEVENT 注入载荷时，icalendar 必须转义为字面文本。

        ICS 值注入（CVE-2007-4510 一类）：若 summary 原样拼入日历流，攻击者
        可用换行符注入新组件。icalendar Event.add 对 vText 做转义，这里锁定该行为。
        """
        payload = "恶意\nBEGIN:VEVENT\nSUMMARY:被注入事件"
        vevent = CalendarExportService()._reminder_to_vevent(self._base(content=payload))  # type: ignore[arg-type]
        assert vevent is not None
        raw = vevent.to_ical().decode("utf-8")
        # 反斜杠转义后的换行不得再产生新的 BEGIN:VEVENT 行
        assert "\nBEGIN:VEVENT" not in raw
        summary = str(vevent.get("summary"))
        assert "恶意" in summary

    def test_unknown_type_falls_back_to_raw_label(self) -> None:
        vevent = CalendarExportService()._reminder_to_vevent(
            self._base(reminder_type="custom_type")  # type: ignore[arg-type]
        )
        assert vevent is not None
        assert "custom_type" in str(vevent.get("categories"))
