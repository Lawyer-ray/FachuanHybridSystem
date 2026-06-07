"""Coverage tests for core.tasking.cleanup_tasks and core.cloud_storage.scanner_adapter."""

from unittest.mock import MagicMock, patch
from pathlib import PurePosixPath

import pytest


class TestCleanupTasks:
    @patch("apps.core.tasking.cleanup_tasks.settings")
    def test_cleanup_temp_files_no_dir(self, mock_settings):
        import tempfile, os
        tmp = tempfile.mkdtemp()
        mock_settings.MEDIA_ROOT = tmp
        from apps.core.tasking.cleanup_tasks import cleanup_temp_files
        result = cleanup_temp_files()
        assert result["skipped"] is True

    @patch("apps.core.tasking.cleanup_tasks.settings")
    def test_cleanup_export_files_no_dir(self, mock_settings):
        import tempfile
        tmp = tempfile.mkdtemp()
        mock_settings.MEDIA_ROOT = tmp
        from apps.core.tasking.cleanup_tasks import cleanup_export_files
        result = cleanup_export_files()
        assert result["skipped"] is True

    @patch("apps.core.tasking.cleanup_tasks.settings")
    @patch("apps.core.tasking.cleanup_tasks.os")
    def test_check_disk_space(self, mock_os, mock_settings):
        import tempfile
        tmp = tempfile.mkdtemp()
        mock_settings.MEDIA_ROOT = tmp
        mock_stat = MagicMock()
        mock_stat.f_blocks = 1000
        mock_stat.f_frsize = 4096
        mock_stat.f_bavail = 500
        mock_os.statvfs.return_value = mock_stat
        from apps.core.tasking.cleanup_tasks import check_disk_space
        result = check_disk_space()
        assert "status" in result

    @patch("apps.core.tasking.cleanup_tasks.settings")
    @patch("apps.core.tasking.cleanup_tasks.os")
    def test_check_disk_space_error(self, mock_os, mock_settings):
        mock_settings.MEDIA_ROOT = "/nonexistent"
        mock_os.statvfs.side_effect = OSError("fail")
        from apps.core.tasking.cleanup_tasks import check_disk_space
        result = check_disk_space()
        assert result["status"] == "error"


class TestScannedFile:
    def test_properties(self):
        from apps.core.cloud_storage.scanner_adapter import ScannedFile, _FakeStat

        info = MagicMock()
        info.name = "doc.pdf"
        info.path = "/root/doc.pdf"
        info.size = 1024
        info.modified_at = 1234567890.0
        info.is_dir = False

        sf = ScannedFile(_info=info, _root="/root")
        assert sf.name == "doc.pdf"
        assert sf.stem == "doc"
        assert sf.suffix == ".pdf"
        assert sf.as_posix == "/root/doc.pdf"
        assert sf.stat.size == 1024

    def test_relative_to(self):
        from apps.core.cloud_storage.scanner_adapter import ScannedFile

        info = MagicMock()
        info.name = "doc.pdf"
        info.path = "/root/sub/doc.pdf"
        sf = ScannedFile(_info=info, _root="/root")
        rel = sf.relative_to("/root")
        assert str(rel) == "sub/doc.pdf"


class TestFakeStat:
    def test_attributes(self):
        from apps.core.cloud_storage.scanner_adapter import _FakeStat

        stat = _FakeStat(size=512, mtime=100.0)
        assert stat.size == 512
        assert stat.mtime == 100.0


class TestFakeParent:
    def test_name(self):
        from apps.core.cloud_storage.scanner_adapter import _FakeParent

        parent = _FakeParent(path="/root/sub/file.txt")
        assert parent.name == "sub"

    def test_relative_to(self):
        from apps.core.cloud_storage.scanner_adapter import _FakeParent

        parent = _FakeParent(path="/root/sub/file.txt")
        result = parent.relative_to("/root")
        assert str(result) == "sub"


class TestCloudFolderScanner:
    def test_collect_pdf_files(self):
        from apps.core.cloud_storage.scanner_adapter import CloudFolderScanner

        mock_provider = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_file.is_dir = False
        mock_file.size = 1024
        mock_file.modified_at = 100.0
        mock_provider.walk.return_value = [("/root", [], [mock_file])]

        scanner = CloudFolderScanner(mock_provider, "/root")
        results = scanner.collect_pdf_files()
        assert len(results) == 1

    def test_read_file_bytes(self):
        from apps.core.cloud_storage.scanner_adapter import CloudFolderScanner, ScannedFile

        mock_provider = MagicMock()
        mock_provider.read_file.return_value = b"pdf content"

        scanner = CloudFolderScanner(mock_provider, "/root")
        info = MagicMock()
        info.path = "test.pdf"
        scanned = ScannedFile(_info=info, _root="/root")
        result = scanner.read_file_bytes(scanned)
        assert result == b"pdf content"
