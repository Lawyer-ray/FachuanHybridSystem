"""Document recognition API integration tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


# ===================================================================
# Recognize document
# ===================================================================


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
@patch("apps.document_recognition.api.document_recognition_api._save_uploaded_file")
def test_recognize_document(mock_save, mock_get_svc, authenticated_client):
    mock_save.return_value = "/tmp/test_upload.pdf"

    mock_task = MagicMock()
    mock_task.id = 1
    mock_svc = MagicMock()
    mock_svc.create_task.return_value = mock_task
    mock_get_svc.return_value = mock_svc

    f = SimpleUploadedFile("document.pdf", b"fake pdf content", content_type="application/pdf")
    resp = authenticated_client.post(
        "/api/v1/document-recognition/court-document/recognize",
        {"file": f},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == 1
    assert data["status"] == "pending"


@pytest.mark.django_db
def test_recognize_document_unsupported_format(authenticated_client):
    f = SimpleUploadedFile("test.exe", b"fake exe", content_type="application/octet-stream")
    resp = authenticated_client.post(
        "/api/v1/document-recognition/court-document/recognize",
        {"file": f},
    )
    # Should return 422 or similar validation error
    assert resp.status_code in (422, 400, 500)


# ===================================================================
# Get task status
# ===================================================================


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_get_task_status_success(mock_get_svc, authenticated_client):
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.status = "success"
    mock_task.file_path = "/tmp/test.pdf"
    mock_task.renamed_file_path = "/tmp/renamed.pdf"
    mock_task.document_type = "complaint"
    mock_task.case_number = "(2026)京01民初1号"
    mock_task.key_time = None
    mock_task.confidence = 0.95
    mock_task.extraction_method = "ocr"
    mock_task.binding_success = None
    mock_task.error_message = None
    mock_task.created_at = MagicMock()
    mock_task.created_at.isoformat.return_value = "2026-01-01T00:00:00Z"
    mock_task.finished_at = MagicMock()
    mock_task.finished_at.isoformat.return_value = "2026-01-01T00:01:00Z"

    mock_svc = MagicMock()
    mock_svc.get_task.return_value = mock_task
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/document-recognition/court-document/task/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == 1
    assert data["status"] == "success"
    assert data["recognition"]["document_type"] == "complaint"


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_get_task_status_pending(mock_get_svc, authenticated_client):
    mock_task = MagicMock()
    mock_task.id = 2
    mock_task.status = "pending"
    mock_task.file_path = "/tmp/test.pdf"
    mock_task.renamed_file_path = None
    mock_task.error_message = None
    mock_task.created_at = MagicMock()
    mock_task.created_at.isoformat.return_value = "2026-01-01T00:00:00Z"
    mock_task.finished_at = None

    mock_svc = MagicMock()
    mock_svc.get_task.return_value = mock_task
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/document-recognition/court-document/task/2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["recognition"] is None


# ===================================================================
# Search cases for binding
# ===================================================================


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_search_cases_for_binding(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.search_cases_for_binding.return_value = [
        {
            "id": 1,
            "name": "测试案件",
            "case_numbers": ["(2026)京01民初1号"],
            "parties": ["原告张三", "被告李四"],
            "created_at": "2026-01-01T00:00:00Z",
        },
    ]
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/document-recognition/court-document/search-cases?q=测试")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "测试案件"


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_search_cases_empty(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.search_cases_for_binding.return_value = []
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/document-recognition/court-document/search-cases?q=不存在")
    assert resp.status_code == 200
    data = resp.json()
    assert data == []


# ===================================================================
# Manual bind case
# ===================================================================


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_case_binding_service")
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_manual_bind_case(mock_get_task_svc, mock_get_bind_svc, authenticated_client):
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.binding_success = None
    mock_task.case_id = None
    mock_task.case = None
    mock_task.case_log_id = None

    mock_task_svc = MagicMock()
    mock_task_svc.get_task.return_value = mock_task
    mock_get_task_svc.return_value = mock_task_svc

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.case_id = 10
    mock_result.case_name = "测试案件"
    mock_result.case_log_id = 5
    mock_result.message = "绑定成功"
    mock_result.error_code = None

    mock_bind_svc = MagicMock()
    mock_bind_svc.manual_bind_document_to_case.return_value = mock_result
    mock_get_bind_svc.return_value = mock_bind_svc

    resp = authenticated_client.post(
        "/api/v1/document-recognition/court-document/task/1/bind",
        data=json.dumps({"case_id": 10}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["case_id"] == 10


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_manual_bind_already_bound(mock_get_svc, authenticated_client):
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.binding_success = True
    mock_task.case_id = 5
    mock_task.case = MagicMock()
    mock_task.case.name = "已绑定案件"
    mock_task.case_log_id = 3

    mock_svc = MagicMock()
    mock_svc.get_task.return_value = mock_task
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/document-recognition/court-document/task/1/bind",
        data=json.dumps({"case_id": 10}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error_code"] == "ALREADY_BOUND"


# ===================================================================
# Update task info
# ===================================================================


@pytest.mark.django_db
@patch("apps.document_recognition.api.document_recognition_api._get_task_service")
def test_update_task_info(mock_get_svc, authenticated_client):
    mock_task = MagicMock()
    mock_task.case_number = "(2026)京01民初1号"
    mock_task.key_time = None

    mock_svc = MagicMock()
    mock_svc.update_task_info.return_value = mock_task
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/document-recognition/court-document/task/1/update-info",
        data=json.dumps({"case_number": "(2026)京01民初1号"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["case_number"] == "(2026)京01民初1号"
