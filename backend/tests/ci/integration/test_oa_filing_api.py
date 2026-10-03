"""OA filing API integration tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.organization.models import AccountCredential

# ===================================================================
# OA Filing configs
# ===================================================================


@pytest.mark.django_db
def test_list_oa_configs(authenticated_client):
    resp = authenticated_client.get("/api/v1/oa-filing/configs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Should contain at least the supported site
    if data:
        assert "oa_system_name" in data[0]


# ===================================================================
# OA Filing session (not found)
# ===================================================================


@pytest.mark.django_db
def test_get_filing_session_not_found(authenticated_client):
    resp = authenticated_client.get("/api/v1/oa-filing/session/99999")
    assert resp.status_code == 404


# ===================================================================
# Case import
# ===================================================================


@pytest.mark.django_db
@patch("apps.oa_filing.services.import_session_service.get_credential")
def test_trigger_case_import_no_credential(mock_cred, authenticated_client):
    mock_cred.return_value = None

    f = SimpleUploadedFile("cases.xlsx", b"fake excel", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp = authenticated_client.post(
        "/api/v1/case-import",
        {"file": f},
    )
    # 缺 OA 凭证抛 ValidationException 400（旧实现返回裸 {"error"} 且会撞
    # CaseImportSessionOut 响应 schema 导致 500）
    assert resp.status_code == 400
    assert "未找到OA账号凭证" in resp.json()["message"]


@pytest.mark.django_db
def test_get_case_import_session_not_found(authenticated_client):
    resp = authenticated_client.get("/api/v1/case-import/99999")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_execute_case_import_session_not_found(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/case-import/99999/execute",
        data=json.dumps({"case_nos": ["CASE-001"]}),
        content_type="application/json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_get_case_import_preview_not_found(authenticated_client):
    resp = authenticated_client.get("/api/v1/case-import/99999/preview")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_batch_create_cases_session_not_found(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/case-import/99999/batch-create",
        data=json.dumps({"cases": [{"case_no": "CASE-001"}]}),
        content_type="application/json",
    )
    # 会话不存在走 NotFoundError 404，与其他 case-import 端点同语义
    assert resp.status_code == 404
    assert "会话不存在" in resp.json()["message"]


# ===================================================================
# Client import
# ===================================================================


@pytest.mark.django_db
@patch("apps.oa_filing.services.import_session_service.get_credential")
def test_trigger_client_import_no_credential(mock_cred, authenticated_client):
    mock_cred.return_value = None

    resp = authenticated_client.post(
        "/api/v1/client-import",
        data=json.dumps({"headless": True}),
        content_type="application/json",
    )
    # 缺 OA 凭证抛 ValidationException 400（旧实现返回裸 {"error"} 且会撞
    # ClientImportSessionOut 响应 schema 导致 500）
    assert resp.status_code == 400
    assert "未找到OA账号凭证" in resp.json()["message"]


@pytest.mark.django_db
def test_get_client_import_session_not_found(authenticated_client):
    resp = authenticated_client.get("/api/v1/client-import/99999")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_batch_create_clients_session_not_found(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client-import/99999/batch-create",
        data=json.dumps({"customers": [{"name": "test", "client_type": "natural"}]}),
        content_type="application/json",
    )
    assert resp.status_code == 404
