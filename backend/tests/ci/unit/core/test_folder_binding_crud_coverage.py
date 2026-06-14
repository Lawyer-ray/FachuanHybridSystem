"""Coverage tests for core.filesystem.folder_binding_crud_service."""
from __future__ import annotations

from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


class TestGetOwner:
    def test_owner_model_none_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.owner_model = None
        with pytest.raises(RuntimeError, match="owner_model"):
            svc._get_owner(owner_id=1)

    def test_owner_not_found(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = None
        svc = FolderBindingCrudService()
        svc.owner_model = mock_model
        svc.owner_label = "合同"

        with pytest.raises(NotFoundError) as exc_info:
            svc._get_owner(owner_id=999)
        assert "合同不存在" in str(exc_info.value)

    def test_owner_found(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        mock_owner = MagicMock()
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = mock_owner
        svc = FolderBindingCrudService()
        svc.owner_model = mock_model

        result = svc._get_owner(owner_id=1)
        assert result is mock_owner


class TestGetOwnerType:
    def test_returns_case_type(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock()
        owner.case_type = "民事"
        assert svc._get_owner_type(owner) == "民事"

    def test_returns_empty_when_no_attr(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock(spec=[])  # no case_type
        assert svc._get_owner_type(owner) == ""


class TestResolveSubdirPath:
    def test_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        assert svc._resolve_subdir_path(owner_type="民事", subdir_key="test") is None


class TestComputeRelativePath:
    def test_no_contract_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock(spec=[])  # no contract attr
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_contract_none_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock()
        owner.contract = None
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_no_binding_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock()
        owner.contract = MagicMock()
        owner.contract.folder_binding = None
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_empty_folder_path_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock()
        owner.contract = MagicMock()
        owner.contract.folder_binding.folder_path = ""
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_relative_path_computed(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock()
        owner.contract = MagicMock()
        owner.contract.folder_binding.folder_path = "/data/contracts/ABC"
        result = svc._compute_relative_path(owner, "/data/contracts/ABC/cases/123")
        assert result == "cases/123"

    def test_not_relative_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = MagicMock()
        owner.contract = MagicMock()
        owner.contract.folder_binding.folder_path = "/data/contracts/ABC"
        result = svc._compute_relative_path(owner, "/other/path/123")
        assert result is None


class TestCreateBinding:
    def test_binding_model_none_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = None
        with pytest.raises(RuntimeError, match="binding_model"):
            svc.create_binding(owner_id=1, folder_path="/tmp")

    def test_owner_rel_field_empty_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_rel_field = ""
        with pytest.raises(RuntimeError, match="owner_rel_field"):
            svc.create_binding(owner_id=1, folder_path="/tmp")

    def test_local_path_invalid_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_rel_field = "owner"
        mock_owner = MagicMock()
        svc._require_owner = MagicMock(return_value=mock_owner)
        svc.validate_folder_path = MagicMock(return_value=(False, "invalid path"))

        with pytest.raises(ValidationException) as exc_info:
            svc.create_binding(owner_id=1, folder_path="invalid//path")
        assert "INVALID_PATH_FORMAT" in str(exc_info.value.code)

    def test_local_path_valid(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_rel_field = "owner"
        svc.owner_model = MagicMock()
        mock_owner = MagicMock()
        svc._require_owner = MagicMock(return_value=mock_owner)
        svc.validate_folder_path = MagicMock(return_value=(True, None))
        mock_inode_resolver = MagicMock()
        mock_inode_resolver.get_inode_info.return_value = (12345, 67890)
        svc._inode_resolver = mock_inode_resolver
        svc.binding_model.objects.update_or_create.return_value = (MagicMock(), True)
        svc._compute_relative_path = MagicMock(return_value=None)

        result = svc.create_binding(owner_id=1, folder_path="/data/test")
        assert result is not None

    def test_cloud_storage_path(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_rel_field = "owner"
        mock_owner = MagicMock()
        svc._require_owner = MagicMock(return_value=mock_owner)
        svc.validate_folder_path = MagicMock(return_value=(True, None))
        mock_inode_resolver = MagicMock()
        mock_inode_resolver.get_inode_info.return_value = None
        svc._inode_resolver = mock_inode_resolver
        svc.binding_model.objects.update_or_create.return_value = (MagicMock(), False)
        svc._compute_relative_path = MagicMock(return_value=None)

        result = svc.create_binding(
            owner_id=1, folder_path="/cloud/path",
            storage_type="webdav", storage_account="acc1"
        )
        call_kwargs = svc.binding_model.objects.update_or_create.call_args[1]["defaults"]
        assert call_kwargs["storage_type"] == "webdav"
        assert call_kwargs["storage_account"] == "acc1"

    def test_with_relative_path(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_rel_field = "owner"
        mock_owner = MagicMock()
        svc._require_owner = MagicMock(return_value=mock_owner)
        svc.validate_folder_path = MagicMock(return_value=(True, None))
        mock_inode_resolver = MagicMock()
        mock_inode_resolver.get_inode_info.return_value = None
        svc._inode_resolver = mock_inode_resolver
        svc.binding_model.objects.update_or_create.return_value = (MagicMock(), True)
        svc._compute_relative_path = MagicMock(return_value="cases/123")

        result = svc.create_binding(owner_id=1, folder_path="/data/contracts/cases/123")
        call_kwargs = svc.binding_model.objects.update_or_create.call_args[1]["defaults"]
        assert call_kwargs["relative_path"] == "cases/123"


class TestDeleteBinding:
    def test_binding_model_none_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = None
        with pytest.raises(RuntimeError):
            svc.delete_binding(owner_id=1)

    def test_owner_id_field_empty_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_id_field = ""
        with pytest.raises(RuntimeError):
            svc.delete_binding(owner_id=1)

    def test_delete_success(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_id_field = "owner_id"
        svc._require_owner = MagicMock()
        svc.binding_model.objects.filter.return_value.delete.return_value = (1, {})

        result = svc.delete_binding(owner_id=1)
        assert result is True

    def test_delete_no_match(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_id_field = "owner_id"
        svc._require_owner = MagicMock()
        svc.binding_model.objects.filter.return_value.delete.return_value = (0, {})

        result = svc.delete_binding(owner_id=1)
        assert result is False


class TestGetBinding:
    def test_binding_model_none_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = None
        with pytest.raises(RuntimeError):
            svc.get_binding(owner_id=1)

    def test_owner_id_field_empty_raises(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_id_field = ""
        with pytest.raises(RuntimeError):
            svc.get_binding(owner_id=1)

    def test_returns_binding(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        mock_binding = MagicMock()
        svc = FolderBindingCrudService()
        svc.binding_model = MagicMock()
        svc.owner_id_field = "owner_id"
        svc._require_owner = MagicMock()
        svc.binding_model.objects.filter.return_value.first.return_value = mock_binding

        result = svc.get_binding(owner_id=1)
        assert result is mock_binding


class TestSaveFileToBoundFolder:
    def test_no_binding_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.get_binding = MagicMock(return_value=None)
        result = svc.save_file_to_bound_folder(
            owner_id=1, file_content=b"data", file_name="test.pdf", subdir_key="k"
        )
        assert result is None

    def test_cloud_storage_success(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/cloud/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._get_owner = MagicMock()
        svc._get_owner_type = MagicMock(return_value="other")
        svc._resolve_subdir_path = MagicMock(return_value=None)
        svc.DEFAULT_SUBDIRS = {"k": "默认目录"}
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "test.pdf"
        svc._path_validator.sanitize_relative_dir.return_value = ["默认目录"]
        svc._is_cloud_storage = MagicMock(return_value=True)
        mock_provider = MagicMock()
        svc._get_provider_for_binding = MagicMock(return_value=mock_provider)

        result = svc.save_file_to_bound_folder(
            owner_id=1, file_content=b"data", file_name="test.pdf", subdir_key="k"
        )
        assert result is not None
        mock_provider.write_file.assert_called_once()

    def test_cloud_storage_error(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/cloud/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._get_owner = MagicMock()
        svc._get_owner_type = MagicMock(return_value="other")
        svc._resolve_subdir_path = MagicMock(return_value=None)
        svc.DEFAULT_SUBDIRS = {"k": "默认目录"}
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "test.pdf"
        svc._path_validator.sanitize_relative_dir.return_value = ["默认目录"]
        svc._is_cloud_storage = MagicMock(return_value=True)
        mock_provider = MagicMock()
        mock_provider.write_file.side_effect = Exception("upload failed")
        svc._get_provider_for_binding = MagicMock(return_value=mock_provider)

        with pytest.raises(ValidationException) as exc_info:
            svc.save_file_to_bound_folder(
                owner_id=1, file_content=b"data", file_name="test.pdf", subdir_key="k"
            )
        assert "FILE_SAVE_FAILED" in str(exc_info.value.code)

    def test_local_save_success(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/local/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._get_owner = MagicMock()
        svc._get_owner_type = MagicMock(return_value="other")
        svc._resolve_subdir_path = MagicMock(return_value="subdir")
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "file.txt"
        svc._path_validator.sanitize_relative_dir.return_value = ["subdir"]
        svc._is_cloud_storage = MagicMock(return_value=False)
        svc._filesystem_service = MagicMock()
        svc._filesystem_service.save_bytes.return_value = "/local/root/subdir/file.txt"

        result = svc.save_file_to_bound_folder(
            owner_id=1, file_content=b"data", file_name="file.txt", subdir_key="k"
        )
        assert result == "/local/root/subdir/file.txt"

    def test_local_save_os_error(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/local/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._get_owner = MagicMock()
        svc._get_owner_type = MagicMock(return_value="other")
        svc._resolve_subdir_path = MagicMock(return_value=None)
        svc.DEFAULT_SUBDIRS = {}
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "file.txt"
        svc._path_validator.sanitize_relative_dir.return_value = []
        svc._is_cloud_storage = MagicMock(return_value=False)
        svc._filesystem_service = MagicMock()
        svc._filesystem_service.save_bytes.side_effect = OSError("disk full")

        with pytest.raises(ValidationException) as exc_info:
            svc.save_file_to_bound_folder(
                owner_id=1, file_content=b"data", file_name="file.txt", subdir_key="k"
            )
        assert "FILE_SAVE_FAILED" in str(exc_info.value.code)


class TestExtractZipToBoundFolder:
    def test_no_binding_returns_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.get_binding = MagicMock(return_value=None)
        result = svc.extract_zip_to_bound_folder(owner_id=1, zip_content=b"data")
        assert result is None

    def test_local_extract_success(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/local/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._is_cloud_storage = MagicMock(return_value=False)
        svc._filesystem_service = MagicMock()
        svc._filesystem_service.extract_zip_bytes.return_value = "/local/root/extracted"

        result = svc.extract_zip_to_bound_folder(owner_id=1, zip_content=b"PKdata")
        assert result == "/local/root/extracted"

    def test_local_extract_error(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/local/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._is_cloud_storage = MagicMock(return_value=False)
        svc._filesystem_service = MagicMock()
        svc._filesystem_service.extract_zip_bytes.side_effect = OSError("permission denied")

        with pytest.raises(ValidationException):
            svc.extract_zip_to_bound_folder(owner_id=1, zip_content=b"PKdata")

    def test_cloud_extract_success(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService
        import io
        import zipfile

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/cloud/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._is_cloud_storage = MagicMock(return_value=True)
        mock_provider = MagicMock()
        svc._get_provider_for_binding = MagicMock(return_value=mock_provider)
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "test.txt"

        # Create a real zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("subdir/", "")
            zf.writestr("subdir/test.txt", "hello")
        zip_content = buf.getvalue()

        result = svc.extract_zip_to_bound_folder(owner_id=1, zip_content=zip_content)
        assert result == "/cloud/root"
        mock_provider.mkdir.assert_called()
        mock_provider.write_file.assert_called()

    def test_cloud_extract_skips_dangerous_paths(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService
        import io
        import zipfile

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/cloud/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._is_cloud_storage = MagicMock(return_value=True)
        mock_provider = MagicMock()
        svc._get_provider_for_binding = MagicMock(return_value=mock_provider)
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "evil.txt"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.txt", "bad")
            zf.writestr("subdir/..\\evil2.txt", "bad2")
            zf.writestr("good.txt", "ok")
        zip_content = buf.getvalue()

        result = svc.extract_zip_to_bound_folder(owner_id=1, zip_content=zip_content)
        # Only "good.txt" should be written
        assert result == "/cloud/root"

    def test_cloud_extract_error(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService
        import io
        import zipfile

        svc = FolderBindingCrudService()
        mock_binding = MagicMock()
        mock_binding.resolved_folder_path = "/cloud/root"
        svc.get_binding = MagicMock(return_value=mock_binding)
        svc._is_cloud_storage = MagicMock(return_value=True)
        mock_provider = MagicMock()
        mock_provider.write_file.side_effect = Exception("cloud error")
        svc._get_provider_for_binding = MagicMock(return_value=mock_provider)
        svc._path_validator = MagicMock()
        svc._path_validator.sanitize_file_name.return_value = "test.txt"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("test.txt", "hello")
        zip_content = buf.getvalue()

        with pytest.raises(ValidationException):
            svc.extract_zip_to_bound_folder(owner_id=1, zip_content=zip_content)


class TestUpdateBinding:
    def test_delegates_to_create(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.create_binding = MagicMock(return_value="result")

        result = svc.update_binding(owner_id=1, folder_path="/test")
        svc.create_binding.assert_called_once_with(owner_id=1, folder_path="/test")
        assert result == "result"
