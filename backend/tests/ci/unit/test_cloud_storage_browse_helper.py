"""browse_helper 单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.cloud_storage.browse_helper import browse_cloud_folder, list_active_cloud_accounts


class TestListActiveCloudAccounts:
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_returns_active_accounts(self, mock_csa):
        mock_qs = MagicMock()
        mock_csa.objects.filter.return_value = mock_qs
        mock_qs.values.return_value = mock_qs
        mock_qs.__iter__ = MagicMock(return_value=iter([
            {"id": 1, "name": "坚果云", "storage_type": "webdav"},
        ]))
        mock_qs.__bool__ = MagicMock(return_value=True)

        result = list_active_cloud_accounts()
        mock_csa.objects.filter.assert_called_once_with(is_active=True)

    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_empty_when_no_accounts(self, mock_csa):
        mock_qs = MagicMock()
        mock_csa.objects.filter.return_value = mock_qs
        mock_qs.values.return_value = []
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_qs.__bool__ = MagicMock(return_value=True)

        result = list_active_cloud_accounts()
        assert result == []


class TestBrowseCloudFolder:
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_account_not_found(self, mock_csa):
        mock_csa.objects.filter.return_value.first.return_value = None

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=999,
            path="/",
        )
        assert result["browsable"] is False
        assert "不存在" in result["message"]

    @patch("apps.core.cloud_storage.factory.create_provider_from_account")
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_successful_browse(self, mock_csa, mock_create_provider):
        mock_account = MagicMock()
        mock_csa.objects.filter.return_value.first.return_value = mock_account

        mock_provider = MagicMock()
        mock_provider.list_directory.return_value = [
            MagicMock(name="folder1", is_dir=True),
            MagicMock(name="file1.pdf", is_dir=False),
            MagicMock(name="folder2", is_dir=True),
        ]
        # Set name attribute on mocks
        mock_provider.list_directory.return_value[0].name = "folder1"
        mock_provider.list_directory.return_value[1].name = "file1.pdf"
        mock_provider.list_directory.return_value[2].name = "folder2"
        mock_create_provider.return_value = mock_provider

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path="/docs",
        )
        assert result["browsable"] is True
        assert len(result["entries"]) == 2  # only dirs
        assert result["entries"][0]["name"] == "folder1"
        assert result["entries"][1]["name"] == "folder2"
        assert result["path"] == "/docs"

    @patch("apps.core.cloud_storage.factory.create_provider_from_account")
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_provider_exception_returns_error(self, mock_csa, mock_create_provider):
        mock_account = MagicMock()
        mock_csa.objects.filter.return_value.first.return_value = mock_account

        mock_provider = MagicMock()
        mock_provider.list_directory.side_effect = ConnectionError("timeout")
        mock_create_provider.return_value = mock_provider

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path="/",
        )
        assert result["browsable"] is False
        assert "访问失败" in result["message"]

    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_root_path_default(self, mock_csa):
        mock_csa.objects.filter.return_value.first.return_value = None

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path=None,
        )
        assert result["browsable"] is False  # account not found

    @patch("apps.core.cloud_storage.factory.create_provider_from_account")
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_hidden_files_filtered(self, mock_csa, mock_create_provider):
        mock_account = MagicMock()
        mock_csa.objects.filter.return_value.first.return_value = mock_account

        mock_provider = MagicMock()
        item1 = MagicMock(name="visible", is_dir=True)
        item1.name = "visible"
        item2 = MagicMock(name=".hidden", is_dir=True)
        item2.name = ".hidden"
        mock_provider.list_directory.return_value = [item1, item2]
        mock_create_provider.return_value = mock_provider

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path="/",
            include_hidden=False,
        )
        assert len(result["entries"]) == 1
        assert result["entries"][0]["name"] == "visible"

    @patch("apps.core.cloud_storage.factory.create_provider_from_account")
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_parent_path_computed(self, mock_csa, mock_create_provider):
        mock_account = MagicMock()
        mock_csa.objects.filter.return_value.first.return_value = mock_account

        mock_provider = MagicMock()
        mock_provider.list_directory.return_value = []
        mock_create_provider.return_value = mock_provider

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path="/docs/2024",
        )
        assert result["parent_path"] == "/docs"

    @patch("apps.core.cloud_storage.factory.create_provider_from_account")
    @patch("apps.core.cloud_storage.browse_helper.CloudStorageAccount")
    def test_root_parent_is_slash(self, mock_csa, mock_create_provider):
        mock_account = MagicMock()
        mock_csa.objects.filter.return_value.first.return_value = mock_account

        mock_provider = MagicMock()
        mock_provider.list_directory.return_value = []
        mock_create_provider.return_value = mock_provider

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path="/",
        )
        assert result["parent_path"] == "/"
