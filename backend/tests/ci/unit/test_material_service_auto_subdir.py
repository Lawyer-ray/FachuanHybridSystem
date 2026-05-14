from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from apps.contracts.admin.contract_inlines import FinalizedMaterialAdminForm
from apps.contracts.models import MaterialCategory
from apps.contracts.services.contract.integrations.material_service import MaterialService


def test_save_material_file_uses_recommended_subdir_when_target_subdir_empty() -> None:
    business_storage = Mock()
    business_storage.save_uploaded_file.return_value = SimpleNamespace(
        legacy_file_path="合同附件/测试.pdf",
        root_type="contract_folder",
        subdir_path="归档清单/收费凭证",
        relative_file_path="归档清单/收费凭证/测试.pdf",
        original_filename="测试.pdf",
    )
    service = MaterialService(business_storage_service=business_storage)

    with patch.object(service, "_resolve_target_subdir", return_value="合同附件/票据材料"):
        uploaded_file = SimpleNamespace(name="测试.pdf")
        service.save_material_file(
            uploaded_file,
            contract_id=124,
            target_subdir="",
            category=MaterialCategory.INVOICE,
        )

    business_storage.save_uploaded_file.assert_called_once()
    kwargs = business_storage.save_uploaded_file.call_args.kwargs
    assert kwargs["target_subdir"] == "合同附件/票据材料"


def test_save_material_file_passes_file_name_into_resolver() -> None:
    business_storage = Mock()
    business_storage.save_uploaded_file.return_value = SimpleNamespace(
        legacy_file_path="合同附件/测试.pdf",
        root_type="contract_folder",
        subdir_path="1-律师资料/3-发票",
        relative_file_path="1-律师资料/3-发票/测试.pdf",
        original_filename="增值税发票.pdf",
    )
    service = MaterialService(business_storage_service=business_storage)

    with patch.object(service, "_resolve_target_subdir", return_value="1-律师资料/3-发票") as resolver_mock:
        uploaded_file = SimpleNamespace(name="增值税发票.pdf")
        service.save_material_file(
            uploaded_file,
            contract_id=124,
            target_subdir="",
            category=MaterialCategory.INVOICE,
        )

    kwargs = resolver_mock.call_args.kwargs
    assert kwargs["file_name"] == "增值税发票.pdf"


def test_move_material_file_uses_recommended_subdir_when_target_subdir_empty() -> None:
    business_storage = Mock()
    business_storage.move_existing_file.return_value = SimpleNamespace(
        legacy_file_path="合同附件/测试.pdf",
        root_type="contract_folder",
        subdir_path="归档清单/委托合同",
        relative_file_path="归档清单/委托合同/测试.pdf",
        original_filename="测试.pdf",
    )
    service = MaterialService(business_storage_service=business_storage)

    material = SimpleNamespace(category=MaterialCategory.CONTRACT_ORIGINAL, original_filename="测试.pdf")
    with patch.object(service, "_resolve_target_subdir", return_value="合同附件/合同正本"):
        service.move_material_file(
            material,
            contract_id=124,
            target_subdir="",
            category=MaterialCategory.CONTRACT_ORIGINAL,
        )

    business_storage.move_existing_file.assert_called_once()
    kwargs = business_storage.move_existing_file.call_args.kwargs
    assert kwargs["target_subdir"] == "合同附件/合同正本"


def test_move_material_file_passes_original_filename_into_resolver() -> None:
    business_storage = Mock()
    business_storage.move_existing_file.return_value = SimpleNamespace(
        legacy_file_path="合同附件/测试.pdf",
        root_type="contract_folder",
        subdir_path="一审/1-立案材料/8-保全申请书及保函",
        relative_file_path="一审/1-立案材料/8-保全申请书及保函/测试.pdf",
        original_filename="财产保全申请书吴杰案.pdf",
    )
    service = MaterialService(business_storage_service=business_storage)

    material = SimpleNamespace(
        category=MaterialCategory.CASE_MATERIAL,
        original_filename="财产保全申请书吴杰案.pdf",
    )
    with patch.object(
        service,
        "_resolve_target_subdir",
        return_value="一审/1-立案材料/8-保全申请书及保函",
    ) as resolver_mock:
        service.move_material_file(
            material,
            contract_id=124,
            target_subdir="",
            category=MaterialCategory.CASE_MATERIAL,
        )

    kwargs = resolver_mock.call_args.kwargs
    assert kwargs["file_name"] == "财产保全申请书吴杰案.pdf"


def test_empty_existing_material_row_does_not_trigger_move(monkeypatch) -> None:
    instance = SimpleNamespace(
        pk=20,
        contract_id=124,
        category=MaterialCategory.ARCHIVE_DOCUMENT,
        file_path="",
        relative_file_path="",
        subdir_path="",
        original_filename="",
        storage_root_type="media",
        save=Mock(),
    )
    form = FinalizedMaterialAdminForm.__new__(FinalizedMaterialAdminForm)
    form.instance = instance
    form.cleaned_data = {
        "file": None,
        "target_subdir": "归档文书",
        "category": MaterialCategory.ARCHIVE_DOCUMENT,
    }

    move_mock = Mock()
    monkeypatch.setattr(
        "apps.contracts.admin.wiring_admin.get_material_service",
        lambda: SimpleNamespace(move_material_file=move_mock),
    )
    monkeypatch.setattr(
        "django.forms.ModelForm.save",
        lambda self, commit=False: instance,
    )

    result = FinalizedMaterialAdminForm.save(form, commit=False)

    assert result is instance
    move_mock.assert_not_called()


def test_empty_new_material_row_with_only_helper_values_is_not_changed(monkeypatch) -> None:
    instance = SimpleNamespace(
        pk=None,
        contract_id=124,
        category=MaterialCategory.ARCHIVE_DOCUMENT,
        file_path="",
        relative_file_path="",
        subdir_path="",
        original_filename="",
        storage_root_type="media",
    )
    form = FinalizedMaterialAdminForm.__new__(FinalizedMaterialAdminForm)
    form.instance = instance
    form.cleaned_data = {
        "file": None,
        "target_subdir": "归档文书",
        "category": MaterialCategory.ARCHIVE_DOCUMENT,
    }
    form.files = {}
    form.add_prefix = lambda name: name  # type: ignore[method-assign]

    monkeypatch.setattr(
        "django.forms.ModelForm.has_changed",
        lambda self: True,
    )

    assert FinalizedMaterialAdminForm.has_changed(form) is False


def test_existing_material_row_with_only_helper_values_is_still_changed(monkeypatch) -> None:
    instance = SimpleNamespace(
        pk=23,
        contract_id=124,
        category=MaterialCategory.ARCHIVE_DOCUMENT,
        file_path="D:/contracts/archive/sample.pdf",
        relative_file_path="归档文书/sample.pdf",
        subdir_path="归档文书",
        original_filename="sample.pdf",
        storage_root_type="contract_folder",
    )
    form = FinalizedMaterialAdminForm.__new__(FinalizedMaterialAdminForm)
    form.instance = instance
    form.cleaned_data = {
        "file": None,
        "target_subdir": "归档文书/补充",
        "category": MaterialCategory.ARCHIVE_DOCUMENT,
    }
    form.files = {}
    form.add_prefix = lambda name: name  # type: ignore[method-assign]

    monkeypatch.setattr(
        "django.forms.ModelForm.has_changed",
        lambda self: True,
    )

    assert FinalizedMaterialAdminForm.has_changed(form) is True
