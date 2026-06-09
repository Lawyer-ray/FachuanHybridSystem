"""Workbench API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.workbench.models import WorkbenchSession


# ===================================================================
# Session CRUD
# ===================================================================


@pytest.mark.django_db
def test_create_session(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "测试会话", "llm_model": "gpt-4"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "测试会话"
    assert WorkbenchSession.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_list_sessions(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "列表测试会话"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    resp = authenticated_client.get("/api/v1/workbench/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data or isinstance(data, list)


@pytest.mark.django_db
def test_get_session_detail(authenticated_client):
    create_resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "详情会话"}),
        content_type="application/json",
    )
    session_id = create_resp.json()["id"]
    resp = authenticated_client.get(f"/api/v1/workbench/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "详情会话"


@pytest.mark.django_db
def test_update_session(authenticated_client):
    create_resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "更新前"}),
        content_type="application/json",
    )
    session_id = create_resp.json()["id"]
    resp = authenticated_client.patch(
        f"/api/v1/workbench/sessions/{session_id}",
        data=json.dumps({"title": "更新后"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "更新后"


@pytest.mark.django_db
def test_delete_session(authenticated_client):
    create_resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "待删除会话"}),
        content_type="application/json",
    )
    session_id = create_resp.json()["id"]
    resp = authenticated_client.delete(f"/api/v1/workbench/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["message"] == "已删除"


# ===================================================================
# Messages
# ===================================================================


@pytest.mark.django_db
def test_list_messages(authenticated_client):
    create_resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "消息测试会话"}),
        content_type="application/json",
    )
    session_id = create_resp.json()["id"]
    resp = authenticated_client.get(f"/api/v1/workbench/sessions/{session_id}/messages")
    assert resp.status_code == 200


# ===================================================================
# Models
# ===================================================================


@pytest.mark.django_db
def test_list_models(authenticated_client):
    resp = authenticated_client.get("/api/v1/workbench/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data


# ===================================================================
# Approval
# ===================================================================


@pytest.mark.django_db
def test_respond_approval_nonexistent(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/workbench/approval",
        data=json.dumps({"approval_id": "nonexistent-id", "approved": True}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


# ===================================================================
# Batch Jobs (list)
# ===================================================================


@pytest.mark.django_db
def test_list_batch_jobs(authenticated_client):
    create_resp = authenticated_client.post(
        "/api/v1/workbench/sessions",
        data=json.dumps({"title": "批量测试会话"}),
        content_type="application/json",
    )
    session_id = create_resp.json()["id"]
    resp = authenticated_client.get(f"/api/v1/workbench/sessions/{session_id}/batch-jobs")
    assert resp.status_code == 200
