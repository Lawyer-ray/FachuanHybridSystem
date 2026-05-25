from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.batch_printing.models import PrintKeywordRule, PrintPresetSnapshot


@pytest.mark.django_db
def test_batch_printing_rule_and_preset_endpoints_support_full_crud(authenticated_client) -> None:
    now = timezone.now()
    preset_a = PrintPresetSnapshot.objects.create(
        printer_name="canonprinter",
        printer_display_name="Canon Printer",
        preset_name="黑白双面",
        preset_source="mac_plist",
        raw_settings_payload={"number-up": "1"},
        executable_options_payload={"sides": "two-sided-long-edge"},
        supported_option_names=["sides"],
        last_synced_at=now,
    )
    preset_b = PrintPresetSnapshot.objects.create(
        printer_name="epsonprinter",
        printer_display_name="Epson Printer",
        preset_name="彩色单面",
        preset_source="mac_plist",
        raw_settings_payload={"ColorModel": "RGB"},
        executable_options_payload={"ColorModel": "RGB"},
        supported_option_names=["ColorModel"],
        last_synced_at=now,
    )
    existing_rule = PrintKeywordRule.objects.create(
        keyword="归档",
        priority=10,
        enabled=True,
        printer_name=preset_a.printer_name,
        preset_snapshot=preset_a,
        notes="默认规则",
    )

    list_presets_response = authenticated_client.get(
        "/api/v1/batch-printing/presets",
        {"keyword": "Printer"},
    )
    assert list_presets_response.status_code == 200
    preset_payload = list_presets_response.json()
    assert {item["id"] for item in preset_payload} == {preset_a.id, preset_b.id}
    preset_a_payload = next(item for item in preset_payload if item["id"] == preset_a.id)
    assert preset_a_payload["rule_count"] == 1
    assert preset_a_payload["preset_name"] == "黑白双面"

    preset_detail_response = authenticated_client.get(f"/api/v1/batch-printing/presets/{preset_a.id}")
    assert preset_detail_response.status_code == 200
    assert preset_detail_response.json()["printer_name"] == "canonprinter"

    list_rules_response = authenticated_client.get(
        "/api/v1/batch-printing/rules",
        {"enabled": "true", "keyword": "归档"},
    )
    assert list_rules_response.status_code == 200
    rules_payload = list_rules_response.json()
    assert len(rules_payload) == 1
    assert rules_payload[0]["id"] == existing_rule.id
    assert rules_payload[0]["printer_name"] == preset_a.printer_name

    create_rule_response = authenticated_client.post(
        "/api/v1/batch-printing/rules",
        data=json.dumps(
            {
                "keyword": "起诉状",
                "priority": 30,
                "enabled": True,
                "preset_snapshot_id": preset_b.id,
                "notes": "新规则",
            }
        ),
        content_type="application/json",
    )
    assert create_rule_response.status_code == 200
    created_rule_payload = create_rule_response.json()
    assert created_rule_payload["preset_snapshot_id"] == preset_b.id
    assert created_rule_payload["printer_name"] == preset_b.printer_name

    created_rule = PrintKeywordRule.objects.get(id=created_rule_payload["id"])
    assert created_rule.printer_name == preset_b.printer_name
    assert created_rule.notes == "新规则"

    rule_detail_response = authenticated_client.get(f"/api/v1/batch-printing/rules/{created_rule.id}")
    assert rule_detail_response.status_code == 200
    assert rule_detail_response.json()["preset_snapshot_name"] == "彩色单面"

    update_rule_response = authenticated_client.put(
        f"/api/v1/batch-printing/rules/{created_rule.id}",
        data=json.dumps(
            {
                "preset_snapshot_id": preset_a.id,
                "enabled": False,
                "notes": "切回黑白",
            }
        ),
        content_type="application/json",
    )
    assert update_rule_response.status_code == 200
    updated_rule_payload = update_rule_response.json()
    assert updated_rule_payload["printer_name"] == preset_a.printer_name
    assert updated_rule_payload["enabled"] is False
    assert updated_rule_payload["notes"] == "切回黑白"

    created_rule.refresh_from_db()
    assert created_rule.preset_snapshot_id == preset_a.id
    assert created_rule.printer_name == preset_a.printer_name

    delete_rule_response = authenticated_client.delete(f"/api/v1/batch-printing/rules/{existing_rule.id}")
    assert delete_rule_response.status_code == 200
    assert delete_rule_response.json() == {"success": True}
    assert not PrintKeywordRule.objects.filter(id=existing_rule.id).exists()


