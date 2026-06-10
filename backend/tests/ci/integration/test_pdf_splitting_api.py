"""PDF Splitting API integration tests."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest


@pytest.mark.django_db
def test_create_pdf_split_job(authenticated_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("test.pdf", b"%PDF-1.4 fake content", content_type="application/pdf")
    with patch("apps.pdf_splitting.services.PdfSplitJobService.create_job") as mock_create:
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "pending"
        mock_create.return_value = mock_job
        resp = authenticated_client.post(
            "/api/v1/pdf-splitting/jobs",
            {"file": upload, "template_key": "filing_materials_v1", "split_mode": "content_analysis"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"


@pytest.mark.django_db
def test_get_pdf_split_job(authenticated_client):
    job_id = uuid4()
    with patch("apps.pdf_splitting.services.PdfSplitJobService.get_job") as mock_get, \
         patch("apps.pdf_splitting.services.PdfSplitJobService.build_job_payload") as mock_payload:
        mock_job = MagicMock()
        mock_get.return_value = mock_job
        mock_payload.return_value = {
            "job_id": str(job_id),
            "status": "completed",
            "split_mode": "content_analysis",
            "ocr_profile": "balanced",
            "progress": 100,
            "total_pages": 10,
            "processed_pages": 10,
            "current_page": 10,
            "summary": {"total_segments": 3},
            "segments": [],
        }
        resp = authenticated_client.get(f"/api/v1/pdf-splitting/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == str(job_id)
        assert data["status"] == "completed"


@pytest.mark.django_db
def test_confirm_pdf_split_job(authenticated_client):
    job_id = uuid4()
    with patch("apps.pdf_splitting.services.PdfSplitJobService.confirm_segments") as mock_confirm:
        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.status = "confirmed"
        mock_confirm.return_value = mock_job
        resp = authenticated_client.post(
            f"/api/v1/pdf-splitting/jobs/{job_id}/confirm",
            data='{"segments": [{"page_start": 1, "page_end": 5, "segment_type": "complaint", "filename": "起诉状.pdf"}]}',
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"


@pytest.mark.django_db
def test_cancel_pdf_split_job(authenticated_client):
    job_id = uuid4()
    with patch("apps.pdf_splitting.services.PdfSplitJobService.request_cancel") as mock_cancel:
        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.status = "cancelled"
        mock_cancel.return_value = mock_job
        resp = authenticated_client.post(f"/api/v1/pdf-splitting/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"


@pytest.mark.django_db
def test_get_pdf_split_download_not_found(authenticated_client):
    job_id = uuid4()
    with patch("apps.pdf_splitting.services.PdfSplitJobService.get_job") as mock_get, \
         patch("apps.pdf_splitting.services.storage.PdfSplitStorage") as mock_storage:
        mock_get.return_value = MagicMock()
        storage_instance = MagicMock()
        storage_instance.export_zip_path.exists.return_value = False
        mock_storage.return_value = storage_instance
        resp = authenticated_client.get(f"/api/v1/pdf-splitting/jobs/{job_id}/download")
        assert resp.status_code == 404


@pytest.mark.django_db
def test_get_pdf_split_raw_not_found(authenticated_client):
    job_id = uuid4()
    with patch("apps.pdf_splitting.services.PdfSplitJobService.get_job") as mock_get, \
         patch("apps.pdf_splitting.services.storage.PdfSplitStorage") as mock_storage:
        mock_job = MagicMock()
        mock_job.source_original_name = "test.pdf"
        mock_get.return_value = mock_job
        storage_instance = MagicMock()
        storage_instance.source_pdf_path.exists.return_value = False
        mock_storage.return_value = storage_instance
        resp = authenticated_client.get(f"/api/v1/pdf-splitting/jobs/{job_id}/pdf")
        assert resp.status_code == 404
