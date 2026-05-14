from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cases.models import Case, CaseLog
from apps.cases.services.case.case_log_internal_service import CaseLogInternalService
from apps.organization.models import LawFirm, Lawyer


@pytest.mark.django_db
def test_add_case_log_attachment_internal_imports_local_file_with_recommended_subdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    firm = LawFirm.objects.create(name="测试律所")
    actor = Lawyer.objects.create_user(username="case-log-import", password="testpass123", law_firm=firm, is_admin=True)
    case = Case.objects.create(name="测试案件", case_type="civil")
    log = CaseLog.objects.create(case=case, actor=actor, content="法院短信日志")

    source_file = tmp_path / "起诉状.pdf"
    source_file.write_bytes(b"pdf-bytes")

    business_root = tmp_path / "case-root" / "2026.05.14-[民商事]-测试案件"
    (business_root / "一审" / "1-立案材料" / "1-起诉材料").mkdir(parents=True)

    class Binding:
        folder_path = str(business_root.parent)
        resolved_folder_path = str(business_root.parent)

    monkeypatch.setattr(
        "apps.cases.services.template.folder_binding_service.CaseFolderBindingService._require_case_access",
        lambda self, **kwargs: None,
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
    monkeypatch.setattr(
        "apps.cases.services.case.case_log_internal_service.SimpleUploadedFile",
        lambda name, content: SimpleUploadedFile("起诉状.pdf", content, content_type="application/pdf"),
    )

    success = CaseLogInternalService().add_case_log_attachment_internal(
        case_log_id=log.id,
        file_path=str(source_file),
        file_name="起诉状.pdf",
    )

    assert success is True

    attachment = log.attachments.get()
    assert attachment.storage_root_type == "case_folder"
    assert attachment.subdir_path == "一审/1-立案材料/1-起诉材料"
    assert attachment.relative_file_path == "一审/1-立案材料/1-起诉材料/起诉状.pdf"
    assert (business_root / "一审" / "1-立案材料" / "1-起诉材料" / "起诉状.pdf").exists()
