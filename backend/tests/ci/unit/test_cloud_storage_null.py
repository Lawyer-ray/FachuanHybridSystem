"""NullProvider 单元测试."""

from __future__ import annotations

import pytest

from apps.core.cloud_storage.null_provider import NullProvider


class TestNullProvider:
    """Verify NullProvider raises RuntimeError on every operation."""

    @pytest.fixture
    def provider(self) -> NullProvider:
        return NullProvider(reason="测试：存储账号未配置")

    def test_list_directory_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.list_directory("/")

    def test_read_file_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.read_file("test.txt")

    def test_write_file_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.write_file("test.txt", b"data")

    def test_mkdir_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.mkdir("dir")

    def test_exists_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.exists("test.txt")

    def test_is_dir_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.is_dir("dir")

    def test_delete_file_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.delete_file("test.txt")

    def test_get_file_info_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.get_file_info("test.txt")

    def test_walk_raises(self, provider: NullProvider):
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            list(provider.walk("/"))

    def test_custom_reason(self):
        provider = NullProvider(reason="OneDrive 授权已过期")
        with pytest.raises(RuntimeError, match="OneDrive 授权已过期"):
            provider.list_directory("/")

    def test_default_reason(self):
        provider = NullProvider()
        with pytest.raises(RuntimeError, match="存储账号未配置或已禁用"):
            provider.list_directory("/")
