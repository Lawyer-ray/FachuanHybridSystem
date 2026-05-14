from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.cases.admin.case_admin import CaseAdmin
from apps.cases.admin.caselog_admin import ReminderInline
from apps.cases.models import Case, CaseLog
from apps.cases.services.case.case_admin_service import CaseAdminService
from apps.reminders.models import Reminder, ReminderType


@pytest.mark.django_db
def test_build_important_times_aggregates_case_and_selected_log_reminders() -> None:
    case = Case.objects.create(name="重要时间测试")
    user = get_user_model().objects.create_user(username="important-time-user")
    log = CaseLog.objects.create(case=case, actor=user, content="日志里的期限")
    other_log = CaseLog.objects.create(case=case, actor=user, content="不应出现的日志")

    now = timezone.now()
    later_case_reminder = Reminder.objects.create(
        case=case,
        reminder_type=ReminderType.HEARING,
        content="手动开庭",
        due_at=now + timedelta(days=3),
        include_in_important_time=True,
    )
    log_reminder = Reminder.objects.create(
        case_log=log,
        reminder_type=ReminderType.EVIDENCE_DEADLINE,
        content="日志举证",
        due_at=now + timedelta(days=1),
        include_in_important_time=True,
    )
    Reminder.objects.create(
        case_log=other_log,
        reminder_type=ReminderType.PAYMENT_DEADLINE,
        content="未列入的重要日期",
        due_at=now + timedelta(days=2),
        include_in_important_time=False,
    )

    loaded_case = CaseAdminService().get_case_with_admin_relations(case.id)
    assert loaded_case is not None

    important_times = CaseAdminService().build_important_times_for_detail(loaded_case)

    assert [item["id"] for item in important_times] == [log_reminder.id, later_case_reminder.id]
    assert [item["source"] for item in important_times] == ["log", "manual"]
    assert important_times[0]["source_log_id"] == log.id
    assert important_times[0]["source_log_url"].endswith(f"/admin/cases/caselog/{log.id}/change/")
    assert important_times[0]["reminder_url"].endswith(f"/admin/reminders/reminder/{log_reminder.id}/change/")
    assert important_times[0]["source_url"].endswith(f"/admin/cases/caselog/{log.id}/change/")
    assert important_times[1]["reminder_url"].endswith(f"/admin/reminders/reminder/{later_case_reminder.id}/change/")
    assert important_times[1]["source_url"].endswith(f"/admin/reminders/reminder/{later_case_reminder.id}/change/")
    assert important_times[0]["source_label"] == "日志提醒"
    assert important_times[1]["source_label"] == "手动添加"
    assert important_times[0]["status_label"] == "即将到期"
    assert important_times[0]["relative_days_label"] == "剩余 1 天"


@pytest.mark.django_db
def test_build_important_times_labels_due_statuses_and_sorts_by_due_time() -> None:
    case = Case.objects.create(name="important-time-status")
    now = timezone.now()
    reminders = [
        Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.OTHER,
            content="upcoming",
            due_at=now + timedelta(days=15),
            include_in_important_time=True,
        ),
        Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.OTHER,
            content="overdue",
            due_at=now - timedelta(days=2),
            include_in_important_time=True,
        ),
        Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.OTHER,
            content="today",
            due_at=now,
            include_in_important_time=True,
        ),
        Reminder.objects.create(
            case=case,
            reminder_type=ReminderType.OTHER,
            content="soon",
            due_at=now + timedelta(days=3),
            include_in_important_time=True,
        ),
    ]

    important_times = CaseAdminService().build_important_times_for_detail(case)

    assert [item["id"] for item in important_times] == [
        reminders[1].id,
        reminders[2].id,
        reminders[3].id,
        reminders[0].id,
    ]
    assert [item["status"] for item in important_times] == ["overdue", "today", "soon", "upcoming"]
    assert [item["status_label"] for item in important_times] == ["已逾期", "今日到期", "即将到期", "未到期"]
    assert important_times[0]["relative_days_label"] == ""
    assert important_times[1]["relative_days_label"] == "今天"
    assert important_times[2]["relative_days_label"] == "剩余 3 天"
    assert important_times[3]["relative_days_label"] == "剩余 15 天"


@pytest.mark.django_db
def test_case_admin_save_formset_forces_case_level_reminders_into_important_time() -> None:
    case = Case.objects.create(name="案件级重要时间")
    reminder = Reminder(
        case=case,
        reminder_type=ReminderType.OTHER,
        content="手动录入",
        due_at=timezone.now(),
        include_in_important_time=False,
    )
    request = RequestFactory().post("/")
    request.user = SimpleNamespace(id=1)
    formset = SimpleNamespace(save=lambda commit=False: [reminder], save_m2m=lambda: None, deleted_objects=[])

    CaseAdmin(Case, AdminSite()).save_formset(request, form=SimpleNamespace(), formset=formset, change=True)
    reminder.refresh_from_db()

    assert reminder.include_in_important_time is True
    assert reminder.contract_id is None
    assert reminder.case_log_id is None


def test_case_log_reminder_inline_labels_important_time_sync_field() -> None:
    request = RequestFactory().get("/")
    formfield = ReminderInline(CaseLog, AdminSite()).formfield_for_dbfield(
        Reminder._meta.get_field("include_in_important_time"),
        request,
    )

    assert formfield is not None
    assert formfield.label == "同步到案件重要时间"
    assert formfield.help_text == "同步到案件重要时间：勾选后会在案件详情的重要时间中展示，不会复制生成新数据。"


