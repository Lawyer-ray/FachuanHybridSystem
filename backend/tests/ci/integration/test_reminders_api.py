"""Reminders API integration tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from apps.cases.models import Case
from apps.contracts.models import Contract
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
        data=json.dumps(
            {
                "case_id": case.id,
                "reminder_type": "hearing",
                "content": "开庭提醒",
                "due_at": (datetime.now() + timedelta(days=7)).isoformat(),
            }
        ),
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
    # 造锚点数据：合同/案件/案件日志各一条，名称带唯一关键词
    Contract.objects.create(name="审计目标选项合同", case_type="civil")
    Case.objects.create(
        name="审计目标选项案件", contract=Contract.objects.get(name="审计目标选项合同"), case_type="civil"
    )
    resp = authenticated_client.get("/api/v1/reminders/target-options", {"q": "审计目标选项"})
    assert resp.status_code == 200
    data = resp.json()
    # 关键词过滤后必须命中造的合同与案件（分组结构 + 合并 items 均应包含锚点）
    names = [item["name"] for group in data["groups"] for item in group["items"]]
    assert "审计目标选项合同" in names
    assert "审计目标选项案件" in names
    flat_names = [i["name"] for i in data["items"]]
    assert "审计目标选项合同" in flat_names
    # 无关数据不应因过滤失效出现
    assert all("非目标" not in n for n in names)


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
