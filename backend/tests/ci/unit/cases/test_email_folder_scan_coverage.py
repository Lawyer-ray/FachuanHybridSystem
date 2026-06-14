"""补充覆盖测试: cases/services/log/email_folder_scan_service.py (36 missing)

覆盖: _resolve_subfolder, _build_log_content, _collect_subdirs, _collect_allowed_files 等。
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService


# ── _build_log_content ────────────────────────────────────────────


class TestBuildLogContent:
    def test_strips_date_prefix(self) -> None:
        svc = EmailFolderScanService()
        result = svc._build_log_content("2024-03-20-原告方回复")
        assert result == "原告方回复"

    def test_strips_date_with_dots(self) -> None:
        svc = EmailFolderScanService()
        result = svc._build_log_content("2024.3.20-被告方答辩")
        assert result == "被告方答辩"

    def test_strips_date_with_spaces(self) -> None:
        svc = EmailFolderScanService()
        result = svc._build_log_content("2024-03-20 开庭通知")
        assert result == "开庭通知"

    def test_no_date_returns_original(self) -> None:
        svc = EmailFolderScanService()
        result = svc._build_log_content("没有日期的文件夹")
        assert result == "没有日期的文件夹"

    def test_empty_string(self) -> None:
        svc = EmailFolderScanService()
        result = svc._build_log_content("")
        assert result == ""


# ── _resolve_subfolder ────────────────────────────────────────────


class TestResolveSubfolder:
    def test_valid_relative_path(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        result = svc._resolve_subfolder(tmp_path, "emails/2024-03")
        assert isinstance(result, Path)
        assert str(result).endswith("emails/2024-03")

    def test_empty_subfolder_raises(self) -> None:
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException, match="子文件夹路径不能为空"):
            svc._resolve_subfolder(Path("/tmp"), "")

    def test_absolute_path_raises(self) -> None:
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._resolve_subfolder(Path("/tmp"), "/etc/passwd")

    def test_tilde_path_raises(self) -> None:
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException, match="相对路径"):
            svc._resolve_subfolder(Path("/tmp"), "~/secret")

    def test_dotdot_raises(self) -> None:
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException, match="非法"):
            svc._resolve_subfolder(Path("/tmp"), "../escape")

    def test_hidden_folder_raises(self) -> None:
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException, match="非法"):
            svc._resolve_subfolder(Path("/tmp"), ".hidden")

    def test_dots_only_raises(self) -> None:
        svc = EmailFolderScanService()
        with pytest.raises(ValidationException, match="不能为空"):
            svc._resolve_subfolder(Path("/tmp"), "./.")

    def test_cloud_provider(self) -> None:
        svc = EmailFolderScanService()
        provider = MagicMock()
        result = svc._resolve_subfolder("/cloud/root", "subfolder", provider=provider)
        assert result == "/cloud/root/subfolder"

    def test_path_escape_rejected(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        # Create a path that would escape via resolve()
        with pytest.raises(ValidationException):
            svc._resolve_subfolder(tmp_path, "subdir/../../escape")

    def test_backslash_normalized(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        result = svc._resolve_subfolder(tmp_path, "emails\\2024-03")
        assert isinstance(result, Path)


# ── _collect_allowed_files ────────────────────────────────────────


class TestCollectAllowedFiles:
    def test_collects_valid_files(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        # Create test files
        (tmp_path / "doc.pdf").write_bytes(b"pdf")
        (tmp_path / "image.jpg").write_bytes(b"jpg")
        (tmp_path / "script.py").write_bytes(b"py")  # not allowed
        (tmp_path / ".hidden.txt").write_text("hidden")

        with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_ALLOWED_EXTENSIONS", {".pdf", ".jpg"}), \
             patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_MAX_FILE_SIZE", 1024):
            result = svc._collect_allowed_files(tmp_path)
            names = [f.name for f in result]
            assert "doc.pdf" in names
            assert "image.jpg" in names
            assert "script.py" not in names

    def test_empty_folder(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        result = svc._collect_allowed_files(tmp_path)
        assert result == []

    def test_file_too_large_skipped(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        (tmp_path / "big.pdf").write_bytes(b"x" * 2000)

        with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_ALLOWED_EXTENSIONS", {".pdf"}), \
             patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_MAX_FILE_SIZE", 100):
            result = svc._collect_allowed_files(tmp_path)
            assert len(result) == 0


# ── _collect_subdirs ──────────────────────────────────────────────


class TestCollectSubdirs:
    def test_collects_subdirs_with_valid_files(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        sub1 = tmp_path / "2024-01-01_emails"
        sub1.mkdir()
        (sub1 / "doc.pdf").write_bytes(b"pdf")

        sub2 = tmp_path / ".hidden"
        sub2.mkdir()

        with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_ALLOWED_EXTENSIONS", {".pdf"}), \
             patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_MAX_FILE_SIZE", 1024):
            result = svc._collect_subdirs(tmp_path)
            assert len(result) == 1
            assert result[0][0].name == "2024-01-01_emails"

    def test_empty_folder(self, tmp_path: Path) -> None:
        svc = EmailFolderScanService()
        result = svc._collect_subdirs(tmp_path)
        assert result == []

    def test_cloud_provider_delegates(self) -> None:
        svc = EmailFolderScanService()
        provider = MagicMock()
        with patch.object(svc, "_collect_subdirs_cloud", return_value=[("/cloud/sub", [])]) as mock_cloud:
            result = svc._collect_subdirs("/cloud/folder", provider=provider)
            mock_cloud.assert_called_once_with("/cloud/folder", provider)


# ── Lazy properties ───────────────────────────────────────────────


class TestLazyProperties:
    def test_mutation_service_lazy(self) -> None:
        svc = EmailFolderScanService()
        assert svc._mutation_service is None
        ms = svc.mutation_service
        assert ms is not None
        assert svc.mutation_service is ms

    def test_query_service_lazy(self) -> None:
        svc = EmailFolderScanService()
        assert svc._query_service is None
        qs = svc.query_service
        assert qs is not None
        assert svc.query_service is qs
