"""Evidence sorting API integration tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===================================================================
# Classify
# ===================================================================


@pytest.mark.django_db
def test_classify_no_images(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/evidence-sorting/classify",
        data=json.dumps({"images": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "没有图片" in data["message"]


@pytest.mark.django_db
@patch("apps.evidence_sorting.services.classifier.ClassifierService")
def test_classify_images(mock_svc_cls, authenticated_client):
    mock_result = MagicMock()
    mock_img = MagicMock()
    mock_img.filename = "test.jpg"
    mock_img.category = "statement"
    mock_img.ocr_text = "text"
    mock_img.date = "2026-01-01"
    mock_img.amount = "1000"
    mock_img.signed = True
    mock_img.confidence = 0.9
    mock_img.rotation = 0
    mock_result.images = [mock_img]
    mock_result.errors = []

    mock_svc = MagicMock()
    mock_svc.classify_images_async = AsyncMock(return_value=mock_result)
    mock_svc_cls.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/evidence-sorting/classify",
        data=json.dumps({"images": [{"filename": "test.jpg", "data": "base64data"}]}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["images"]) == 1


# ===================================================================
# Parse statement
# ===================================================================


@pytest.mark.django_db
def test_parse_statement_no_text(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/evidence-sorting/parse-statement",
        data=json.dumps({"ocr_text": ""}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "缺少" in data["message"]


@pytest.mark.django_db
@patch("apps.evidence_sorting.services.reconciler.ReconcilerService")
def test_parse_statement(mock_svc_cls, authenticated_client):
    mock_info = MagicMock()
    mock_info.month = "2026-01"
    mock_info.total_amount = 5000.00
    mock_info.signed = True
    mock_li = MagicMock()
    mock_li.date = "2026-01-15"
    mock_li.amount = 5000.00
    mock_li.description = "货款"
    mock_info.line_items = [mock_li]

    mock_svc = MagicMock()
    mock_svc.parse_statement_async = AsyncMock(return_value=mock_info)
    mock_svc_cls.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/evidence-sorting/parse-statement",
        data=json.dumps({"ocr_text": "对账单 2026年1月 应付5000元"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["month"] == "2026-01"


# ===================================================================
# Reconcile
# ===================================================================


@pytest.mark.django_db
@patch("apps.evidence_sorting.services.reconciler.ReconcilerService")
def test_reconcile(mock_svc_cls, authenticated_client):
    mock_group = MagicMock()
    mock_group.month = "2026-01"
    mock_group.folder_name = "2026-01"
    mock_group.issues = []
    mock_group.statement = MagicMock(
        filename="stmt.pdf", month="2026-01", total_amount=5000.00, signed=True, line_items=[]
    )
    mock_group.deliveries = []

    mock_result = MagicMock()
    mock_result.month_groups = [mock_group]
    mock_result.unsigned_statements = []
    mock_result.receipts = []
    mock_result.others = []
    mock_result.unmatched_deliveries = []

    mock_svc = MagicMock()
    mock_svc.reconcile_async = AsyncMock(return_value=mock_result)
    mock_svc_cls.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/evidence-sorting/reconcile",
        data=json.dumps({
            "statements": [{"filename": "stmt.pdf", "ocr_text": "text"}],
            "deliveries": [],
            "receipts": [],
            "others": [],
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["month_groups"]) == 1


# ===================================================================
# Export
# ===================================================================


@pytest.mark.django_db
@patch("apps.evidence_sorting.services.exporter.ExporterService")
@patch("apps.evidence_sorting.services.reconciler.ReconcilerService")
def test_export_zip(mock_reconciler_cls, mock_exporter_cls, authenticated_client):
    mock_result = MagicMock()
    mock_reconciler = MagicMock()
    mock_reconciler.reconcile_async = AsyncMock(return_value=mock_result)
    mock_reconciler_cls.return_value = mock_reconciler

    mock_exporter = MagicMock()
    mock_exporter.export_zip.return_value = {"success": True, "zip_url": "/tmp/export.zip"}
    mock_exporter_cls.return_value = mock_exporter

    resp = authenticated_client.post(
        "/api/v1/evidence-sorting/export",
        data=json.dumps({
            "statements": [],
            "deliveries": [],
            "receipts": [],
            "others": [],
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ===================================================================
# LLM options
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.llm.get_llm_service")
def test_llm_options(mock_llm, authenticated_client):
    mock_backend = MagicMock()
    mock_backend.is_available.return_value = True
    mock_backend.get_default_model.return_value = "qwen3:0.6b"

    mock_llm_svc = MagicMock()
    mock_llm_svc.get_backend.return_value = mock_backend
    mock_llm.return_value = mock_llm_svc

    resp = authenticated_client.get("/api/v1/evidence-sorting/llm-options")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "backends" in data
