"""browse_helper 单元测试."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.cloud_storage.browse_helper import abrowse_cloud_folder, browse_cloud_folder, list_active_cloud_accounts


class TestListActiveCloudAccounts:
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_returns_active_accounts(self, mock_csa):
        mock_qs = MagicMock()
        mock_csa.objects.filter.return_value = mock_qs
        mock_qs.values.return_value = mock_qs
        mock_qs.__iter__ = MagicMock(
            return_value=iter(
                [
                    {"id": 1, "name": "坚果云", "storage_type": "webdav"},
                ]
            )
        )
        mock_qs.__bool__ = MagicMock(return_value=True)

        result = list_active_cloud_accounts()
        mock_csa.objects.filter.assert_called_once_with(is_active=True)

    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_empty_when_no_accounts(self, mock_csa):
        mock_qs = MagicMock()
        mock_csa.objects.filter.return_value = mock_qs
        mock_qs.values.return_value = []
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_qs.__bool__ = MagicMock(return_value=True)

        result = list_active_cloud_accounts()
        assert result == []


class TestBrowseCloudFolder:
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_account_not_found(self, mock_csa):
        mock_csa.objects.filter.return_value.first.return_value = None

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=999,
            path="/",
        )
        assert result["browsable"] is False
        assert "不存在" in result["message"]

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
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

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
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

    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_root_path_default(self, mock_csa):
        mock_csa.objects.filter.return_value.first.return_value = None

        result = browse_cloud_folder(
            storage_type="webdav",
            storage_account_id=1,
            path=None,
        )
        assert result["browsable"] is False  # account not found

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
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

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
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

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
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


class TestBrowseCloudFolderRateLimit:
    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_rate_limit_error_returns_message(self, mock_csa, mock_create_provider):
        from apps.cloud_storage.exceptions import CloudStorageRateLimitError

        mock_csa.objects.filter.return_value.first.return_value = MagicMock()
        mock_provider = MagicMock()
        mock_provider.list_directory.side_effect = CloudStorageRateLimitError("请求过于频繁，请稍后再试")
        mock_create_provider.return_value = mock_provider

        result = browse_cloud_folder(storage_type="webdav", storage_account_id=1, path="/")
        assert result["browsable"] is False
        assert "频繁" in result["message"]  # 限流原文透出（非通用兜底文案）


class TestAbrowseCloudFolder:
    """异步版：alist_directory 快路径 / sync_to_async 回退 / 错误分支 / 父路径。"""

    @staticmethod
    def _make_provider(children: list | None = None, *, with_alist: bool = True) -> MagicMock:
        provider = MagicMock()
        if with_alist:
            provider.alist_directory = MagicMock(return_value=_async_iter(children or []))
        else:
            # 无 alist_directory 属性时走 sync_to_async 分支（hasattr 为 False）
            provider.alist_directory = MagicMock()
            del provider.alist_directory
            provider.list_directory = MagicMock(return_value=children or [])
        return provider


def _async_iter(items):
    async def _list(_path):
        return items

    return _list


def _arun(coro):
    from asgiref.sync import async_to_sync

    return async_to_sync(lambda: coro)()


class TestAbrowse:
    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_alist_path_success(self, mock_csa, mock_create_provider):
        import asyncio

        async def _afirst():
            return MagicMock()

        mock_csa.objects.filter.return_value.afirst = _afirst
        provider = MagicMock()

        async def _alist(_path):
            item = MagicMock()
            item.is_dir = True
            item.name = "docs"
            return [item]

        provider.alist_directory = _alist
        provider.has_alist = True
        mock_create_provider.return_value = provider

        result = asyncio.run(abrowse_cloud_folder(storage_type="webdav", storage_account_id=1, path="/"))
        assert result["browsable"] is True
        assert result["entries"] == [{"name": "docs", "path": "/docs"}]
        assert result["parent_path"] == "/"

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_sync_provider_falls_back_to_list_directory(self, mock_csa, mock_create_provider):
        import asyncio

        async def _afirst():
            return MagicMock()

        mock_csa.objects.filter.return_value.afirst = _afirst
        provider = MagicMock(spec=["list_directory"])  # 无 alist_directory
        item = MagicMock()
        item.is_dir = True
        item.name = "backup"
        provider.list_directory.return_value = [item]
        mock_create_provider.return_value = provider

        result = asyncio.run(abrowse_cloud_folder(storage_type="local", storage_account_id=1, path="/data"))
        assert result["browsable"] is True
        assert result["entries"] == [{"name": "backup", "path": "/data/backup"}]
        assert result["parent_path"] == "/"
        provider.list_directory.assert_called_once_with("/data")

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_account_not_found(self, mock_csa, mock_create_provider):
        import asyncio

        async def _afirst():
            return None

        mock_csa.objects.filter.return_value.afirst = _afirst
        result = asyncio.run(abrowse_cloud_folder(storage_type="webdav", storage_account_id=42, path="/x"))
        assert result["browsable"] is False
        assert "不存在" in result["message"]
        mock_create_provider.assert_not_called()

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_rate_limit_error(self, mock_csa, mock_create_provider):
        import asyncio

        from apps.cloud_storage.exceptions import CloudStorageRateLimitError

        async def _afirst():
            return MagicMock()

        mock_csa.objects.filter.return_value.afirst = _afirst
        provider = MagicMock(spec=["alist_directory"])

        async def _alist(_path):
            raise CloudStorageRateLimitError("too frequent")

        provider.alist_directory = _alist
        mock_create_provider.return_value = provider

        result = asyncio.run(abrowse_cloud_folder(storage_type="webdav", storage_account_id=1, path="/"))
        assert result["browsable"] is False
        assert result["message"] == "too frequent"

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_generic_exception_swallowed(self, mock_csa, mock_create_provider):
        import asyncio

        async def _afirst():
            return MagicMock()

        mock_csa.objects.filter.return_value.afirst = _afirst
        provider = MagicMock(spec=["alist_directory"])

        async def _alist(_path):
            raise RuntimeError("boom")

        provider.alist_directory = _alist
        mock_create_provider.return_value = provider

        result = asyncio.run(abrowse_cloud_folder(storage_type="webdav", storage_account_id=1, path="/"))
        assert result["browsable"] is False
        assert "访问失败" in result["message"]

    @patch("apps.cloud_storage.factory.create_provider_from_account")
    @patch("apps.cloud_storage.browse_helper.CloudStorageAccount")
    def test_hidden_and_files_filtered_with_parent(self, mock_csa, mock_create_provider):
        import asyncio

        async def _afirst():
            return MagicMock()

        mock_csa.objects.filter.return_value.afirst = _afirst
        provider = MagicMock(spec=["alist_directory"])

        async def _alist(_path):
            folder = MagicMock()
            folder.is_dir = True
            folder.name = "Zeta"
            hidden = MagicMock()
            hidden.is_dir = True
            hidden.name = ".git"
            alpha = MagicMock()
            alpha.is_dir = True
            alpha.name = "alpha"
            return [folder, hidden, alpha]

        provider.alist_directory = _alist
        mock_create_provider.return_value = provider

        result = asyncio.run(abrowse_cloud_folder(storage_type="webdav", storage_account_id=1, path="/root"))
        # 隐藏目录过滤 + 忽略大小写排序
        assert [e["name"] for e in result["entries"]] == ["alpha", "Zeta"]
        assert result["parent_path"] == "/"
