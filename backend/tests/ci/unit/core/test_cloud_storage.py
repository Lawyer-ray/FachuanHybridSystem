"""测试 core.cloud_storage 子模块

覆盖: webdav_provider, onedrive_provider, s3_provider, dropbox_provider,
      protocols, exceptions, factory, null_provider, local
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.cloud_storage.exceptions import CloudStorageError, CloudStorageRateLimitError
from apps.core.cloud_storage.protocols import CloudFileInfo


# ============================================================
# CloudFileInfo
# ============================================================


class TestCloudFileInfo:
    """测试 CloudFileInfo 数据类"""

    def test_creation(self) -> None:
        info = CloudFileInfo(name="file.txt", path="/dir/file.txt", is_dir=False, size=1024, modified_at=100.0)
        assert info.name == "file.txt"
        assert info.is_dir is False
        assert info.size == 1024

    def test_frozen(self) -> None:
        info = CloudFileInfo(name="a", path="/a", is_dir=True, size=0, modified_at=0.0)
        with pytest.raises(AttributeError):
            info.name = "b"  # type: ignore[misc]


# ============================================================
# CloudStorageError hierarchy
# ============================================================


class TestCloudStorageExceptions:
    """测试云存储异常类"""

    def test_base_error(self) -> None:
        err = CloudStorageError("msg", provider="WebDAV", retry_after=30)
        assert str(err) == "msg"
        assert err.provider == "WebDAV"
        assert err.retry_after == 30

    def test_base_error_defaults(self) -> None:
        err = CloudStorageError("msg")
        assert err.provider == ""
        assert err.retry_after is None

    def test_rate_limit_error(self) -> None:
        err = CloudStorageRateLimitError("rate limited", provider="OneDrive", retry_after=60)
        assert isinstance(err, CloudStorageError)
        assert err.provider == "OneDrive"
        assert err.retry_after == 60


# ============================================================
# WebDAVProvider
# ============================================================


class TestWebDAVProvider:
    """测试 WebDAVProvider"""

    @patch("apps.core.cloud_storage.webdav_provider.requests.Session")
    def test_init(self, mock_session_cls: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        provider = WebDAVProvider(username="user", app_password="pass", root_path="/myroot")
        assert provider._root == "/myroot"
        assert provider._username == "user"

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_full_path(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_requests.Session.return_value = MagicMock()
        provider = WebDAVProvider(username="u", app_password="p", root_path="root")
        assert provider._full_path("") == "/root"
        assert provider._full_path("sub/file.txt") == "/root/sub/file.txt"
        assert provider._full_path("/sub/") == "/root/sub"

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_url_construction(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_requests.Session.return_value = MagicMock()
        provider = WebDAVProvider(
            username="u", app_password="p", root_path="/docs",
            webdav_url="https://dav.example.com/dav/"
        )
        url = provider._url("file.txt")
        assert url.startswith("https://dav.example.com/dav/")
        assert "file.txt" in url

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_503_raises_rate_limit(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_session.request.return_value = mock_response

        provider = WebDAVProvider(username="u", app_password="p")
        with pytest.raises(CloudStorageRateLimitError):
            provider._request("GET", "test")

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_exists_true(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session
        mock_session.request.return_value = MagicMock(status_code=200)

        provider = WebDAVProvider(username="u", app_password="p")
        assert provider.exists("file.txt") is True

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_exists_false(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session
        mock_session.request.return_value = MagicMock(status_code=404)

        provider = WebDAVProvider(username="u", app_password="p")
        assert provider.exists("missing.txt") is False

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_delete_file_success(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session
        mock_session.request.return_value = MagicMock(status_code=204)

        provider = WebDAVProvider(username="u", app_password="p")
        provider.delete_file("file.txt")  # 不抛异常

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_delete_file_404_ok(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import WebDAVProvider

        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session
        mock_session.request.return_value = MagicMock(status_code=404)

        provider = WebDAVProvider(username="u", app_password="p")
        provider.delete_file("missing.txt")  # 404 不报错

    @patch("apps.core.cloud_storage.webdav_provider.requests")
    def test_jianguoyun_alias(self, mock_requests: MagicMock) -> None:
        from apps.core.cloud_storage.webdav_provider import JianguoyunProvider, WebDAVProvider

        assert JianguoyunProvider is WebDAVProvider


# ============================================================
# OneDriveProvider
# ============================================================


class TestOneDriveProvider:
    """测试 OneDriveProvider"""

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_init(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        provider = OneDriveProvider(access_token="tok123", root_path="/docs")  # allowlist secret
        assert provider._token == "tok123"
        assert provider._root == "docs"
        assert "Bearer tok123" in provider._headers["Authorization"]

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_item_path(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        provider = OneDriveProvider(access_token="t", root_path="/myroot")
        assert provider._item_path("file.txt") == "myroot/file.txt"
        assert provider._item_path("") == "myroot"

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_item_url(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        provider = OneDriveProvider(access_token="t", root_path="/docs")
        url = provider._item_url("report.pdf")
        assert "graph.microsoft.com" in url
        assert "docs/report.pdf" in url

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_exists_true(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get.return_value = MagicMock(status_code=200)

        provider = OneDriveProvider(access_token="t")
        assert provider.exists("file.txt") is True

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_exists_false(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get.return_value = MagicMock(status_code=404)

        provider = OneDriveProvider(access_token="t")
        assert provider.exists("missing.txt") is False

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_delete_file_ok(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.delete.return_value = MagicMock(status_code=204)

        provider = OneDriveProvider(access_token="t")
        provider.delete_file("file.txt")  # 不抛异常

    @patch("apps.core.cloud_storage.onedrive_provider.httpx.Client")
    def test_children_url_root(self, mock_client_cls: MagicMock) -> None:
        from apps.core.cloud_storage.onedrive_provider import OneDriveProvider

        provider = OneDriveProvider(access_token="t", root_path="")
        url = provider._children_url("")
        assert "children" in url


class TestOAuthTokenManager:
    """测试 OAuthTokenManager"""

    def test_tenant_id_default(self) -> None:
        from apps.core.cloud_storage.onedrive_provider import OAuthTokenManager

        account = SimpleNamespace()
        mgr = OAuthTokenManager(account)
        assert mgr._tenant_id() == "consumers"

    def test_tenant_id_custom(self) -> None:
        from apps.core.cloud_storage.onedrive_provider import OAuthTokenManager

        account = SimpleNamespace(onedrive_tenant_id="abc-123")
        mgr = OAuthTokenManager(account)
        assert mgr._tenant_id() == "abc-123"

    def test_get_valid_token_raises_when_no_tokens(self) -> None:
        from apps.core.cloud_storage.onedrive_provider import OAuthTokenManager

        account = SimpleNamespace(
            get_decrypted_onedrive_access_token=MagicMock(return_value=None),
            onedrive_token_expires_at=None,
            get_decrypted_onedrive_refresh_token=MagicMock(return_value=None),
        )
        mgr = OAuthTokenManager(account)
        with pytest.raises(RuntimeError, match="未授权"):
            mgr.get_valid_token()

    def test_get_valid_token_valid_token(self) -> None:
        from datetime import UTC, datetime, timedelta

        from apps.core.cloud_storage.onedrive_provider import OAuthTokenManager

        account = SimpleNamespace(
            get_decrypted_onedrive_access_token=MagicMock(return_value="valid_token"),
            onedrive_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        mgr = OAuthTokenManager(account)
        assert mgr.get_valid_token() == "valid_token"


# ============================================================
# DropboxProvider
# ============================================================


class TestDropboxOAuthTokenManager:
    """测试 DropboxOAuthTokenManager"""

    def test_get_valid_token_raises_when_no_tokens(self) -> None:
        from apps.core.cloud_storage.dropbox_provider import DropboxOAuthTokenManager

        account = SimpleNamespace(
            get_decrypted_dropbox_access_token=MagicMock(return_value=None),
            dropbox_token_expires_at=None,
            get_decrypted_dropbox_refresh_token=MagicMock(return_value=None),
        )
        mgr = DropboxOAuthTokenManager(account)
        with pytest.raises(RuntimeError, match="未授权"):
            mgr.get_valid_token()

    def test_get_valid_token_valid(self) -> None:
        from datetime import UTC, datetime, timedelta

        from apps.core.cloud_storage.dropbox_provider import DropboxOAuthTokenManager

        account = SimpleNamespace(
            get_decrypted_dropbox_access_token=MagicMock(return_value="valid_token"),
            dropbox_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        mgr = DropboxOAuthTokenManager(account)
        assert mgr.get_valid_token() == "valid_token"


# ============================================================
# DropboxProvider path building
# ============================================================


class TestDropboxProviderPath:
    """测试 DropboxProvider 路径构建"""

    def test_full_path_concept(self) -> None:
        """测试 Dropbox 路径构建逻辑（不依赖 dropbox SDK）"""
        from apps.core.cloud_storage.dropbox_provider import DropboxProvider

        import types
        # 直接测试 _full_path 方法的逻辑
        mock_provider = types.SimpleNamespace()
        mock_provider._root = "myroot"
        result = DropboxProvider._full_path(mock_provider, "")
        assert result == "/myroot"
        result = DropboxProvider._full_path(mock_provider, "sub/file.txt")
        assert result == "/myroot/sub/file.txt"


# ============================================================
# S3Provider path building
# ============================================================


class TestS3ProviderPath:
    """测试 S3Provider 路径构建"""

    def test_full_key_concept(self) -> None:
        """测试 S3 key 构建逻辑（不依赖 boto3）"""
        from apps.core.cloud_storage.s3_provider import S3Provider

        # 直接测试 _full_key 的逻辑，跳过 boto3 初始化
        # _full_key: clean = path.strip("/"); parts = [p for p in (self._root, clean) if p]; return "/".join(parts)
        # 通过创建 mock 对象来测试
        import types

        mock_provider = types.SimpleNamespace()
        mock_provider._root = "prefix"
        result = S3Provider._full_key(mock_provider, "")
        assert result == "prefix"

        result = S3Provider._full_key(mock_provider, "file.txt")
        assert result == "prefix/file.txt"


# ============================================================
# null_provider.py
# ============================================================


class TestNullProvider:
    """测试 NullProvider - 所有操作应抛出 RuntimeError"""

    def test_list_directory_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.list_directory("/")

    def test_read_file_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError):
            provider.read_file("/file")

    def test_write_file_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError):
            provider.write_file("/file", b"data")

    def test_exists_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError):
            provider.exists("/anything")

    def test_is_dir_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError):
            provider.is_dir("/anything")

    def test_delete_file_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError):
            provider.delete_file("/file")

    def test_get_file_info_raises(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider()
        with pytest.raises(RuntimeError):
            provider.get_file_info("/file")

    def test_custom_reason(self) -> None:
        from apps.core.cloud_storage.null_provider import NullProvider

        provider = NullProvider(reason="自定义错误信息")
        with pytest.raises(RuntimeError, match="自定义错误信息"):
            provider.exists("/x")


# ============================================================
# local.py
# ============================================================


class TestLocalProvider:
    """测试 LocalProvider"""

    def test_init(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        assert provider._root.exists()

    def test_list_directory_empty(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        result = provider.list_directory(".")
        assert result == []

    def test_write_and_read_file(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        provider.write_file("test.txt", b"hello world")
        assert provider.read_file("test.txt") == b"hello world"

    def test_exists_true(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        provider.write_file("file.txt", b"data")
        assert provider.exists("file.txt") is True

    def test_exists_false(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        assert provider.exists("nonexistent.txt") is False

    def test_mkdir(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        provider.mkdir("newdir")
        assert provider.is_dir("newdir") is True

    def test_delete_file(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        provider.write_file("file.txt", b"data")
        provider.delete_file("file.txt")
        assert provider.exists("file.txt") is False

    def test_get_file_info(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        provider.write_file("file.txt", b"hello")
        info = provider.get_file_info("file.txt")
        assert info is not None
        assert info.name == "file.txt"
        assert info.size == 5
        assert info.is_dir is False

    def test_walk(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        provider.mkdir("subdir")
        provider.write_file("subdir/file.txt", b"data")
        walk_results = list(provider.walk("."))
        assert len(walk_results) >= 1

    def test_path_traversal_prevention(self, tmp_path: object) -> None:
        from apps.core.cloud_storage.local import LocalProvider

        provider = LocalProvider(root=str(tmp_path))  # type: ignore[arg-type]
        with pytest.raises(OSError, match="路径逃逸"):
            provider.list_directory("../../etc")
