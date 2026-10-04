"""reminders 访问范围过滤测试（安全审计）。

- target-options：合同/案件/案件日志按查询用户过滤（A 看不到 B 的）
- calendar：关联案件/合同的提醒按 AccessPolicy 过滤；未绑定目标的
  个人提醒仅创建者本人与管理员可见
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from apps.cases.models import CaseAssignment
from apps.contracts.models import ContractAssignment
from apps.core.security.access_context import AccessContext
from apps.reminders.models import Reminder
from apps.reminders.services.calendar_month_service import CalendarMonthService
from apps.reminders.services.target_query import get_target_options
from apps.testing.factories import CaseFactory, CaseLogFactory, ContractFactory, LawyerFactory


def _ctx(user) -> AccessContext:
    return AccessContext(user=user, org_access=None, perm_open_access=False)


@pytest.mark.django_db
class TestTargetOptionsScoping:
    def test_lawyer_sees_only_own_targets(self):
        """律师 A 只看到自己被指派的案件/合同（及其日志），看不到 B 的。"""
        lawyer_a = LawyerFactory()
        lawyer_b = LawyerFactory()
        case_a = CaseFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_a, lawyer=lawyer_a)
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
        contract_a = ContractFactory()
        contract_b = ContractFactory()
        ContractAssignment.objects.create(contract=contract_a, lawyer=lawyer_a)
        ContractAssignment.objects.create(contract=contract_b, lawyer=lawyer_b)
        log_a = CaseLogFactory(case=case_a)
        log_b = CaseLogFactory(case=case_b)

        result = get_target_options(keyword="", ctx=_ctx(lawyer_a))

        ids_by_type: dict[str, set[int]] = {"case": set(), "contract": set(), "case_log": set()}
        for group in result["groups"]:
            for item in group["items"]:
                ids_by_type[group["key"]].add(item["id"])

        assert case_a.id in ids_by_type["case"]
        assert case_b.id not in ids_by_type["case"]
        assert contract_a.id in ids_by_type["contract"]
        assert contract_b.id not in ids_by_type["contract"]
        assert log_a.id in ids_by_type["case_log"]
        assert log_b.id not in ids_by_type["case_log"]

    def test_unassigned_user_sees_nothing(self):
        """无指派的普通用户看不到他人案件。"""
        lawyer_b = LawyerFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)

        result = get_target_options(keyword="", ctx=_ctx(LawyerFactory()))

        case_ids = {item["id"] for group in result["groups"] if group["key"] == "case" for item in group["items"]}
        assert case_b.id not in case_ids

    def test_ctx_none_keeps_full_view(self):
        """ctx=None（admin 内部调用）不过滤，保持原有全量口径。"""
        lawyer_b = LawyerFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)

        result = get_target_options(keyword="", ctx=None)

        case_ids = {item["id"] for group in result["groups"] if group["key"] == "case" for item in group["items"]}
        assert case_b.id in case_ids


@pytest.mark.django_db
class TestCalendarScoping:
    def _month_window(self) -> tuple[int, int]:
        due = datetime.now() + timedelta(days=3)
        return due.year, due.month

    def _event_case_ids(self, view) -> set[int]:
        ids: set[int] = set()
        for items in view.days.values():
            for item in items:
                if item.case_id is not None:
                    ids.add(item.case_id)
        return ids

    def test_lawyer_cannot_see_others_case_reminders(self):
        """律师 A 看不到 B 案件上的提醒。"""
        lawyer_a = LawyerFactory()
        lawyer_b = LawyerFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
        year, month = self._month_window()
        Reminder.objects.create(
            case=case_b, reminder_type="hearing", content="B的庭", due_at=datetime.now() + timedelta(days=3)
        )

        view = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(lawyer_a))

        assert case_b.id not in self._event_case_ids(view)

    def test_lawyer_sees_own_case_reminders(self):
        """A 自己案件上的提醒可见。"""
        lawyer_a = LawyerFactory()
        case_a = CaseFactory()
        CaseAssignment.objects.create(case=case_a, lawyer=lawyer_a)
        year, month = self._month_window()
        Reminder.objects.create(
            case=case_a, reminder_type="hearing", content="A的庭", due_at=datetime.now() + timedelta(days=3)
        )

        view = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(lawyer_a))

        assert case_a.id in self._event_case_ids(view)

    def test_unbound_reminder_creator_only(self):
        """未绑定目标的个人提醒：创建者可见、无关律师不可见。"""
        creator = LawyerFactory()
        other = LawyerFactory()
        year, month = self._month_window()
        reminder = Reminder.objects.create(
            reminder_type="other",
            content="个人提醒",
            due_at=datetime.now() + timedelta(days=3),
            metadata={"created_by_user_id": creator.id},
        )

        creator_view = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(creator))
        other_view = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(other))

        creator_ids = {item.id for items in creator_view.days.values() for item in items}
        other_ids = {item.id for items in other_view.days.values() for item in items}
        assert reminder.id in creator_ids
        assert reminder.id not in other_ids

    def test_unbound_reminder_admin_visible(self):
        """未绑定目标的个人提醒：管理员可见。"""
        admin = LawyerFactory(is_admin=True, is_superuser=True)
        year, month = self._month_window()
        reminder = Reminder.objects.create(
            reminder_type="other",
            content="他人的个人提醒",
            due_at=datetime.now() + timedelta(days=3),
            metadata={"created_by_user_id": 999999},
        )

        view = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(admin))

        event_ids = {item.id for items in view.days.values() for item in items}
        assert reminder.id in event_ids

    def test_case_log_reminder_scoped_via_case(self):
        """案件日志提醒随所属案件过滤。"""
        lawyer_a = LawyerFactory()
        lawyer_b = LawyerFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
        log_b = CaseLogFactory(case=case_b)
        year, month = self._month_window()
        reminder = Reminder.objects.create(
            case_log=log_b, reminder_type="other", content="B的日志提醒", due_at=datetime.now() + timedelta(days=3)
        )

        view_a = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(lawyer_a))
        view_b = CalendarMonthService().build_month(year=year, month=month, ctx=_ctx(lawyer_b))

        ids_a = {item.id for items in view_a.days.values() for item in items}
        ids_b = {item.id for items in view_b.days.values() for item in items}
        assert reminder.id not in ids_a
        assert reminder.id in ids_b

    def test_ctx_none_keeps_full_view(self):
        """ctx=None 时不过滤（admin 后台口径）。"""
        lawyer_b = LawyerFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
        year, month = self._month_window()
        Reminder.objects.create(
            case=case_b, reminder_type="hearing", content="B的庭", due_at=datetime.now() + timedelta(days=3)
        )

        view = CalendarMonthService().build_month(year=year, month=month)

        assert case_b.id in self._event_case_ids(view)


class TestCalendarScopeUnauthenticated:
    def test_unauthenticated_context_gets_empty(self):
        """未认证用户拿到空查询集（防全量泄露）。"""
        anonymous = SimpleNamespace(is_authenticated=False)
        qs = CalendarMonthService()._scope_for_context(Reminder.objects.all(), _ctx(anonymous))
        assert qs.count() == 0
