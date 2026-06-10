"""Doc converter API integration tests."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.doc_converter.models import DocConverterJob, DocConverterJobStatus


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_job(user, **kwargs):
    return DocConverterJob.objects.create(
        status=kwargs.get("status", DocConverterJobStatus.PENDING),
        total_files=kwargs.get("total_files", 1),
        created_by=user,
    )


# ===================================================================
# Create conversion job
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api._service")
def test_create_conversion_job(mock_service, authenticated_client):
    mock_job = MagicMock()
    mock_job.id = uuid.uuid4()
    mock_job.status = "pending"
    mock_job.total_files = 1
    mock_service.create_job.return_value = mock_job

    f = SimpleUploadedFile("test.doc", b"fake doc content", content_type="application/msword")
    resp = authenticated_client.post(
        "/api/v1/doc-converter/jobs",
        {"files": f},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == str(mock_job.id)
    assert data["status"] == "pending"


# ===================================================================
# Get job progress
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api._service")
def test_get_conversion_progress(mock_service, authenticated_client):
    job_id = uuid.uuid4()
    mock_job = MagicMock()
    mock_job.id = job_id
    mock_job.status = "converting"
    mock_job.total_files = 1
    mock_job.converted_files = 0
    mock_job.failed_files = 0
    mock_job.progress = 50
    mock_job.cancel_requested = False
    mock_job.error_message = ""
    mock_job.created_at = "2026-01-01T00:00:00Z"
    mock_job.updated_at = "2026-01-01T00:00:00Z"
    mock_job.started_at = None
    mock_job.finished_at = None
    mock_job.output_zip = ""

    mock_service.get_job_progress.return_value = (mock_job, [])
    mock_service.build_job_payload.return_value = {
        "id": job_id,
        "status": "converting",
        "total_files": 1,
        "converted_files": 0,
        "failed_files": 0,
        "progress": 50,
        "error_message": "",
        "download_url": "",
        "created_at": "2026-01-01T00:00:00Z",
        "finished_at": None,
    }
    mock_service.build_item_payload.return_value = {}

    resp = authenticated_client.get(f"/api/v1/doc-converter/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job"]["status"] == "converting"


# ===================================================================
# Cancel job
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api._service")
def test_cancel_conversion_job(mock_service, authenticated_client):
    job_id = uuid.uuid4()
    mock_job = MagicMock()
    mock_job.status = "cancelled"
    mock_service.request_cancel.return_value = mock_job

    resp = authenticated_client.post(f"/api/v1/doc-converter/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


# ===================================================================
# Health check
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api.find_libreoffice")
def test_health_check(mock_find, authenticated_client):
    mock_find.return_value = "/usr/bin/libreoffice"

    resp = authenticated_client.get("/api/v1/doc-converter/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["libreoffice_available"] is True


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api.find_libreoffice")
def test_health_check_not_available(mock_find, authenticated_client):
    mock_find.return_value = None

    resp = authenticated_client.get("/api/v1/doc-converter/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["libreoffice_available"] is False


# ===================================================================
# Delete job
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api._service")
def test_delete_conversion_job(mock_service, authenticated_client):
    job_id = uuid.uuid4()
    mock_job = MagicMock()
    mock_job.delete = MagicMock()
    mock_service.get_job.return_value = mock_job

    resp = authenticated_client.delete(f"/api/v1/doc-converter/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"


# ===================================================================
# Save to directory
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_converter.api.doc_converter_api._service")
def test_save_to_directory(mock_service, authenticated_client):
    job_id = uuid.uuid4()
    mock_service.save_job_to_directory.return_value = {
        "saved_files": ["file1.docx"],
        "total_saved": 1,
        "target_dir": "/tmp/output",
    }

    resp = authenticated_client.post(
        f"/api/v1/doc-converter/jobs/{job_id}/save-to-dir",
        data=json.dumps({"target_dir": "/tmp/output"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_saved"] == 1
