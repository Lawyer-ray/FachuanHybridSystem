"""Cloud storage factory 单元测试."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.core.cloud_storage.factory import create_provider_for_binding
from apps.core.cloud_storage.local import LocalProvider
from apps.core.cloud_storage.null_provider import NullProvider


class TestFactoryNullProviderFallback:
    """Verify factory returns NullProvider when storage account is missing."""

    def test_webdav_without_account_returns_null(self):
        binding = SimpleNamespace(storage_type="webdav", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_onedrive_without_account_returns_null(self):
        binding = SimpleNamespace(storage_type="onedrive", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_s3_without_account_returns_null(self):
        binding = SimpleNamespace(storage_type="s3", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_google_drive_without_account_returns_null(self):
        binding = SimpleNamespace(storage_type="google_drive", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_dropbox_without_account_returns_null(self):
        binding = SimpleNamespace(storage_type="dropbox", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_unknown_type_returns_null(self):
        binding = SimpleNamespace(storage_type="ftp", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_local_type_returns_local_provider(self):
        binding = SimpleNamespace(storage_type="local", storage_account=None)
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, LocalProvider)

    def test_webdav_null_provider_raises_on_use(self):
        binding = SimpleNamespace(storage_type="webdav", storage_account=None)
        provider = create_provider_for_binding(binding)
        with pytest.raises(RuntimeError, match="WebDAV 账号未配置"):
            provider.list_directory("/")

    def test_onedrive_null_provider_raises_on_use(self):
        binding = SimpleNamespace(storage_type="onedrive", storage_account=None)
        provider = create_provider_for_binding(binding)
        with pytest.raises(RuntimeError, match="OneDrive 账号未配置"):
            provider.list_directory("/")

    def test_s3_null_provider_raises_on_use(self):
        binding = SimpleNamespace(storage_type="s3", storage_account=None)
        provider = create_provider_for_binding(binding)
        with pytest.raises(RuntimeError, match="S3 账号未配置"):
            provider.list_directory("/")

    def test_google_drive_null_provider_raises_on_use(self):
        binding = SimpleNamespace(storage_type="google_drive", storage_account=None)
        provider = create_provider_for_binding(binding)
        with pytest.raises(RuntimeError, match="Google Drive 账号未配置"):
            provider.list_directory("/")

    def test_dropbox_null_provider_raises_on_use(self):
        binding = SimpleNamespace(storage_type="dropbox", storage_account=None)
        provider = create_provider_for_binding(binding)
        with pytest.raises(RuntimeError, match="Dropbox 账号未配置"):
            provider.list_directory("/")

    def test_unknown_type_null_provider_raises_on_use(self):
        binding = SimpleNamespace(storage_type="ftp", storage_account=None)
        provider = create_provider_for_binding(binding)
        with pytest.raises(RuntimeError, match="不支持的存储类型: ftp"):
            provider.list_directory("/")