@pytest.mark.django_db
def test_batch_printing_job_endpoints_expose_full_contract(authenticated_client, monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = uuid4()
    now = timezone.now()
    captured: dict[str, object] = {}

    class _StubJobService:
        def list_jobs(self, *, status: str = "", keyword: str = "") -> list[object]:
            captured["list"] = {"status": status, "keyword": keyword}
            return [object()]

        def create_job(self, *, files, created_by=None):
            captured["create_files"] = [file.name for file in files]
            captured["created_by_authenticated"] = bool(getattr(created_by, "is_authenticated", False))
            return SimpleNamespace(id=job_id, status="pending")

        def get_job(self, job_id_value):
            captured["detail_job_id"] = str(job_id_value)
            return object()

        def request_cancel(self, *, job_id):
            captured["cancel_job_id"] = str(job_id)
            return SimpleNamespace(id=job_id, status="cancelled")

        def delete_job(self, *, job_id):
            captured["delete_job_id"] = str(job_id)

        def build_job_summary_payload(self, *, job) -> dict[str, object]:
            return {
                "job_id": str(job_id),
                "status": "processing",
                "total_count": 1,
                "processed_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "progress": 20,
                "cancel_requested": False,
                "task_id": "q-task-001",
                "created_by_id": 1,
                "created_by_name": "testuser",
                "capability_payload": {"docx_supported": True, "docx_converter": "soffice"},
                "summary_payload": {"queued": 1},
                "error_message": "",
                "created_at": now,
                "started_at": now,
                "finished_at": None,
            }

        def build_job_payload(self, *, job) -> dict[str, object]:
            payload = self.build_job_summary_payload(job=job)
            payload["items"] = [
                {
                    "id": 1,
                    "order": 1,
                    "filename": "归档材料.pdf",
                    "source_relpath": "batch_printing/jobs/1/source/001_归档材料.pdf",
                    "prepared_relpath": "",
                    "file_type": "pdf",
                    "status": "pending",
                    "matched_rule_id": 10,
                    "matched_keyword": "归档",
                    "target_preset_id": 3,
                    "target_printer_name": "canonprinter",
                    "target_preset_name": "黑白双面",
                    "cups_job_id": "",
                    "error_message": "",
                    "started_at": None,
                    "finished_at": None,
                }
            ]
            return payload

    monkeypatch.setattr(
        "apps.batch_printing.api.batch_printing_api.get_batch_print_job_service",
        lambda: _StubJobService(),
    )

    list_jobs_response = authenticated_client.get(
        "/api/v1/batch-printing/jobs",
        {"status": "processing", "keyword": "归档"},
    )
    assert list_jobs_response.status_code == 200
    listed_jobs = list_jobs_response.json()
    assert len(listed_jobs) == 1
    assert listed_jobs[0]["job_id"] == str(job_id)
    assert captured["list"] == {"status": "processing", "keyword": "归档"}

    upload = SimpleUploadedFile("归档材料.pdf", b"%PDF-1.4\n", content_type="application/pdf")
    create_job_response = authenticated_client.post(
        "/api/v1/batch-printing/jobs",
        data={"files": upload},
    )
    assert create_job_response.status_code == 200
    assert create_job_response.json() == {"job_id": str(job_id), "status": "pending"}
    assert captured["create_files"] == ["归档材料.pdf"]
    assert captured["created_by_authenticated"] is True

    job_detail_response = authenticated_client.get(f"/api/v1/batch-printing/jobs/{job_id}")
    assert job_detail_response.status_code == 200
    detail_payload = job_detail_response.json()
    assert detail_payload["job_id"] == str(job_id)
    assert detail_payload["items"][0]["target_preset_name"] == "黑白双面"
    assert captured["detail_job_id"] == str(job_id)

    cancel_job_response = authenticated_client.post(f"/api/v1/batch-printing/jobs/{job_id}/cancel")
    assert cancel_job_response.status_code == 200
    assert cancel_job_response.json() == {"job_id": str(job_id), "status": "cancelled"}
    assert captured["cancel_job_id"] == str(job_id)

    delete_job_response = authenticated_client.delete(f"/api/v1/batch-printing/jobs/{job_id}")
    assert delete_job_response.status_code == 200
    assert delete_job_response.json() == {"success": True}
    assert captured["delete_job_id"] == str(job_id)
