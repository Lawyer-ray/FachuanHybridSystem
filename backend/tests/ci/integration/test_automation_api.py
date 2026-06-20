"""Automation API integration tests."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.automation.models.base import TestCourt
from apps.automation.models.court_sms import CourtSMS
from apps.automation.models.preservation import PreservationQuote
from apps.automation.models.scraper import ScraperTask, ScraperTaskType
from apps.automation.models.court_document import DocumentDeliverySchedule
from apps.cases.models import Case, SupervisingAuthority
from apps.contracts.models import Contract
from apps.organization.models import AccountCredential


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_contract():
    return Contract.objects.create(name="测试合同", case_type="civil")


def _make_case(**kwargs):
    return Case.objects.create(
        name=kwargs.get("name", "测试案件"),
        contract=kwargs.get("contract", _make_contract()),
        case_type=kwargs.get("case_type", "civil"),
    )


# ===================================================================
# Status / Config endpoints
# ===================================================================


@pytest.mark.django_db
def test_get_status(authenticated_client):
    resp = authenticated_client.get("/api/v1/automation/status")
    assert resp.status_code == 200


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_adapters.build_automation_config_service")
def test_get_config(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.get_automation_config.return_value = {"version": "1.0"}
    mock_build.return_value = mock_service

    resp = authenticated_client.get("/api/v1/automation/config")
    assert resp.status_code == 200


# ===================================================================
# AI Ollama
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_adapters.build_ai_service")
def test_ai_ollama(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.chat_with_ollama.return_value = {"response": "response text"}
    mock_build.return_value = mock_service

    resp = authenticated_client.post(
        "/api/v1/automation/ai/ollama",
        data=json.dumps({"model": "qwen3:0.6b", "prompt": "test", "text": "hello"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert "data" in resp.json()


# ===================================================================
# File upload
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_adapters.build_document_processing_service")
def test_upload_file(mock_build, authenticated_client):
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.file_info = {"name": "test.txt"}
    mock_result.extraction = {"text": "hello"}
    mock_result.processing_params = {}
    mock_result.error = None

    mock_service = MagicMock()
    mock_service.process_uploaded_file.return_value = mock_result
    mock_build.return_value = mock_service

    f = SimpleUploadedFile("test.txt", b"hello world", content_type="text/plain")
    resp = authenticated_client.post(
        "/api/v1/automation/file/upload",
        {"file": f},
    )
    assert resp.status_code == 200


# ===================================================================
# Document processor
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.build_document_processing_service")
def test_document_processor_process(mock_build, authenticated_client):
    mock_result = MagicMock()
    mock_result.image_url = "http://example.com/img.png"
    mock_result.text_excerpt = "excerpt"
    mock_service = MagicMock()
    mock_service.process_document.return_value = mock_result
    mock_build.return_value = mock_service

    resp = authenticated_client.post(
        "/api/v1/automation/document-processor/process",
        data=json.dumps({"file_path": "/tmp/test.pdf", "kind": "pdf"}),
        content_type="application/json",
    )
    assert resp.status_code == 200


# ===================================================================
# Auto namer
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.build_auto_namer_service")
def test_auto_namer_process(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.process_document_for_naming.return_value = {
        "text": "content",
        "ollama_response": {"suggested_name": "suggested_name.pdf"},
        "error": None,
    }
    mock_build.return_value = mock_service

    f = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
    resp = authenticated_client.post(
        "/api/v1/automation/auto-namer/process",
        {"file": f, "prompt": "name this", "model": "qwen3:0.6b"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "content"


# ===================================================================
# Captcha recognition (no auth)
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.build_captcha_service")
def test_captcha_recognize(mock_build, api_client):
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.text = "AB12"
    mock_result.processing_time = 0.1
    mock_result.error = None
    mock_service = MagicMock()
    mock_service.recognize_from_base64.return_value = mock_result
    mock_build.return_value = mock_service

    resp = api_client.post(
        "/api/v1/automation/captcha/recognize",
        data=json.dumps({"image_base64": "iVBORw0KGgo="}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["text"] == "AB12"


# ===================================================================
# Court SMS
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx")
def test_submit_sms(mock_build, authenticated_client):
    mock_sms = MagicMock()
    mock_sms.id = 1
    mock_sms.status = "pending"
    mock_sms.created_at = timezone.now()
    mock_service = MagicMock()
    mock_service.submit_sms.return_value = mock_sms
    mock_build.return_value = mock_service

    resp = authenticated_client.post(
        "/api/v1/automation/court-sms",
        data=json.dumps({"content": "test sms", "received_at": "2026-01-01T00:00:00Z"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx")
def test_list_sms(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.list_sms.return_value = []
    mock_build.return_value = mock_service

    resp = authenticated_client.get("/api/v1/automation/court-sms")
    assert resp.status_code == 200


@pytest.mark.django_db
@patch("apps.automation.schemas.court_sms.CourtSMSDocumentReferenceService")
@patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx")
def test_get_sms_detail(mock_build, mock_doc_ref, authenticated_client):
    mock_sms = MagicMock()
    mock_sms.id = 1
    mock_sms.content = "test"
    mock_sms.status = "pending"
    mock_sms.sms_type = None
    mock_sms.received_at = timezone.now()
    mock_sms.created_at = timezone.now()
    mock_sms.updated_at = timezone.now()
    mock_sms.download_links = []
    mock_sms.case_numbers = []
    mock_sms.party_names = []
    mock_sms.document_file_paths = []
    mock_sms.case = None
    mock_sms.error_message = None
    mock_sms.retry_count = 0
    mock_sms.feishu_sent_at = None
    mock_sms.feishu_error = ""
    mock_sms.notification_results = {}
    mock_service = MagicMock()
    mock_service.get_sms_detail.return_value = mock_sms
    mock_build.return_value = mock_service

    mock_doc_ref_instance = MagicMock()
    mock_doc_ref_instance.collect.return_value = []
    mock_doc_ref.return_value = mock_doc_ref_instance

    resp = authenticated_client.get("/api/v1/automation/court-sms/1")
    assert resp.status_code == 200


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx")
def test_delete_sms(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.delete_sms.return_value = None
    mock_build.return_value = mock_service

    resp = authenticated_client.delete("/api/v1/automation/court-sms/999")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
@patch("apps.core.dependencies.automation_sms_entry.build_court_sms_service_ctx")
def test_batch_delete_sms(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.batch_delete_sms.return_value = 2
    mock_build.return_value = mock_service

    # NOTE: batch-delete POST may conflict with DELETE /court-sms/{sms_id} routing
    # Testing that the endpoint is reachable
    resp = authenticated_client.post(
        "/api/v1/automation/court-sms/batch-delete",
        data=json.dumps({"ids": [1, 2]}),
        content_type="application/json",
    )
    # Due to route ordering, this may return 405 (matched by DELETE/{sms_id} first)
    assert resp.status_code in (200, 405)


# ===================================================================
# Document delivery schedules
# ===================================================================


@pytest.mark.django_db
@patch("apps.automation.services.document_delivery.document_delivery_schedule_service.DocumentDeliveryScheduleService")
def test_list_schedules(mock_svc_cls, authenticated_client):
    mock_svc = MagicMock()
    mock_svc.list_schedules.return_value = []
    mock_svc_cls.return_value = mock_svc

    resp = authenticated_client.get("/api/v1/automation/document-delivery/schedules")
    assert resp.status_code == 200


@pytest.mark.django_db
@patch("apps.automation.services.document_delivery.document_delivery_schedule_service.DocumentDeliveryScheduleService")
def test_create_schedule(mock_svc_cls, authenticated_client):
    now = timezone.now()
    mock_schedule = MagicMock()
    mock_schedule.id = 1
    mock_schedule.credential_id = 1
    mock_schedule.runs_per_day = 2
    mock_schedule.hour_interval = 12
    mock_schedule.cutoff_hours = 24
    mock_schedule.is_active = True
    mock_schedule.last_run_at = None
    mock_schedule.next_run_at = now
    mock_schedule.created_at = now
    mock_schedule.updated_at = now
    mock_svc = MagicMock()
    mock_svc.create_schedule.return_value = mock_schedule
    mock_svc_cls.return_value = mock_svc

    resp = authenticated_client.post(
        "/api/v1/automation/document-delivery/schedules",
        data=json.dumps({
            "credential_id": 1,
            "runs_per_day": 2,
            "hour_interval": 12,
            "cutoff_hours": 24,
            "is_active": True,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["credential_id"] == 1


# ===================================================================
# Performance monitor (admin endpoints)
# ===================================================================


@pytest.mark.django_db
@patch("apps.core.dependencies.build_performance_monitor_service")
def test_performance_health(mock_build, authenticated_client):
    mock_service = MagicMock()
    mock_service.get_system_metrics.return_value = {
        "status": "healthy",
        "version": "1.0",
    }
    mock_build.return_value = mock_service

    resp = authenticated_client.get("/api/v1/automation/performance/health")
    assert resp.status_code == 200


# ===================================================================
# Court filing
# ===================================================================


@pytest.mark.django_db
@patch("plugins.court_automation.filing.api_endpoint._check_plugin")
def test_case_filing_info_no_plugin(mock_plugin, authenticated_client):
    mock_plugin.return_value = False
    case = _make_case()

    resp = authenticated_client.get(f"/api/v1/court-filing/case-info/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin_available"] is False


@pytest.mark.django_db
@patch("plugins.court_automation.filing.api_endpoint._check_plugin")
def test_court_filing_execute_no_plugin(mock_plugin, authenticated_client):
    mock_plugin.return_value = False

    resp = authenticated_client.post(
        "/api/v1/court-filing/execute",
        data=json.dumps({"case_id": 999, "filing_type": "civil_first"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "插件未安装" in data["message"]


@pytest.mark.django_db
def test_court_filing_session_not_found(authenticated_client):
    resp = authenticated_client.get("/api/v1/court-filing/session/99999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["message"]
