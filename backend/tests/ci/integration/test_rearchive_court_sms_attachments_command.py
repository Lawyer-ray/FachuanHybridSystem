from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test.utils import override_settings
from django.utils import timezone

from apps.automation.models import CourtSMS
from apps.cases.models import Case, CaseLog, CaseLogAttachment
from apps.organization.models import LawFirm, Lawyer


def _build_binding_monkeypatch(monkeypatch: pytest.MonkeyPatch, *, business_root: Path) -> None:
    class Binding:
        folder_path = str(business_root.parent)
        resolved_folder_path = str(business_root.parent)

    monkeypatch.setattr(
        "apps.cases.services.template.folder_binding_service.CaseFolderBindingService._require_case_access",
        lambda self, **kwargs: Case(current_stage="first_trial", case_type="civil"),
    )
    monkeypatch.setattr(
        "apps.cases.services.template.folder_binding_service.CaseFolderBindingService._get_binding_record",
        lambda self, case_id: Binding(),
    )
    monkeypatch.setattr(
        "apps.cases.services.template.folder_binding_service.CaseFolderBindingService.check_and_repair_path",
        lambda self, binding: (True, False),
    )
    monkeypatch.setattr(
        "apps.cases.services.template.folder_binding_service.CaseFolderBindingService._resolve_business_root_from_binding",
        lambda self, owner_id, root: business_root,
    )
    monkeypatch.setattr(
        "apps.core.services.business_file_storage_service.BusinessFileStorageService._get_case_folder_root",
        lambda self, *, case_id, require_writable: business_root,
    )


def _build_sms_fixture() -> tuple[LawFirm, Lawyer, Case, CaseLog, CourtSMS]:
    firm = LawFirm.objects.create(name="测试律所")
    actor = Lawyer.objects.create_user(
        username="rearchive-court-sms",
        password="placeholder-password",
        law_firm=firm,
        is_admin=True,
    )
    case = Case.objects.create(name="测试案件", case_type="civil", current_stage="first_trial")
    log = CaseLog.objects.create(case=case, actor=actor, content="法院短信日志")
    sms = CourtSMS.objects.create(
        content="法院送达短信",
        received_at=timezone.now(),
        status="matching",
        case=case,
        case_log=log,
    )
    return firm, actor, case, log, sms


@pytest.mark.django_db
def test_rearchive_court_sms_attachments_command_dry_run_does_not_move_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, _, case, log, sms = _build_sms_fixture()

    media_root = tmp_path / "media"
    source_dir = media_root / "case_logs"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "案件受理通知书.pdf"
    source_file.write_bytes(b"pdf-bytes")

    business_root = tmp_path / "case-root" / "测试案件业务目录"
    (business_root / "一审" / "法院送达材料" / "受理通知书").mkdir(parents=True)
    _build_binding_monkeypatch(monkeypatch, business_root=business_root)

    attachment = CaseLogAttachment.objects.create(
        log=log,
        file="case_logs/案件受理通知书.pdf",
        storage_root_type="media",
        subdir_path="case_logs",
        relative_file_path="case_logs/案件受理通知书.pdf",
        original_filename="案件受理通知书.pdf",
    )

    stdout = StringIO()
    with override_settings(MEDIA_ROOT=str(media_root)):
        call_command("rearchive_court_sms_attachments", sms_id=sms.id, dry_run=True, stdout=stdout)

    attachment.refresh_from_db()
    assert attachment.storage_root_type == "media"
    assert attachment.relative_file_path == "case_logs/案件受理通知书.pdf"
    assert source_file.exists()
    assert not (business_root / "一审" / "法院送达材料" / "受理通知书" / "案件受理通知书.pdf").exists()
    assert "[PLAN]" in stdout.getvalue()
    assert "计划迁移 1 个" in stdout.getvalue()
    assert case.id == sms.case_id


@pytest.mark.django_db
def test_rearchive_court_sms_attachments_command_moves_media_attachment_into_case_folder_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, _, _, log, sms = _build_sms_fixture()

    media_root = tmp_path / "media"
    source_dir = media_root / "case_logs"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "判决书.pdf"
    source_file.write_bytes(b"pdf-bytes")

    business_root = tmp_path / "case-root" / "测试案件业务目录"
    target_dir = business_root / "一审" / "法院送达材料" / "裁定书、判决书、通知书"
    target_dir.mkdir(parents=True)
    _build_binding_monkeypatch(monkeypatch, business_root=business_root)

    attachment = CaseLogAttachment.objects.create(
        log=log,
        file="case_logs/判决书.pdf",
        storage_root_type="media",
        subdir_path="case_logs",
        relative_file_path="case_logs/判决书.pdf",
        original_filename="判决书.pdf",
    )

    stdout = StringIO()
    with override_settings(MEDIA_ROOT=str(media_root)):
        call_command("rearchive_court_sms_attachments", sms_id=sms.id, stdout=stdout)

    attachment.refresh_from_db()
    expected_relative = "一审/法院送达材料/裁定书、判决书、通知书/判决书.pdf"
    assert attachment.storage_root_type == "case_folder"
    assert attachment.subdir_path == "一审/法院送达材料/裁定书、判决书、通知书"
    assert attachment.relative_file_path == expected_relative
    assert not source_file.exists()
    assert (target_dir / "判决书.pdf").exists()
    assert "[MOVED]" in stdout.getvalue()
    assert "成功迁移 1 个" in stdout.getvalue()

    stdout_second = StringIO()
    with override_settings(MEDIA_ROOT=str(media_root)):
        call_command("rearchive_court_sms_attachments", sms_id=sms.id, stdout=stdout_second)

    attachment.refresh_from_db()
    assert attachment.storage_root_type == "case_folder"
    assert attachment.relative_file_path == expected_relative
    assert "附件已在案件目录" in stdout_second.getvalue()
    assert "成功迁移 0 个" in stdout_second.getvalue()
