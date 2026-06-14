"""Contract review API integration tests."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.contract_review.models.review_task import ReviewTask


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_review_task(user, **kwargs):
    return ReviewTask.objects.create(
        user=user,
        original_file=kwargs.get("original_file", "/tmp/test.docx"),
        status=kwargs.get("status", ReviewTask._meta.get_field("status").default),
        contract_title=kwargs.get("contract_title", "测试合同"),
        party_a=kwargs.get("party_a", "甲方公司"),
        party_b=kwargs.get("party_b", "乙方公司"),
    )


# ===================================================================
# Upload
# ===================================================================


@pytest.mark.django_db
@patch("apps.contract_review.api.review_api._get_review_service")
def test_upload_contract(mock_build, authenticated_client):
    mock_task = MagicMock()
    mock_task.id = uuid.uuid4()
    mock_task.status = "uploaded"
    mock_task.contract_title = "测试合同"
    mock_task.party_a = "甲方"
    mock_task.party_b = "乙方"
    mock_task.party_c = ""
    mock_task.party_d = ""

    mock_svc = MagicMock()
    mock_svc.upload_contract.return_value = mock_task
    mock_build.return_value = mock_svc

    f = SimpleUploadedFile("contract.docx", b"fake docx content", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    resp = authenticated_client.post(
        "/api/v1/contract-review/upload",
        {"file": f, "model_name": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == str(mock_task.id)
    assert data["status"] == "uploaded"


# ===================================================================
# Confirm party
# ===================================================================


@pytest.mark.django_db
@patch("apps.contract_review.api.review_api._get_review_service")
def test_confirm_party(mock_build, authenticated_client):
    from apps.organization.models import Lawyer

    user = Lawyer.objects.get(username="testuser")
    task = _make_review_task(user)

    mock_task = MagicMock()
    mock_task.id = task.id
    mock_task.status = "confirmed"
    mock_task.current_step = "contract_review"
    mock_task.error_message = None
    mock_task.output_filename = None

    mock_svc = MagicMock()
    mock_svc.get_task_status.return_value = mock_task
    mock_svc.confirm_party.return_value = mock_task
    mock_build.return_value = mock_svc

    resp = authenticated_client.post(
        f"/api/v1/contract-review/{task.id}/confirm-party",
        data=json.dumps({
            "represented_party": "party_a",
            "reviewer_name": "法穿AI",
            "selected_steps": ["contract_review"],
            "party_a": "甲方修正",
            "party_b": "",
            "party_c": "",
            "party_d": "",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "confirmed"


# ===================================================================
# Task status
# ===================================================================


@pytest.mark.django_db
@patch("apps.contract_review.api.review_api._get_review_service")
def test_get_task_status(mock_build, authenticated_client):
    from apps.organization.models import Lawyer

    user = Lawyer.objects.get(username="testuser")
    task = _make_review_task(user)

    mock_task = MagicMock()
    mock_task.id = task.id
    mock_task.status = "uploaded"
    mock_task.current_step = ""
    mock_task.error_message = None
    mock_task.output_file = ""

    mock_svc = MagicMock()
    mock_svc.get_task_status.return_value = mock_task
    mock_build.return_value = mock_svc

    resp = authenticated_client.get(f"/api/v1/contract-review/{task.id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == str(task.id)


# ===================================================================
# Models list
# ===================================================================


@pytest.mark.django_db
@patch("apps.contract_review.api.review_api._get_model_list_service")
def test_get_models(mock_build, authenticated_client):
    mock_result = MagicMock()
    mock_result.models = [{"id": "qwen3:0.6b", "name": "Qwen3"}]
    mock_result.is_fallback = False
    mock_result.error_message = None
    mock_svc = MagicMock()
    mock_svc.get_result.return_value = mock_result
    mock_build.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/contract-review/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data


# ===================================================================
# Format normalize
# ===================================================================


@pytest.mark.django_db
def test_normalize_format_task_not_found(authenticated_client):
    fake_id = uuid.uuid4()
    resp = authenticated_client.post(
        "/api/v1/contract-review/format/normalize",
        data=json.dumps({"task_id": str(fake_id)}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "不存在" in data["message"]


@pytest.mark.django_db
def test_download_normalized_not_found(authenticated_client):
    fake_id = uuid.uuid4()
    resp = authenticated_client.get(f"/api/v1/contract-review/format/{fake_id}/download-normalized")
    assert resp.status_code == 404
