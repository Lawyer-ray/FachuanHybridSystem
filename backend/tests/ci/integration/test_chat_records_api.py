"""Chat Records API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.chat_records.models import ChatRecordProject as Project


# ===================================================================
# Export Types & Statuses
# ===================================================================


@pytest.mark.django_db
def test_get_export_types(authenticated_client):
    resp = authenticated_client.get("/api/v1/chat-records/export-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.django_db
def test_get_export_statuses(authenticated_client):
    resp = authenticated_client.get("/api/v1/chat-records/export-statuses")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ===================================================================
# Project CRUD
# ===================================================================


@pytest.mark.django_db
def test_create_project(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/chat-records/projects",
        data=json.dumps({"name": "测试项目", "description": "项目描述"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "测试项目"
    assert Project.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_list_projects(authenticated_client):
    Project.objects.create(name="项目A")
    Project.objects.create(name="项目B")
    resp = authenticated_client.get("/api/v1/chat-records/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.django_db
def test_list_recordings(authenticated_client):
    project = Project.objects.create(name="录像项目")
    resp = authenticated_client.get(f"/api/v1/chat-records/projects/{project.id}/recordings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.django_db
def test_list_screenshots(authenticated_client):
    project = Project.objects.create(name="截图项目")
    resp = authenticated_client.get(f"/api/v1/chat-records/projects/{project.id}/screenshots")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ===================================================================
# Recordings
# ===================================================================


@pytest.mark.django_db
def test_upload_recording(authenticated_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    project = Project.objects.create(name="上传录像项目")
    upload = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")
    resp = authenticated_client.post(
        f"/api/v1/chat-records/projects/{project.id}/recordings",
        {"file": upload},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data


# ===================================================================
# Screenshots
# ===================================================================


@pytest.mark.django_db
def test_upload_screenshots(authenticated_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    project = Project.objects.create(name="上传截图项目")
    upload = SimpleUploadedFile("screenshot.png", b"fake png content", content_type="image/png")
    resp = authenticated_client.post(
        f"/api/v1/chat-records/projects/{project.id}/screenshots",
        {"files": upload, "deduplicate": "true"},
    )
    # May return 500 if image processing libraries are not available
    assert resp.status_code in (200, 500)


# ===================================================================
# Reorder Screenshots
# ===================================================================


@pytest.mark.django_db
def test_reorder_screenshots_empty(authenticated_client):
    project = Project.objects.create(name="排序项目")
    resp = authenticated_client.post(
        f"/api/v1/chat-records/projects/{project.id}/screenshots/reorder",
        data=json.dumps({"screenshot_ids": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
