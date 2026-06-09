"""Reminders API integration tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from apps.contracts.models import Contract
from apps.cases.models import Case
from apps.reminders.models import Reminder


def _make_case():
    contract = Contract.objects.create(name="提醒测试合同", case_type="civil")
    return Case.objects.create(name="提醒测试案件", contract=contract)


# ===================================================================
# Reminder CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_reminders(authenticated_client):
    case = _make_case()
    Reminder.objects.create(
        case=case,
        reminder_type="hearing",
        content="开庭提醒",
        due_at=datetime.now() + timedelta(days=7),
    )
    resp = authenticated_client.get("/api/v1/reminders/list", {"case_id": case.id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_reminder(authenticated_client):
    case = _make_case()
    resp = authenticated_client.post(
        "/api/v1/reminders/create",
        data=json.dumps({
            "case_id": case.id,
            "reminder_type": "hearing",
            "content": "开庭提醒",
            "due_at": (datetime.now() + timedelta(days=7)).isoformat(),
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "开庭提醒"
    assert Reminder.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_reminder_detail(authenticated_client):
    case = _make_case()
    reminder = Reminder.objects.create(
        case=case,
        reminder_type="deadline",
        content="举证期限",
        due_at=datetime.now() + timedelta(days=14),
    )
    resp = authenticated_client.get(f"/api/v1/reminders/{reminder.id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "举证期限"


@pytest.mark.django_db
def test_update_reminder(authenticated_client):
    case = _make_case()
    reminder = Reminder.objects.create(
        case=case,
        reminder_type="deadline",
        content="更新前内容",
        due_at=datetime.now() + timedelta(days=14),
    )
    resp = authenticated_client.put(
        f"/api/v1/reminders/{reminder.id}",
        data=json.dumps({"content": "更新后内容"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "更新后内容"


@pytest.mark.django_db
def test_delete_reminder(authenticated_client):
    case = _make_case()
    reminder = Reminder.objects.create(
        case=case,
        reminder_type="hearing",
        content="待删除提醒",
        due_at=datetime.now() + timedelta(days=7),
    )
    resp = authenticated_client.delete(f"/api/v1/reminders/{reminder.id}")
    assert resp.status_code == 204
    assert not Reminder.objects.filter(id=reminder.id).exists()


@pytest.mark.django_db
def test_get_types(authenticated_client):
    resp = authenticated_client.get("/api/v1/reminders/types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.django_db
def test_get_target_options(authenticated_client):
    resp = authenticated_client.get("/api/v1/reminders/target-options", {"q": ""})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_parse_reminders(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/reminders/parse",
        data=json.dumps({"text": "下周一开庭 2026年6月16日上午9点"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
