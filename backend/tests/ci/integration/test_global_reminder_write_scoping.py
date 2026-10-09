"""全局提醒写权限端到端测试（安全审计 2026Q4 M-1）。

``authenticated_client`` fixture 默认是 is_admin+is_superuser 的账号（走管理员
豁免），无法证明收敛生效。这里显式构造普通律师 A / B，验证 A 改删 B 的全局
提醒被 403 拒绝，而 A 改自己的成功。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from django.test import Client

from apps.organization.models import LawFirm, Lawyer
from apps.reminders.models import Reminder


def _make_lawyer(username: str) -> Lawyer:
    firm, _ = LawFirm.objects.get_or_create(name=f"律所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="testpass123",
        law_firm=firm,
    )


def _login(username: str) -> Client:
    client = Client()
    assert client.login(username=username, password="testpass123")
    return client


def _global_reminder(*, creator: Lawyer | None, content: str) -> Reminder:
    return Reminder.objects.create(
        reminder_type="other",
        content=content,
        due_at=datetime.now() + timedelta(days=3),
        created_by=creator,
    )


@pytest.mark.django_db
class TestGlobalReminderWriteScoping:
    def test_creator_can_update_own_global_reminder(self) -> None:
        alice = _make_lawyer("alice")
        reminder = _global_reminder(creator=alice, content="A的全局提醒")

        resp = _login("alice").put(
            f"/api/v1/reminders/{reminder.id}",
            data=json.dumps({"content": "A改后的内容"}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        assert resp.json()["content"] == "A改后的内容"

    def test_other_user_cannot_update_global_reminder(self) -> None:
        """M-1 核心：他人创建的全局提醒不可改。"""
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        reminder = _global_reminder(creator=alice, content="A的全局提醒")

        resp = _login("bob").put(
            f"/api/v1/reminders/{reminder.id}",
            data=json.dumps({"content": "B篡改的内容"}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        reminder.refresh_from_db()
        assert reminder.content == "A的全局提醒"

    def test_other_user_cannot_delete_global_reminder(self) -> None:
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        reminder = _global_reminder(creator=alice, content="A的全局提醒")

        resp = _login("bob").delete(f"/api/v1/reminders/{reminder.id}")

        assert resp.status_code == 403
        assert Reminder.objects.filter(id=reminder.id).exists()

    def test_other_user_cannot_complete_global_reminder(self) -> None:
        """批量完成同样是写操作。"""
        alice = _make_lawyer("alice")
        bob = _make_lawyer("bob")
        reminder = _global_reminder(creator=alice, content="A的全局提醒")

        resp = _login("bob").post(
            "/api/v1/reminders/complete",
            data=json.dumps({"reminder_ids": [reminder.id], "is_completed": True}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        reminder.refresh_from_db()
        assert reminder.is_completed is False

    def test_orphan_global_reminder_denies_non_admin(self) -> None:
        """存量数据 created_by 为空（未回填/创建人已删）→ fail-closed。"""
        bob = _make_lawyer("bob")
        reminder = _global_reminder(creator=None, content="无主全局提醒")

        resp = _login("bob").put(
            f"/api/v1/reminders/{reminder.id}",
            data=json.dumps({"content": "B篡改的内容"}),
            content_type="application/json",
        )

        assert resp.status_code == 403
        reminder.refresh_from_db()
        assert reminder.content == "无主全局提醒"

    def test_admin_can_update_others_global_reminder(self) -> None:
        """管理员豁免。"""
        alice = _make_lawyer("alice")
        reminder = _global_reminder(creator=alice, content="A的全局提醒")
        firm, _ = LawFirm.objects.get_or_create(name="律所-admin")
        admin = Lawyer.objects.create_user(
            username="theadmin",
            password="testpass123",
            law_firm=firm,
            is_admin=True,
            is_superuser=True,
        )

        resp = _login("theadmin").put(
            f"/api/v1/reminders/{reminder.id}",
            data=json.dumps({"content": "管理员改后的内容"}),
            content_type="application/json",
        )

        assert resp.status_code == 200
        assert admin.is_admin is True

    def test_create_records_created_by(self) -> None:
        """新建全局提醒必须记录创建人，否则自己下次也改不了。"""
        alice = _make_lawyer("alice")

        resp = _login("alice").post(
            "/api/v1/reminders/create",
            data=json.dumps(
                {
                    "reminder_type": "other",
                    "content": "A新建的全局提醒",
                    "due_at": (datetime.now() + timedelta(days=5)).isoformat(),
                }
            ),
            content_type="application/json",
        )

        assert resp.status_code == 200
        reminder = Reminder.objects.get(id=resp.json()["id"])
        assert reminder.created_by_id == alice.id
        assert reminder.is_global is True
        assert resp.json()["created_by"] == alice.id