@pytest.mark.django_db
def test_important_time_partial_renders_sources_and_empty_state() -> None:
    case = Case.objects.create(name="渲染测试")
    now = timezone.now()
    important_times = [
        {
            "id": 1,
            "reminder_type": ReminderType.OTHER,
            "reminder_type_label": "其他",
            "content": "手动事项",
            "due_at": now,
            "due_at_display": "2026-06-01 09:00",
            "source": "manual",
            "source_label": "手动添加",
            "source_log_id": None,
            "source_log_url": "",
            "status": "upcoming",
            "status_label": "未到期",
            "relative_days_label": "剩余 10 天",
            "reminder_url": "/admin/reminders/reminder/1/change/",
            "source_url": "/admin/reminders/reminder/1/change/",
        },
        {
            "id": 2,
            "reminder_type": ReminderType.HEARING,
            "reminder_type_label": "开庭",
            "content": "日志事项",
            "due_at": now,
            "due_at_display": "2026-06-02 14:30",
            "source": "log",
            "source_label": "日志提醒",
            "source_log_id": 9,
            "source_log_url": "/admin/cases/caselog/9/change/",
            "status": "overdue",
            "status_label": "已逾期",
            "relative_days_label": "",
            "reminder_url": "/admin/reminders/reminder/2/change/",
            "source_url": "/admin/cases/caselog/9/change/",
        },
    ]

    html = render_to_string(
        "admin/cases/case/partials/important_time.html",
        {
            "case": case,
            "important_times": important_times,
            "has_change_permission": True,
            "important_time_type_options": [{"value": "other", "label": "其他"}],
        },
    )

    assert "重要时间" in html
    assert "添加重要时间" in html
    assert "importantTimeApp()" in html
    assert "/api/v1/reminders/cases/" in html
    assert "09:00" in html
    assert "手动事项" in html
    assert "日志事项" in html
    assert "手动添加" in html
    assert "日志提醒" in html
    assert "/admin/reminders/reminder/1/change/" in html
    assert "/admin/reminders/reminder/2/change/" in html
    assert "/admin/cases/caselog/9/change/" in html
    assert "已逾期" in html
    assert "已逾期 1 天" not in html
    assert "important-time-row--overdue" not in html
    assert "确认删除" in html
    assert "/api/v1/reminders/1/important-time" in html
    assert "/api/v1/reminders/2/important-time" in html

    empty_html = render_to_string(
        "admin/cases/case/partials/important_time.html",
        {
            "case": case,
            "important_times": [],
            "has_change_permission": False,
            "important_time_type_options": [{"value": "other", "label": "其他"}],
        },
    )
    assert "暂无重要时间" in empty_html


@pytest.mark.django_db
def test_create_case_important_time_from_detail_shortcut() -> None:
    case = Case.objects.create(name="create-important-time-shortcut")
    user = get_user_model().objects.create_user(username="important-time-creator", password="pw", is_staff=True)
    client = Client(HTTP_HOST="127.0.0.1")
    client.force_login(user)

    response = client.post(
        f"/api/v1/reminders/cases/{case.id}/important-time",
        data={
            "reminder_type": ReminderType.EVIDENCE_DEADLINE,
            "content": "详情页快捷添加",
            "due_at": "2026-05-20T09:00:00",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    reminder = Reminder.objects.get(case=case, content="详情页快捷添加")
    assert reminder.reminder_type == ReminderType.EVIDENCE_DEADLINE
    assert reminder.include_in_important_time is True
    assert reminder.contract_id is None
    assert reminder.case_log_id is None


@pytest.mark.django_db
def test_remove_important_time_deletes_manual_reminder_and_only_unsyncs_log_reminder() -> None:
    case = Case.objects.create(name="remove-important-time")
    user = get_user_model().objects.create_user(username="important-time-remover", password="pw", is_staff=True)
    log = CaseLog.objects.create(case=case, actor=user, content="日志仍保留")
    now = timezone.now()
    manual_reminder = Reminder.objects.create(
        case=case,
        reminder_type=ReminderType.OTHER,
        content="手动重要时间",
        due_at=now,
        include_in_important_time=True,
    )
    log_reminder = Reminder.objects.create(
        case_log=log,
        reminder_type=ReminderType.OTHER,
        content="日志提醒",
        due_at=now,
        include_in_important_time=True,
    )
    client = Client()
    client.force_login(user)

    manual_response = client.delete(f"/api/v1/reminders/{manual_reminder.id}/important-time")
    log_response = client.delete(f"/api/v1/reminders/{log_reminder.id}/important-time")

    assert manual_response.status_code == 204
    assert log_response.status_code == 204
    assert not Reminder.objects.filter(id=manual_reminder.id).exists()
    log_reminder.refresh_from_db()
    log.refresh_from_db()
    assert log_reminder.include_in_important_time is False
    assert log_reminder.case_log_id == log.id
    assert log.content == "日志仍保留"


@pytest.mark.django_db
def test_remove_important_time_requires_staff_user() -> None:
    case = Case.objects.create(name="remove-important-time-permission")
    reminder = Reminder.objects.create(
        case=case,
        reminder_type=ReminderType.OTHER,
        content="手动重要时间",
        due_at=timezone.now(),
        include_in_important_time=True,
    )
    response = Client().delete(f"/api/v1/reminders/{reminder.id}/important-time", HTTP_HOST="127.0.0.1")

    assert response.status_code in {401, 403}
    assert Reminder.objects.filter(id=reminder.id, include_in_important_time=True).exists()
