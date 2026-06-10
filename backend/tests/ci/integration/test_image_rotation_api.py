"""Image rotation API integration tests."""

from __future__ import annotations

import json
import base64
from unittest.mock import MagicMock, patch

import pytest


# ===================================================================
# Extract PDF fast
# ===================================================================


@pytest.mark.django_db
def test_extract_pdf_fast_no_data(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/image-rotation/extract-pdf-fast",
        data=json.dumps({"filename": "test.pdf", "data": ""}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "缺少" in data["message"]


@pytest.mark.django_db
@patch("apps.image_rotation.api.image_rotation_api._get_pdf_service")
def test_extract_pdf_fast(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.extract_pages.return_value = {
        "success": True,
        "pages": [{"page_num": 1, "data": "base64data", "width": 800, "height": 600}],
        "total_pages": 1,
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/image-rotation/extract-pdf-fast",
        data=json.dumps({"filename": "test.pdf", "data": base64.b64encode(b"fake pdf").decode()}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ===================================================================
# Detect page orientation
# ===================================================================


@pytest.mark.django_db
def test_detect_page_orientation_no_data(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/image-rotation/detect-page-orientation",
        data=json.dumps({"data": ""}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rotation"] == 0
    assert data["confidence"] == 0


@pytest.mark.django_db
@patch("apps.image_rotation.api.image_rotation_api._get_pdf_service")
def test_detect_page_orientation(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.detect_single_page_orientation.return_value = {
        "rotation": 0,
        "confidence": 0.95,
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/image-rotation/detect-page-orientation",
        data=json.dumps({"data": base64.b64encode(b"fake image").decode()}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rotation"] == 0
    assert data["confidence"] == 0.95


# ===================================================================
# Detect orientation (batch)
# ===================================================================


@pytest.mark.django_db
def test_detect_orientation_no_images(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/image-rotation/detect-orientation",
        data=json.dumps({"images": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.django_db
@patch("apps.image_rotation.api.image_rotation_api._get_pdf_service")
def test_detect_orientation(mock_get_svc, authenticated_client):
    mock_orientation_svc = MagicMock()
    mock_orientation_svc.detect_orientation_with_text.return_value = {
        "rotation": 0,
        "confidence": 0.9,
        "ocr_text": "test text",
    }
    mock_svc = MagicMock()
    mock_svc.orientation_service = mock_orientation_svc
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/image-rotation/detect-orientation",
        data=json.dumps({"images": [{"filename": "img.jpg", "data": base64.b64encode(b"fake").decode()}]}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["results"]) == 1


# ===================================================================
# Suggest rename
# ===================================================================


@pytest.mark.django_db
def test_suggest_rename_no_items(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/image-rotation/suggest-rename",
        data=json.dumps({"items": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["suggestions"] == []


@pytest.mark.django_db
@patch("apps.image_rotation.api.image_rotation_api._get_rename_service")
def test_suggest_rename(mock_get_svc, authenticated_client):
    mock_suggestion = MagicMock()
    mock_suggestion.original_filename = "scan001.jpg"
    mock_suggestion.suggested_filename = "对账单_2026年1月.jpg"
    mock_suggestion.date = "2026-01-15"
    mock_suggestion.amount = "5000"
    mock_suggestion.success = True

    mock_svc = MagicMock()
    mock_svc.suggest_rename_batch.return_value = [mock_suggestion]
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/image-rotation/suggest-rename",
        data=json.dumps({"items": [{"filename": "scan001.jpg", "ocr_text": "对账单"}]}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["suggestions"]) == 1


# ===================================================================
# Export PDF
# ===================================================================


@pytest.mark.django_db
def test_export_pdf_no_pages(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/image-rotation/export-pdf",
        data=json.dumps({"pages": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "没有页面" in data["message"]


@pytest.mark.django_db
@patch("apps.image_rotation.api.image_rotation_api._get_rotation_service")
def test_export_pdf(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.export_as_pdf.return_value = {
        "success": True,
        "pdf_url": "/tmp/output.pdf",
        "total_pages": 1,
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/image-rotation/export-pdf",
        data=json.dumps({
            "pages": [{"filename": "page1.jpg", "data": base64.b64encode(b"fake").decode(), "rotation": 0}],
            "paper_size": "a4",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ===================================================================
# Export images
# ===================================================================


@pytest.mark.django_db
def test_export_images_no_images(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/image-rotation/export",
        data=json.dumps({"images": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "没有图片" in data["message"]


@pytest.mark.django_db
@patch("apps.image_rotation.api.image_rotation_api._get_rotation_service")
def test_export_images(mock_get_svc, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.export_images.return_value = {
        "success": True,
        "zip_url": "/tmp/output.zip",
        "total_images": 1,
    }
    mock_get_svc.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/image-rotation/export",
        data=json.dumps({
            "images": [{"filename": "img.jpg", "data": base64.b64encode(b"fake").decode(), "format": "jpeg"}],
            "paper_size": "original",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
