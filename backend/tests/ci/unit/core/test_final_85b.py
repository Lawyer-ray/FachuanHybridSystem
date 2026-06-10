"""Coverage boost tests for core module — folder_binding, s3_provider, filesystem, cloud_storage."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone as tz
from pathlib import PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, PropertyMock, patch, call

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ============================================================================
# folder_binding_crud_service.py — FolderBindingCrudService
# ============================================================================


class TestFolderBindingCrudServiceGetOwner:
    def test_raises_when_owner_model_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.owner_model = None
        with pytest.raises(RuntimeError, match="owner_model"):
            svc._get_owner(owner_id=1)

    def test_raises_when_owner_not_found(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        mock_model = Mock()
        mock_model.objects.filter.return_value.first.return_value = None
        svc = FolderBindingCrudService()
        svc.owner_model = mock_model
        with pytest.raises(NotFoundError):
            svc._get_owner(owner_id=999)

    def test_returns_owner_when_found(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        mock_owner = Mock()
        mock_model = Mock()
        mock_model.objects.filter.return_value.first.return_value = mock_owner
        svc = FolderBindingCrudService()
        svc.owner_model = mock_model
        result = svc._get_owner(owner_id=1)
        assert result is mock_owner


class TestFolderBindingCrudServiceGetOwnerType:
    def test_returns_case_type(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = Mock()
        owner.case_type = "civil"
        assert svc._get_owner_type(owner) == "civil"

    def test_returns_empty_when_no_case_type(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = SimpleNamespace()
        assert svc._get_owner_type(owner) == ""


class TestFolderBindingCrudServiceComputeRelativePath:
    def test_returns_none_when_no_contract(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        owner = SimpleNamespace(contract=None)
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_returns_none_when_no_folder_binding(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        contract = SimpleNamespace(folder_binding=None)
        owner = SimpleNamespace(contract=contract)
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_returns_none_when_binding_has_no_folder_path(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        binding = SimpleNamespace(folder_path="")
        contract = SimpleNamespace(folder_binding=binding)
        owner = SimpleNamespace(contract=contract)
        assert svc._compute_relative_path(owner, "/some/path") is None

    def test_returns_relative_path_when_case_under_contract(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        binding = SimpleNamespace(folder_path="/data/contracts/c001")
        contract = SimpleNamespace(folder_binding=binding)
        owner = SimpleNamespace(contract=contract)
        result = svc._compute_relative_path(owner, "/data/contracts/c001/cases/case001")
        assert result == "cases/case001"

    def test_returns_none_when_not_relative(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        binding = SimpleNamespace(folder_path="/other/path")
        contract = SimpleNamespace(folder_binding=binding)
        owner = SimpleNamespace(contract=contract)
        result = svc._compute_relative_path(owner, "/data/contracts/c001/cases/case001")
        assert result is None


class TestFolderBindingCrudServiceCreateBinding:
    def test_raises_when_binding_model_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = None
        with pytest.raises(RuntimeError, match="binding_model"):
            svc.create_binding(owner_id=1, folder_path="/tmp")

    def test_raises_when_owner_rel_field_empty(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = Mock()
        svc.owner_rel_field = ""
        with pytest.raises(RuntimeError, match="owner_rel_field"):
            svc.create_binding(owner_id=1, folder_path="/tmp")


class TestFolderBindingCrudServiceDeleteBinding:
    def test_raises_when_binding_model_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = None
        with pytest.raises(RuntimeError, match="binding_model"):
            svc.delete_binding(owner_id=1)

    def test_raises_when_owner_id_field_empty(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = Mock()
        svc.owner_id_field = ""
        with pytest.raises(RuntimeError, match="owner_id_field"):
            svc.delete_binding(owner_id=1)


class TestFolderBindingCrudServiceGetBinding:
    def test_raises_when_binding_model_none(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = None
        with pytest.raises(RuntimeError, match="binding_model"):
            svc.get_binding(owner_id=1)

    def test_raises_when_owner_id_field_empty(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        svc.binding_model = Mock()
        svc.owner_id_field = ""
        with pytest.raises(RuntimeError, match="owner_id_field"):
            svc.get_binding(owner_id=1)


class TestFolderBindingCrudServiceSaveFileToBoundFolder:
    def test_returns_none_when_no_binding(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        with patch.object(svc, "get_binding", return_value=None):
            result = svc.save_file_to_bound_folder(
                owner_id=1, file_content=b"test", file_name="test.pdf", subdir_key="docs"
            )
            assert result is None


class TestFolderBindingCrudServiceExtractZipToBoundFolder:
    def test_returns_none_when_no_binding(self):
        from apps.core.filesystem.folder_binding_crud_service import FolderBindingCrudService

        svc = FolderBindingCrudService()
        with patch.object(svc, "get_binding", return_value=None):
            result = svc.extract_zip_to_bound_folder(owner_id=1, zip_content=b"PK...")
            assert result is None


# ============================================================================
# folder_binding_base.py — BaseFolderBindingService
# ============================================================================


class TestBaseFolderBindingServiceProperties:
    def test_path_validator_lazy(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        assert svc._path_validator is None
        validator = svc.path_validator
        assert svc._path_validator is not None
        assert svc.path_validator is validator  # same instance

    def test_filesystem_service_lazy(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        assert svc._filesystem_service is None
        fs = svc.filesystem_service
        assert svc._filesystem_service is not None
        assert svc.filesystem_service is fs

    def test_browse_policy_lazy(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        assert svc._browse_policy is None
        policy = svc.browse_policy
        assert svc._browse_policy is not None
        assert svc.browse_policy is policy

    def test_inode_resolver_lazy(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        assert svc._inode_resolver is None
        resolver = svc.inode_resolver
        assert svc._inode_resolver is not None
        assert svc.inode_resolver is resolver


class TestBaseFolderBindingServiceMethods:
    def test_validate_folder_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_validator = Mock()
        mock_validator.validate_folder_path.return_value = (True, None)
        svc._path_validator = mock_validator
        ok, err = svc.validate_folder_path("/valid/path")
        assert ok is True
        assert err is None

    def test_is_network_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_validator = Mock()
        mock_validator.is_network_path.return_value = True
        svc._path_validator = mock_validator
        assert svc._is_network_path("//server/share") is True

    def test_format_path_for_display_short(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        assert svc.format_path_for_display("/short/path") == "/short/path"

    def test_format_path_for_display_empty(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        assert svc.format_path_for_display("") == ""

    def test_format_path_for_display_long(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        path = "/very/long/path/to/some/deeply/nested/directory/structure/here"
        result = svc.format_path_for_display(path, max_length=30)
        assert len(result) == 30
        assert "..." in result

    def test_is_browsable_network_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_validator = Mock()
        mock_validator.is_network_path.return_value = True
        svc._path_validator = mock_validator
        ok, msg = svc.is_browsable_path("//server/share")
        assert ok is False
        assert "网络路径" in msg

    def test_is_browsable_normal_path(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_validator = Mock()
        mock_validator.is_network_path.return_value = False
        svc._path_validator = mock_validator
        ok, msg = svc.is_browsable_path("/local/path")
        assert ok is True
        assert msg is None

    def test_is_cloud_storage_returns_false_for_local(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="local", storage_account=None)
        assert svc._is_cloud_storage(binding) is False

    def test_is_cloud_storage_returns_true_for_s3(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=Mock())
        assert svc._is_cloud_storage(binding) is True

    def test_is_cloud_storage_returns_false_when_no_account(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=None)
        assert svc._is_cloud_storage(binding) is False

    def test_check_folder_accessible_local(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_folder = Mock()
        mock_folder.exists.return_value = True
        mock_folder.is_dir.return_value = True
        with patch("apps.core.filesystem.folder_binding_base.Path", return_value=mock_folder):
            assert svc.check_folder_accessible("/existing/path") is True

    def test_check_folder_accessible_local_not_exists(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_folder = Mock()
        mock_folder.exists.return_value = False
        with patch("apps.core.filesystem.folder_binding_base.Path", return_value=mock_folder):
            assert svc.check_folder_accessible("/nonexistent") is False

    def test_check_folder_accessible_os_error(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_folder = Mock()
        mock_folder.exists.side_effect = OSError("permission denied")
        with patch("apps.core.filesystem.folder_binding_base.Path", return_value=mock_folder):
            assert svc.check_folder_accessible("/locked/path") is False

    def test_check_folder_accessible_cloud(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=Mock())
        mock_provider = Mock()
        mock_provider.is_dir.return_value = True
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            assert svc.check_folder_accessible("/cloud/path", binding=binding) is True

    def test_check_folder_accessible_cloud_exception(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=Mock())
        mock_provider = Mock()
        mock_provider.is_dir.side_effect = RuntimeError("connection failed")
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            assert svc.check_folder_accessible("/cloud/path", binding=binding) is False

    def test_list_subdirs_cloud(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        from apps.core.cloud_storage.protocols import CloudFileInfo

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=Mock())
        mock_provider = Mock()
        mock_provider.list_directory.return_value = [
            CloudFileInfo(name="subdir1", path="/root/subdir1", is_dir=True, size=0, modified_at=0.0),
            CloudFileInfo(name="file.txt", path="/root/file.txt", is_dir=False, size=100, modified_at=0.0),
            CloudFileInfo(name=".hidden", path="/root/.hidden", is_dir=True, size=0, modified_at=0.0),
        ]
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            result = svc.list_subdirs("/root", binding=binding)
            assert len(result) == 1
            assert result[0]["name"] == "subdir1"

    def test_list_subdirs_cloud_include_hidden(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService
        from apps.core.cloud_storage.protocols import CloudFileInfo

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=Mock())
        mock_provider = Mock()
        mock_provider.list_directory.return_value = [
            CloudFileInfo(name="subdir1", path="/root/subdir1", is_dir=True, size=0, modified_at=0.0),
            CloudFileInfo(name=".hidden", path="/root/.hidden", is_dir=True, size=0, modified_at=0.0),
        ]
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            result = svc.list_subdirs("/root", include_hidden=True, binding=binding)
            assert len(result) == 2

    def test_list_subdirs_cloud_exception(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="s3", storage_account=Mock())
        mock_provider = Mock()
        mock_provider.list_directory.side_effect = RuntimeError("fail")
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            result = svc.list_subdirs("/root", binding=binding)
            assert result == []

    def test_check_and_repair_path_cloud_accessible(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(
            storage_type="s3", storage_account=Mock(), folder_path="/cloud/path", id=1
        )
        mock_provider = Mock()
        mock_provider.is_dir.return_value = True
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            ok, repaired = svc.check_and_repair_path(binding)
            assert ok is True
            assert repaired is False

    def test_check_and_repair_path_cloud_not_accessible(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(
            storage_type="s3", storage_account=Mock(), folder_path="/cloud/path", id=1
        )
        mock_provider = Mock()
        mock_provider.is_dir.return_value = False
        mock_provider.exists.return_value = False
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            ok, repaired = svc.check_and_repair_path(binding)
            assert ok is False
            assert repaired is False

    def test_check_and_repair_path_cloud_exception(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(
            storage_type="s3", storage_account=Mock(), folder_path="/cloud/path", id=1
        )
        mock_provider = Mock()
        mock_provider.is_dir.side_effect = RuntimeError("boom")
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            ok, repaired = svc.check_and_repair_path(binding)
            assert ok is False
            assert repaired is False

    def test_check_and_repair_path_local_accessible_no_inode(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(storage_type="local", folder_path="/existing", id=1)
        with patch.object(svc, "check_folder_accessible", return_value=True):
            with patch.object(svc, "_maybe_fill_inode"):
                ok, repaired = svc.check_and_repair_path(binding)
                assert ok is True
                assert repaired is False

    def test_check_and_repair_path_local_no_inode_no_device(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(
            storage_type="local", folder_path="/missing", id=1,
            folder_inode=None, folder_device=None
        )
        with patch.object(svc, "check_folder_accessible", return_value=False):
            ok, repaired = svc.check_and_repair_path(binding)
            assert ok is False
            assert repaired is False

    def test_maybe_fill_inode_skips_when_no_field(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace()  # no folder_inode attr
        svc._maybe_fill_inode(binding)  # should not raise

    def test_maybe_fill_inode_skips_when_already_set(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = SimpleNamespace(folder_inode=12345)
        svc._maybe_fill_inode(binding)  # should return early

    def test_maybe_fill_inode_backfills(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        binding = Mock()
        binding.folder_inode = None
        binding.folder_path = "/some/path"
        binding.id = 1
        mock_resolver = Mock()
        mock_resolver.get_inode_info.return_value = (999, 888)
        svc._inode_resolver = mock_resolver
        svc._maybe_fill_inode(binding)
        assert binding.folder_inode == 999
        assert binding.folder_device == 888
        binding.save.assert_called_once()

    def test_ensure_subdirectories(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        svc.DEFAULT_SUBDIRS = {"a": "dir_a", "b": "dir_b"}
        mock_fs = Mock()
        mock_fs.ensure_subdirectories.return_value = True
        svc._filesystem_service = mock_fs
        result = svc.ensure_subdirectories("/base")
        assert result is True

    def test_compute_parent_path_in_roots(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_policy = Mock()
        mock_policy.get_browse_roots.return_value = [PurePosixPath("/data")]
        svc._browse_policy = mock_policy
        result = svc.compute_parent_path(PurePosixPath("/data/projects"))
        assert result == "/data"

    def test_compute_parent_path_not_in_roots(self):
        from apps.core.filesystem.folder_binding_base import BaseFolderBindingService

        svc = BaseFolderBindingService()
        mock_policy = Mock()
        mock_policy.get_browse_roots.return_value = [PurePosixPath("/other")]
        svc._browse_policy = mock_policy
        result = svc.compute_parent_path(PurePosixPath("/data/projects"))
        assert result is None


# ============================================================================
# s3_provider.py — S3Provider
# ============================================================================


def _make_s3_provider(root: str = "") -> "S3Provider":
    """Create an S3Provider without actually connecting to S3."""
    from apps.core.cloud_storage.s3_provider import S3Provider

    provider = object.__new__(S3Provider)
    provider._bucket = "test-bucket"
    provider._root = root
    provider._client = Mock()
    provider._client.exceptions.ClientError = Exception
    return provider


class TestS3ProviderFullKey:
    def test_with_root(self):
        provider = _make_s3_provider(root="root")
        assert provider._full_key("path/to/file") == "root/path/to/file"

    def test_without_root(self):
        provider = _make_s3_provider(root="")
        assert provider._full_key("path/to/file") == "path/to/file"

    def test_strips_slashes(self):
        provider = _make_s3_provider(root="")
        assert provider._full_key("/path/to/file/") == "path/to/file"


class TestS3ProviderListDirectory:
    def test_lists_files_and_dirs(self):
        provider = _make_s3_provider(root="root")

        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {
                "CommonPrefixes": [{"Prefix": "root/subdir1/"}],
                "Contents": [
                    {"Key": "root", "Size": 0, "LastModified": datetime(2024, 1, 1, tzinfo=tz.utc)},
                    {"Key": "root/file1.txt", "Size": 100, "LastModified": datetime(2024, 1, 2, tzinfo=tz.utc)},
                    {"Key": "root/subdir/nested.txt", "Size": 200, "LastModified": datetime(2024, 1, 3, tzinfo=tz.utc)},
                ],
            }
        ]
        provider._client.get_paginator.return_value = mock_paginator

        results = provider.list_directory("")
        dirs = [r for r in results if r.is_dir]
        files = [r for r in results if not r.is_dir]
        assert len(dirs) == 1
        assert len(files) == 1  # nested.txt is filtered out (has "/" in name)


class TestS3ProviderReadFile:
    def test_reads_bytes(self):
        provider = _make_s3_provider(root="")
        mock_body = Mock()
        mock_body.read.return_value = b"file content"
        provider._client.get_object.return_value = {"Body": mock_body}
        result = provider.read_file("test.txt")
        assert result == b"file content"


class TestS3ProviderWriteFile:
    def test_creates_parent_dir(self):
        provider = _make_s3_provider(root="")
        with patch.object(provider, "mkdir") as mock_mkdir:
            provider.write_file("dir/file.txt", b"content")
            mock_mkdir.assert_called_once_with("dir")
        provider._client.put_object.assert_called_once()


class TestS3ProviderMkdir:
    def test_creates_nested_dirs(self):
        provider = _make_s3_provider(root="")
        with patch.object(provider, "exists", return_value=False):
            provider.mkdir("a/b/c")
            assert provider._client.put_object.call_count == 3


class TestS3ProviderExists:
    def test_returns_true_when_object_exists(self):
        provider = _make_s3_provider(root="")
        provider._client.head_object.return_value = {}
        assert provider.exists("file.txt") is True

    def test_returns_false_when_404_and_no_children(self):
        from botocore.exceptions import ClientError

        provider = _make_s3_provider(root="")
        provider._client.exceptions.ClientError = ClientError
        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        provider._client.head_object.side_effect = error
        provider._client.list_objects_v2.return_value = {"KeyCount": 0}
        assert provider.exists("missing") is False

    def test_returns_true_when_404_but_has_children(self):
        from botocore.exceptions import ClientError

        provider = _make_s3_provider(root="")
        provider._client.exceptions.ClientError = ClientError
        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        provider._client.head_object.side_effect = error
        provider._client.list_objects_v2.return_value = {"KeyCount": 1}
        assert provider.exists("dir") is True


class TestS3ProviderIsDir:
    def test_returns_true_when_has_children(self):
        provider = _make_s3_provider(root="")
        provider._client.list_objects_v2.return_value = {"KeyCount": 1}
        assert provider.is_dir("some_dir") is True

    def test_returns_false_when_empty(self):
        provider = _make_s3_provider(root="")
        provider._client.list_objects_v2.return_value = {"KeyCount": 0}
        assert provider.is_dir("empty_dir") is False


class TestS3ProviderDeleteFile:
    def test_calls_delete_object(self):
        provider = _make_s3_provider(root="")
        provider.delete_file("file.txt")
        provider._client.delete_object.assert_called_once()


class TestS3ProviderGetFileInfo:
    def test_returns_file_info(self):
        provider = _make_s3_provider(root="")
        provider._client.head_object.return_value = {
            "ContentLength": 42,
            "LastModified": datetime(2024, 6, 1, tzinfo=tz.utc),
        }
        result = provider.get_file_info("test.txt")
        assert result is not None
        assert result.name == "test.txt"
        assert result.size == 42
        assert result.is_dir is False

    def test_returns_dir_info_when_trailing_slash(self):
        from botocore.exceptions import ClientError

        provider = _make_s3_provider(root="")
        provider._client.exceptions.ClientError = ClientError

        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")

        call_count = [0]
        def mock_head(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise error
            return {"LastModified": datetime(2024, 6, 1, tzinfo=tz.utc)}

        provider._client.head_object.side_effect = mock_head
        result = provider.get_file_info("mydir")
        assert result is not None
        assert result.is_dir is True

    def test_returns_virtual_dir_info(self):
        from botocore.exceptions import ClientError

        provider = _make_s3_provider(root="")
        provider._client.exceptions.ClientError = ClientError
        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        provider._client.head_object.side_effect = error
        provider._client.list_objects_v2.return_value = {"KeyCount": 1}
        result = provider.get_file_info("mydir")
        assert result is not None
        assert result.is_dir is True

    def test_returns_none_when_not_found(self):
        from botocore.exceptions import ClientError

        provider = _make_s3_provider(root="")
        provider._client.exceptions.ClientError = ClientError
        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        provider._client.head_object.side_effect = error
        provider._client.list_objects_v2.return_value = {"KeyCount": 0}
        result = provider.get_file_info("missing")
        assert result is None


class TestS3ProviderWalk:
    def test_walks_tree(self):
        from apps.core.cloud_storage.protocols import CloudFileInfo

        provider = _make_s3_provider(root="")

        with patch.object(provider, "list_directory") as mock_list:
            mock_list.side_effect = [
                [  # root
                    CloudFileInfo(name="sub", path="sub", is_dir=True, size=0, modified_at=0.0),
                    CloudFileInfo(name="file.txt", path="file.txt", is_dir=False, size=10, modified_at=0.0),
                ],
                [  # sub
                    CloudFileInfo(name="nested.txt", path="sub/nested.txt", is_dir=False, size=20, modified_at=0.0),
                ],
            ]
            results = list(provider.walk(""))
            assert len(results) == 2
            assert results[0][0] == ""
            assert len(results[0][2]) == 1  # file.txt
            assert results[1][0] == "/sub"  # "" + "/" + "sub"
            assert len(results[1][2]) == 1  # nested.txt
