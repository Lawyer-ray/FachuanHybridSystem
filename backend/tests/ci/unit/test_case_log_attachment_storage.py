from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from apps.cases.admin.caselog_admin import CaseLogAttachmentInlineForm
from apps.cases.models import Case
from apps.cases.services.log.case_log_attachment_storage_service import CaseLogAttachmentStorageService
from apps.cases.services.template.folder_binding_service import CaseFolderBindingService


def test_recommend_bound_subdir_for_log_attachment_prefers_existing_mail_folder(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "4-邮件往来").mkdir(parents=True)
    (root / "案件日志附件").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(owner_id=1)

    assert result["recommended_subdir"] == "4-邮件往来"
    assert result["matched_existing_subdir"] == "4-邮件往来"
    assert result["reason"] == "preferred_log_attachment_subdir"


def test_recommend_bound_subdir_for_log_attachment_prefers_file_name_rule(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "1-起诉材料").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "4-证据目录").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="起诉书签字版.pdf",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/1-起诉材料"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/1-起诉材料"
    assert result["reason"] == "file_name_rule_match"


def test_recommend_bound_subdir_for_log_attachment_prefers_preservation_folder(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "1-起诉状和反诉答辩状").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "8-保全申请书及保函").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="财产保全申请书吴杰案.pdf",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/8-保全申请书及保函"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/8-保全申请书及保函"
    assert result["reason"] in {"file_name_rule_match", "file_name_keyword_match"}


def test_save_attachment_passes_file_name_into_recommendation() -> None:
    business_storage = Mock()
    business_storage.save_uploaded_file.return_value = SimpleNamespace(
        legacy_file_path="D:/cases/test.pdf",
        root_type="case_folder",
        subdir_path="一审/1-立案材料/1-起诉材料",
        relative_file_path="一审/1-立案材料/1-起诉材料/test.pdf",
        original_filename="起诉书签字版.pdf",
    )
    service = CaseLogAttachmentStorageService(business_storage_service=business_storage)

    recommend_mock = Mock(return_value={"recommended_subdir": "一审/1-立案材料/1-起诉材料"})
    with patch.object(service, "recommend_attachment_subdir", recommend_mock):
        uploaded_file = SimpleNamespace(name="起诉书签字版.pdf")
        service.save_attachment(
            uploaded_file,
            case_id=10,
            target_subdir="",
        )

    kwargs = recommend_mock.call_args.kwargs
    assert kwargs["file_name"] == "起诉书签字版.pdf"


def test_recommend_bound_subdir_for_log_attachment_uses_source_subfolder(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "4-证据目录").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        source_subfolder="一审/1-立案材料/4-证据目录",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/4-证据目录"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/4-证据目录"
    assert result["reason"] == "source_subfolder_match"


def test_save_attachment_uses_recommended_subdir_when_target_subdir_empty() -> None:
    business_storage = Mock()
    business_storage.save_uploaded_file.return_value = SimpleNamespace(
        legacy_file_path="D:/cases/test.pdf",
        root_type="case_folder",
        subdir_path="4-邮件往来",
        relative_file_path="4-邮件往来/test.pdf",
        original_filename="test.pdf",
    )
    service = CaseLogAttachmentStorageService(business_storage_service=business_storage)

    with patch.object(service, "recommend_attachment_subdir", return_value={"recommended_subdir": "4-邮件往来"}):
        uploaded_file = SimpleNamespace(name="test.pdf")
        service.save_attachment(
            uploaded_file,
            case_id=10,
            target_subdir="",
        )

    kwargs = business_storage.save_uploaded_file.call_args.kwargs
    assert kwargs["target_subdir"] == "4-邮件往来"


def test_empty_new_log_attachment_row_with_only_helper_values_is_not_changed(monkeypatch) -> None:
    instance = SimpleNamespace(
        pk=None,
        log=SimpleNamespace(case_id=124),
        file="",
        relative_file_path="",
        subdir_path="",
        original_filename="",
        storage_root_type="media",
    )
    form = CaseLogAttachmentInlineForm.__new__(CaseLogAttachmentInlineForm)
    form.instance = instance
    form.cleaned_data = {
        "file": None,
        "target_subdir": "案件日志附件",
    }
    form.files = {}
    form.add_prefix = lambda name: name  # type: ignore[method-assign]

    monkeypatch.setattr(
        "django.forms.ModelForm.has_changed",
        lambda self: True,
    )

    assert CaseLogAttachmentInlineForm.has_changed(form) is False


def test_empty_existing_log_attachment_row_does_not_trigger_move(monkeypatch) -> None:
    instance = SimpleNamespace(
        pk=20,
        log=SimpleNamespace(case_id=124),
        file="",
        relative_file_path="",
        subdir_path="",
        original_filename="",
        storage_root_type="media",
        save=Mock(),
    )
    form = CaseLogAttachmentInlineForm.__new__(CaseLogAttachmentInlineForm)
    form.instance = instance
    form.cleaned_data = {
        "file": None,
        "target_subdir": "案件日志附件",
    }

    move_mock = Mock()
    monkeypatch.setattr(
        "apps.cases.services.log.case_log_attachment_storage_service.CaseLogAttachmentStorageService.move_attachment",
        move_mock,
    )
    monkeypatch.setattr(
        "django.forms.ModelForm.save",
        lambda self, commit=False: instance,
    )

    result = CaseLogAttachmentInlineForm.save(form, commit=False)

    assert result is instance
    move_mock.assert_not_called()


