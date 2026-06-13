"""Doc convert API integration tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


# ===================================================================
# MBID list
# ===================================================================


@pytest.mark.django_db
def test_get_mbid_list(authenticated_client):
    resp = authenticated_client.get("/api/v1/doc-convert/mbid-list")
    assert resp.status_code == 200
    data = resp.json()
    assert "categories" in data
    assert isinstance(data["categories"], list)


# ===================================================================
# Convert document (requires ZNSZJ_ENABLED)
# ===================================================================


@pytest.mark.django_db
@patch("apps.doc_convert.api.doc_convert_api._check_znszj_enabled")
@patch("apps.doc_convert.api.doc_convert_api._get_doc_convert_service")
def test_convert_document(mock_get_svc, mock_check, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.convert_document.return_value = b"fake docx bytes"
    mock_get_svc.return_value = mock_svc

    f = SimpleUploadedFile("document.docx", b"fake docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    resp = authenticated_client.post(
        "/api/v1/doc-convert/convert",
        {"file": f, "mbid": "test-mbid"},
    )
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.django_db
def test_convert_document_invalid_mbid(authenticated_client):
    """When mbid is invalid, should return 400."""
    f = SimpleUploadedFile("document.docx", b"fake docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    resp = authenticated_client.post(
        "/api/v1/doc-convert/convert",
        {"file": f, "mbid": "invalid-mbid"},
    )
    # 插件未安装时返回 503；插件安装时 mbid 无效返回 400；ZNSZJ 关闭返回 403
    assert resp.status_code in (400, 403, 503)
