"""Unit tests for BusinessFileStorageService."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ValidationException
from apps.core.services.business_file_storage_service import BusinessFileStorageService


@pytest.fixture
def service() -> BusinessFileStorageService:
    return BusinessFileStorageService()


def test_choose_storage_target_prefers_contract_folder(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract_root = tmp_path / "contract_root"
    contract_root.mkdir()

    monkeypatch.setattr(
        service,
        "_get_contract_folder_root",
        lambda *, contract_id, require_writable: contract_root,
    )

    target = service.choose_storage_target(
        purpose="finalized_material",
        contract_id=9,
        target_subdir="归档材料/补充协议",
    )

    assert target.root_type == "contract_folder"
    assert target.subdir_path == "归档材料/补充协议"
    assert target.relative_dir == "归档材料/补充协议"
    assert target.absolute_dir == (contract_root / "归档材料" / "补充协议").resolve()
    assert target.is_fallback is False


def test_choose_storage_target_prefers_case_folder(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case_root"
    case_root.mkdir()

    monkeypatch.setattr(
        service,
        "_get_case_folder_root",
        lambda *, case_id, require_writable: case_root,
    )

    target = service.choose_storage_target(
        purpose="log_attachment",
        case_id=18,
        target_subdir="证据材料\\原件",
    )

    assert target.root_type == "case_folder"
    assert target.subdir_path == "证据材料/原件"
    assert target.absolute_dir == (case_root / "证据材料" / "原件").resolve()
    assert target.is_fallback is False


def test_choose_storage_target_falls_back_to_media(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()

    monkeypatch.setattr(
        service,
        "_get_contract_folder_root",
        lambda *, contract_id, require_writable: None,
    )
    monkeypatch.setattr(service, "_get_media_root_path", lambda: media_root)

    target = service.choose_storage_target(
        purpose="finalized_material",
        contract_id=23,
        target_subdir="合同附件/补充协议",
    )

    assert target.root_type == "media"
    assert target.relative_dir == "contracts/finalized/23/合同附件/补充协议"
    assert target.absolute_dir == (media_root / "contracts" / "finalized" / "23" / "合同附件" / "补充协议").resolve()
    assert target.is_fallback is True


def test_choose_storage_target_rejects_invalid_subdir(service: BusinessFileStorageService) -> None:
    with pytest.raises(ValidationException):
        service.choose_storage_target(
            purpose="log_attachment",
            case_id=1,
            target_subdir="../secret",
        )


def test_resolve_file_supports_legacy_media_record(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    file_path = media_root / "case_logs" / "a.pdf"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"hello")

    monkeypatch.setattr(service, "_get_media_root_path", lambda: media_root)

    record = SimpleNamespace(file=SimpleNamespace(name="case_logs/a.pdf"))
    resolved = service.resolve_file(record)

    assert resolved.root_type == "media"
    assert resolved.exists is True
    assert resolved.relative_file_path == "case_logs/a.pdf"
    assert Path(resolved.abs_path) == file_path.resolve()


def test_resolve_file_supports_case_folder_record(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "case_root"
    case_root.mkdir()
    file_path = case_root / "证据材料" / "原件" / "证据1.pdf"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"hello")

    monkeypatch.setattr(
        service,
        "_get_case_folder_root",
        lambda *, case_id, require_writable: case_root,
    )

    record = SimpleNamespace(
        storage_root_type="case_folder",
        relative_file_path="证据材料/原件/证据1.pdf",
        log=SimpleNamespace(case_id=7),
    )
    resolved = service.resolve_file(record)

    assert resolved.root_type == "case_folder"
    assert resolved.exists is True
    assert resolved.relative_file_path == "证据材料/原件/证据1.pdf"
    assert Path(resolved.abs_path) == file_path.resolve()


def test_save_uploaded_file_prefers_contract_folder(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract_root = tmp_path / "contract_root"
    contract_root.mkdir()

    monkeypatch.setattr(
        service,
        "_get_contract_folder_root",
        lambda *, contract_id, require_writable: contract_root,
    )

    uploaded = SimpleUploadedFile("archive.pdf", b"pdf-bytes", content_type="application/pdf")
    saved = service.save_uploaded_file(
        uploaded_file=uploaded,
        purpose="finalized_material",
        contract_id=5,
        target_subdir="归档/扫描件",
        allowed_extensions=[".pdf"],
    )

    assert saved.root_type == "contract_folder"
    assert saved.subdir_path == "归档/扫描件"
    assert saved.relative_file_path.startswith("归档/扫描件/")
    assert Path(saved.absolute_file_path).exists()
    assert not Path(saved.legacy_file_path).is_absolute()


def test_delete_file_supports_business_record(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract_root = tmp_path / "contract_root"
    contract_root.mkdir()
    file_path = contract_root / "归档" / "a.pdf"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"hello")

    monkeypatch.setattr(
        service,
        "_get_contract_folder_root",
        lambda *, contract_id, require_writable: contract_root,
    )

    record = SimpleNamespace(
        contract_id=9,
        storage_root_type="contract_folder",
        relative_file_path="归档/a.pdf",
    )

    assert service.delete_file(record) is True
    assert file_path.exists() is False


def test_move_existing_file_moves_under_new_subdir(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract_root = tmp_path / "contract_root"
    contract_root.mkdir()
    old_file = contract_root / "旧目录" / "材料.pdf"
    old_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"hello")

    monkeypatch.setattr(
        service,
        "_get_contract_folder_root",
        lambda *, contract_id, require_writable: contract_root,
    )

    record = SimpleNamespace(
        contract_id=9,
        storage_root_type="contract_folder",
        subdir_path="旧目录",
        relative_file_path="旧目录/材料.pdf",
        original_filename="材料.pdf",
    )

    moved = service.move_existing_file(
        record,
        purpose="finalized_material",
        contract_id=9,
        target_subdir="新目录/二级目录",
    )

    assert moved.root_type == "contract_folder"
    assert moved.subdir_path == "新目录/二级目录"
    assert moved.relative_file_path == "新目录/二级目录/材料.pdf"
    assert old_file.exists() is False
    assert (contract_root / "新目录" / "二级目录" / "材料.pdf").exists() is True


def test_get_contract_folder_root_prefers_generated_business_root(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    business_root = tmp_path / "contract_root" / "2026.05.10-[民商事]合同1"
    business_root.mkdir(parents=True)

    class StubFolderBindingService:
        def get_contract_storage_root(self, owner_id: int) -> Path:
            assert owner_id == 1
            return business_root

    import apps.contracts.services.folder.folder_binding_service as folder_binding_module

    monkeypatch.setattr(folder_binding_module, "FolderBindingService", StubFolderBindingService)

    resolved = service._get_contract_folder_root(contract_id=1, require_writable=True)

    assert resolved == business_root.resolve()


def test_get_case_folder_root_prefers_generated_business_root(
    service: BusinessFileStorageService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    business_root = tmp_path / "case_root" / "2026.05.10-[姘戝晢浜媇妗堜欢1"
    business_root.mkdir(parents=True)

    class StubCaseFolderBindingService:
        def get_case_storage_root(self, owner_id: int) -> Path:
            assert owner_id == 1
            return business_root

    import apps.cases.services.template.folder_binding_service as folder_binding_module

    monkeypatch.setattr(folder_binding_module, "CaseFolderBindingService", StubCaseFolderBindingService)

    resolved = service._get_case_folder_root(case_id=1, require_writable=True)

    assert resolved == business_root.resolve()