def test_list_bound_subdirs_falls_back_to_existing_parent(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.list_bound_subdirs(
        owner_id=1,
        relative_path="一审/1-立案材料/4-证据目录",
    )

    assert result["root_path"] == root.resolve().as_posix()
    assert result["current_path"] == "一审/1-立案材料"
    assert result["parent_path"] == "一审"
    assert result["entries"] == []


def test_list_bound_subdirs_falls_back_to_root_when_target_missing(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.list_bound_subdirs(owner_id=1, relative_path="不存在/更深层")

    assert result["root_path"] == root.resolve().as_posix()
    assert result["current_path"] == ""
    assert result["parent_path"] is None
    assert result["entries"] == [{"name": "一审", "relative_path": "一审"}]


def test_list_bound_subdirs_uses_generated_case_business_root(db, tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    case = Case.objects.create(name="案件1", case_type="civil")
    root = tmp_path / "case_root"
    business_root = root / "2026.05.10-[民商事]案件1"
    (business_root / "一审" / "1-立案材料").mkdir(parents=True)
    (business_root / "案件日志附件").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.list_bound_subdirs(owner_id=case.id)

    assert Path(result["root_path"]).resolve() == business_root.resolve()
    assert result["current_path"] == ""
    assert {entry["name"] for entry in result["entries"]} == {"一审", "案件日志附件"}


def test_recommend_bound_subdir_for_log_attachment_uses_generated_case_business_root(db, tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    case = Case.objects.create(name="案件1", case_type="civil")
    root = tmp_path / "case_root"
    business_root = root / "2026.05.10-[民商事]案件1"
    (business_root / "一审" / "1-立案材料" / "4-证据目录").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(owner_id=case.id)

    assert result["recommended_subdir"] == "一审/1-立案材料/4-证据目录"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/4-证据目录"
    assert result["reason"] == "preferred_log_attachment_subdir"


def test_recommend_bound_subdir_for_log_attachment_distinguishes_directory_vs_material(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "4-证据目录").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "5-证据材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    directory_result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="证据目录.pdf",
    )
    material_result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="微信聊天记录.pdf",
    )

    assert directory_result["recommended_subdir"] == "一审/1-立案材料/4-证据目录"
    assert material_result["recommended_subdir"] == "一审/1-立案材料/5-证据材料"


def test_recommend_bound_subdir_for_log_attachment_prefers_deeper_existing_child(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "5-证据材料" / "聊天记录").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "5-证据材料" / "转账记录").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="微信聊天记录.pdf",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/5-证据材料/聊天记录"


def test_manual_log_recommendation_prefers_non_court_subdir_before_court_delivery_folder(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "5-证据材料").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "4-证据目录").mkdir(parents=True)
    (root / "一审" / "法院送达材料" / "对方当事人提交材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="提交证据.pdf",
        source_scene="manual_log_upload",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/5-证据材料"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/5-证据材料"
    assert result["reason"] in {
        "file_name_evidence_material_preferred",
        "file_name_evidence_material_match",
        "file_name_evidence_material_fallback",
    }


def test_manual_log_recommendation_still_prefers_normal_fallback_over_court_delivery_folder(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "法院送达材料" / "对方当事人提交材料").mkdir(parents=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="对方质证意见.pdf",
        source_scene="manual_log_upload",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/5-证据材料"
    assert result["matched_existing_subdir"] == ""
    assert result["reason"] == "file_name_rule_fallback"


def test_manual_log_recommendation_prefers_evidence_directory_for_generic_stage_evidence_name(tmp_path: Path) -> None:
    service = CaseFolderBindingService()
    root = tmp_path / "case_root"
    (root / "一审" / "1-立案材料" / "5-证据材料").mkdir(parents=True)
    (root / "一审" / "1-立案材料" / "4-证据目录").mkdir(parents=True)
    (root / "一审").mkdir(exist_ok=True)

    class Binding:
        folder_path = str(root)
        resolved_folder_path = str(root)

    service._get_binding_record = lambda case_id: Binding()  # type: ignore[method-assign]
    service.check_and_repair_path = lambda binding: (True, False)  # type: ignore[method-assign]
    service._require_case_access = lambda **kwargs: None  # type: ignore[method-assign]

    result = service.recommend_bound_subdir_for_log_attachment(
        owner_id=1,
        file_name="一审证据.pdf",
        source_scene="manual_log_upload",
    )

    assert result["recommended_subdir"] == "一审/1-立案材料/5-证据材料"
    assert result["matched_existing_subdir"] == "一审/1-立案材料/5-证据材料"
    assert result["reason"] in {
        "file_name_evidence_material_preferred",
        "file_name_evidence_material_match",
    }
