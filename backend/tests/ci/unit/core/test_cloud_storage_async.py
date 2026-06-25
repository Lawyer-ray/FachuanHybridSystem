"""Tests for LocalProvider.aread_file async method."""

from __future__ import annotations

import pytest
from pathlib import Path

from apps.core.cloud_storage.local import LocalProvider


@pytest.mark.asyncio
class TestLocalProviderAsync:
    async def test_aread_file_returns_bytes(self, tmp_path):
        test_file = tmp_path / "test_async.txt"
        test_file.write_bytes(b"hello async world")
        provider = LocalProvider(root=str(tmp_path))
        result = await provider.aread_file("test_async.txt")
        assert result == b"hello async world"

    async def test_aread_file_not_found(self, tmp_path):
        provider = LocalProvider(root=str(tmp_path))
        with pytest.raises((FileNotFoundError, OSError)):
            await provider.aread_file("nonexistent_file_xyz.txt")

    async def test_aread_file_binary_content(self, tmp_path):
        test_file = tmp_path / "binary.dat"
        binary_data = bytes(range(256))
        test_file.write_bytes(binary_data)
        provider = LocalProvider(root=str(tmp_path))
        result = await provider.aread_file("binary.dat")
        assert result == binary_data
