"""Invoice recognition API integration tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.automation.models.invoice_recognition import InvoiceRecognitionTask, InvoiceRecognitionTaskStatus


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_invoice_task(**kwargs):
    return InvoiceRecognitionTask.objects.create(
        name=kwargs.get("name", "测试发票任务"),
        status=kwargs.get("status", InvoiceRecognitionTaskStatus.PENDING),
    )


# ===================================================================
# Quick recognize
# ===================================================================


@pytest.mark.django_db
@patch("apps.invoice_recognition.api.invoice_recognition_api._get_quick_recognition_service")
def test_quick_recognize(mock_get_svc, authenticated_client):
    mock_result = MagicMock()
    mock_result.filename = "invoice.pdf"
    mock_result.success = True
    mock_result.data = MagicMock()
    mock_result.data.invoice_code = "123456"
    mock_result.data.invoice_number = "789012"
    mock_result.data.invoice_date = "2026-01-01"
    mock_result.data.amount = "1000.00"
    mock_result.data.tax_amount = "130.00"
    mock_result.data.total_amount = "1130.00"
    mock_result.data.buyer_name = "买方公司"
    mock_result.data.seller_name = "卖方公司"
    mock_result.data.project_name = "咨询服务"
    mock_result.data.category = "vat_special"
    mock_result.error = None

    mock_svc = MagicMock()
    mock_svc.recognize_files.return_value = [mock_result]
    mock_get_svc.return_value = mock_svc

    f = SimpleUploadedFile("invoice.pdf", b"fake pdf", content_type="application/pdf")
    resp = authenticated_client.post(
        "/api/v1/invoice-recognition/quick-recognize",
        {"files": f},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["success"] is True


# ===================================================================
# Upload invoices to task
# ===================================================================


@pytest.mark.django_db
@patch("apps.invoice_recognition.api.invoice_recognition_api._get_recognition_service")
def test_upload_invoices(mock_get_svc, authenticated_client):
    task = _make_invoice_task()

    mock_record = MagicMock()
    mock_record.id = 1
    mock_record.original_filename = "invoice.pdf"
    mock_record.status = "success"
    mock_record.invoice_code = "123456"
    mock_record.invoice_number = "789012"
    mock_record.is_duplicate = False
    mock_record.category = "vat_special"

    mock_svc = MagicMock()
    mock_svc.upload_and_recognize.return_value = [mock_record]
    mock_get_svc.return_value = mock_svc

    f = SimpleUploadedFile("invoice.pdf", b"fake pdf", content_type="application/pdf")
    resp = authenticated_client.post(
        f"/api/v1/invoice-recognition/{task.id}/upload",
        {"files": f},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 1


# ===================================================================
# Task status
# ===================================================================


@pytest.mark.django_db
@patch("apps.invoice_recognition.api.invoice_recognition_api._get_recognition_service")
def test_get_task_status(mock_get_svc, authenticated_client):
    task = _make_invoice_task(status=InvoiceRecognitionTaskStatus.COMPLETED)

    mock_svc = MagicMock()
    mock_svc.get_task_status.return_value = {
        "task_id": task.id,
        "name": task.name,
        "status": "completed",
        "records": [],
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get(f"/api/v1/invoice-recognition/{task.id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"


@pytest.mark.django_db
@patch("apps.invoice_recognition.api.invoice_recognition_api._get_recognition_service")
def test_get_task_status_not_found(mock_get_svc, authenticated_client):
    from django.core.exceptions import ObjectDoesNotExist

    mock_svc = MagicMock()
    mock_svc.get_task_status.side_effect = ObjectDoesNotExist("Task not found")
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/invoice-recognition/99999/status")
    assert resp.status_code == 404


# ===================================================================
# Download
# ===================================================================


@pytest.mark.django_db
@patch("apps.invoice_recognition.api.invoice_recognition_api._get_download_service")
def test_download_invoices_all(mock_get_svc, authenticated_client):
    task = _make_invoice_task(status=InvoiceRecognitionTaskStatus.COMPLETED)

    mock_svc = MagicMock()
    mock_svc.download_all.return_value = (b"fake zip data", "invoices.zip")
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.get(
        f"/api/v1/invoice-recognition/{task.id}/download?scope=all&fmt=zip"
    )
    assert resp.status_code == 200
    assert resp["Content-Disposition"].startswith("attachment")
