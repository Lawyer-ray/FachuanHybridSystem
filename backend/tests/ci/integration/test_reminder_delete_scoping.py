"""日历事件删除权限端到端测试：谁创建谁删。

``authenticated_client`` fixture 是 is_admin+is_superuser 账号（走管理员豁免），
证明不了收敛生效。这里显式构造普通律师 A / B 并把两人都指派到同一案件——
B 对该案件有访问权（能看、能勾完成、能改），但删 A 建的日程必须 403。
这正是与 M-1「全局提醒才看创建人」的差异所在。
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.utils import timezone

from apps.cases.models import Case, CaseAssignment
from apps.contracts.models import Contract
from apps.organization.models import LawFirm, Lawyer
from apps.reminders.models import Reminder

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _make_lawyer(username: str, **flags: Any) -> Lawyer:
    firm, _ = LawFirm.objects.get_or_create(name="律所-删除权限测试")
    return Lawyer.objects.create_user(
        username=username,
        password="testpass123",  # pragma: allowlist secret
        law_firm=firm,
        **flags,
    )


def _login(username: str) -> Client:
    client = Client()
    assert client.login(username=username, password="testpass123")  # pragma: allowlist secret
    return client


def _make_shared_case(*lawyers: Lawyer) -> Case:
    """两人都指派到同一案件 → 对该案件的提醒都有访问权。"""
    contract = Contract.objects.create(name="删除权限测试合同", case_type="civil")
    case = Case.objects.create(name="删除权限测试案件", contract=contract)
    for lawyer in lawyers:
        CaseAssignment.objects.create(case=case, lawyer=lawyer)
    return case


def _bound_reminder(
    case: Case,
    *,
    creator: Lawyer | None,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Reminder:
    # 类型 other 且无法庭信息 → 日历不做同庭合并，一条 reminder 对应一条事件
    return Reminder.objects.create(
        case=case,
        reminder_type="other",
        content=content,
        due_at=timezone.now() + timedelta(hours=1),
        created_by=creator,
        metadata=metadata or {},
    )


def _calendar_event(client: Client, reminder: Reminder) -> dict[str, Any]:
    """按 reminder 到期的本地月取日历，找到含该 id 的事件。"""
    local_due = reminder.due_at.astimezone(_SHANGHAI)
    resp = client.get("/api/v1/reminders/calendar", {"year": local_due.year, "month": local_due.month})
    assert resp.status_code == 200
    for events in resp.json()["days"].values():
        for event in events:
            if reminder.id in (event.get("member_ids") or [event["id"]]):
                return event
    raise AssertionError(f"日历里找不到 reminder #{reminder.id}")


@pytest.mark.django_db
class TestReminderDeleteScoping:
    def test_colleague_on_same_case_can_read_and_complete_but_not_delete(self) -> None:
        """核心：B 对案件有访问权（GET 200、勾完成 200），但删 A 的日程 403。"""
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        case = _make_shared_case(alice, bob)
        reminder = _bound_reminder(case, creator=alice, content="A建的日程")
        bob_client = _login("bob")

        assert bob_client.get(f"/api/v1/reminders/{reminder.id}").status_code == 200

        complete = bob_client.post(
            "/api/v1/reminders/complete",
            data=json.dumps({"reminder_ids": [reminder.id], "is_completed": True}),
            content_type="application/json",
        )
        assert complete.status_code == 200

        resp = bob_client.delete(f"/api/v1/reminders/{reminder.id}")

        assert resp.status_code == 403
        assert resp.json()["code"] == "REMINDER_NOT_CREATOR"
        assert Reminder.objects.filter(id=reminder.id).exists()

    def test_creator_can_delete_own_bound_reminder(self) -> None:
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        case = _make_shared_case(alice, bob)
        reminder = _bound_reminder(case, creator=alice, content="A建的日程")

        resp = _login("alice").delete(f"/api/v1/reminders/{reminder.id}")

        assert resp.status_code == 204
        assert not Reminder.objects.filter(id=reminder.id).exists()

    def test_batch_delete_rejects_whole_batch_when_any_item_is_not_mine(self) -> None:
        """批量接口任一条不是自己建的 → 整批 403、一条不删（不留半截）。"""
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        case = _make_shared_case(alice, bob)
        mine = _bound_reminder(case, creator=alice, content="A的")
        theirs = _bound_reminder(case, creator=bob, content="B的")

        resp = _login("alice").post(
            "/api/v1/reminders/delete",
            data=json.dumps({"reminder_ids": [mine.id, theirs.id]}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        assert Reminder.objects.filter(id__in=[mine.id, theirs.id]).count() == 2

    def test_batch_delete_own_reminders(self) -> None:
        alice = _make_lawyer("alice")
        case = _make_shared_case(alice)
        first = _bound_reminder(case, creator=alice, content="A的一")
        second = _bound_reminder(case, creator=alice, content="A的二")

        resp = _login("alice").post(
            "/api/v1/reminders/delete",
            data=json.dumps({"reminder_ids": [first.id, second.id, 999999]}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        assert resp.json() == {"deleted": 2}
        assert not Reminder.objects.filter(id__in=[first.id, second.id]).exists()

    def test_calendar_marks_can_delete_per_viewer(self) -> None:
        """前端据 can_delete 显隐删除按钮：创建人 True、同案同事 False。"""
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        case = _make_shared_case(alice, bob)
        reminder = _bound_reminder(case, creator=alice, content="A建的日程")

        assert _calendar_event(_login("alice"), reminder)["can_delete"] is True
        assert _calendar_event(_login("bob"), reminder)["can_delete"] is False

    def test_metadata_creator_fallback_allows_delete(self) -> None:
        """案件日志等内部路径只写 metadata.created_by_user_id，不填 FK，也要认作创建人。"""
        alice = _make_lawyer("alice")
        case = _make_shared_case(alice)
        reminder = _bound_reminder(
            case, creator=None, content="内部路径建的", metadata={"created_by_user_id": alice.id}
        )
        alice_client = _login("alice")

        assert _calendar_event(alice_client, reminder)["can_delete"] is True
        assert alice_client.delete(f"/api/v1/reminders/{reminder.id}").status_code == 204

    def test_orphan_reminder_denies_non_admin_but_allows_admin(self) -> None:
        """无主提醒（同步产生 / 创建人已删）fail-closed：普通律师 403，管理员可删。"""
        alice = _make_lawyer("alice")
        _make_lawyer("theadmin", is_admin=True, is_superuser=True)
        case = _make_shared_case(alice)
        reminder = _bound_reminder(case, creator=None, content="无主日程")

        assert _login("alice").delete(f"/api/v1/reminders/{reminder.id}").status_code == 403
        assert Reminder.objects.filter(id=reminder.id).exists()

        assert _login("theadmin").delete(f"/api/v1/reminders/{reminder.id}").status_code == 204
        assert not Reminder.objects.filter(id=reminder.id).exists()

    def test_admin_can_delete_others_reminder(self) -> None:
        alice = _make_lawyer("alice")
        _make_lawyer("theadmin", is_admin=True, is_superuser=True)
        case = _make_shared_case(alice)
        reminder = _bound_reminder(case, creator=alice, content="A建的日程")

        resp = _login("theadmin").delete(f"/api/v1/reminders/{reminder.id}")

        assert resp.status_code == 204
        assert not Reminder.objects.filter(id=reminder.id).exists()
