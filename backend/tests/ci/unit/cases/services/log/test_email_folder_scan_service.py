"""Tests for cases.services.log.email_folder_scan_service."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.log.email_folder_scan_service import EmailFolderScanService
from apps.core.exceptions import NotFoundError, ValidationException


def _make_service(**overrides: Any) -> EmailFolderScanService:
    return EmailFolderScanService(
        mutation_service=overrides.get("mutation_service", MagicMock()),
        query_service=overrides.get("query_service", MagicMock()),
    )


class TestEmailFolderScanServiceInit:
    def test_lazy_init(self):
        svc = EmailFolderScanService()
        with patch("apps.cases.services.log.email_folder_scan_service.CaseLogMutationService") as M:
            M.return_value = MagicMock()
            assert svc.mutation_service is not None

    def test_lazy_query_service(self):
        svc = EmailFolderScanService()
        with patch("apps.cases.services.log.email_folder_scan_service.CaseLogQueryService") as M:
            M.return_value = MagicMock()
            assert svc.query_service is not None


class TestEmailFolderScanServiceResolveSubfolder:
    def test_empty_subfolder_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="子文件夹路径不能为空"):
            svc._resolve_subfolder(Path("/root"), "")

    def test_absolute_path_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="子文件夹必须使用相对路径"):
            svc._resolve_subfolder(Path("/root"), "/absolute")

    def test_tilde_path_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="子文件夹必须使用相对路径"):
            svc._resolve_subfolder(Path("/root"), "~/hack")

    def test_dotdot_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="子文件夹路径非法"):
            svc._resolve_subfolder(Path("/root"), "../escape")

    def test_hidden_dir_raises(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="子文件夹路径非法"):
            svc._resolve_subfolder(Path("/root"), ".hidden")

    def test_cloud_provider_joins_paths(self):
        svc = _make_service()
        provider = MagicMock()
        result = svc._resolve_subfolder("/root", "subdir", provider=provider)
        assert result == "/root/subdir"


class TestEmailFolderScanServiceBuildLogContent:
    def test_date_prefix_stripped(self):
        svc = _make_service()
        assert svc._build_log_content("2024.01.15-讨论记录") == "讨论记录"

    def test_no_date_keeps_original(self):
        svc = _make_service()
        assert svc._build_log_content("讨论记录") == "讨论记录"

    def test_only_date_returns_original(self):
        svc = _make_service()
        assert svc._build_log_content("2024.1.5") == "2024.1.5"


class TestEmailFolderScanServiceCollectAllowedFiles:
    def test_cloud_collect(self):
        svc = _make_service()
        provider = MagicMock()
        f = MagicMock()
        f.is_dir = False
        f.name = "test.pdf"
        f.size = 100
        provider.walk.return_value = [("/dir", [], [f])]
        with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_ALLOWED_EXTENSIONS", {".pdf"}):
            with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_MAX_FILE_SIZE", 10000):
                result = svc._collect_allowed_files_cloud("/dir", provider)
                assert len(result) >= 1

    def test_cloud_collect_skips_hidden(self):
        svc = _make_service()
        provider = MagicMock()
        f = MagicMock()
        f.is_dir = False
        f.name = ".hidden.pdf"
        f.size = 100
        provider.walk.return_value = [("/dir", [], [f])]
        with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_ALLOWED_EXTENSIONS", {".pdf"}):
            with patch("apps.cases.services.log.email_folder_scan_service.CASE_LOG_MAX_FILE_SIZE", 10000):
                result = svc._collect_allowed_files_cloud("/dir", provider)
                assert result == []


class TestEmailFolderScanServiceCollectSubdirs:
    def test_cloud_collect_subdirs(self):
        svc = _make_service()
        provider = MagicMock()
        child = MagicMock()
        child.is_dir = True
        child.name = "subdir"
        provider.list_directory.return_value = [child]
        with patch.object(svc, "_collect_allowed_files_cloud", return_value=["/root/subdir/file.pdf"]):
            result = svc._collect_subdirs_cloud("/root", provider)
            assert len(result) == 1

    def test_cloud_collect_subdirs_skips_hidden(self):
        svc = _make_service()
        provider = MagicMock()
        child = MagicMock()
        child.is_dir = True
        child.name = ".hidden"
        provider.list_directory.return_value = [child]
        result = svc._collect_subdirs_cloud("/root", provider)
        assert result == []


class TestEmailFolderScanServiceGetBoundCaseRoot:
    @patch("apps.cases.services.log.email_folder_scan_service.CaseFolderBinding")
    def test_no_binding_returns_none(self, MockBinding):
        svc = _make_service()
        MockBinding.objects.filter.return_value.first.return_value = None
        root, provider = svc._get_bound_case_root(1)
        assert root is None
        assert provider is None

    @patch("apps.cases.services.log.email_folder_scan_service.CaseFolderBinding")
    def test_empty_path_returns_none(self, MockBinding):
        svc = _make_service()
        binding = MagicMock()
        binding.resolved_folder_path = ""
        MockBinding.objects.filter.return_value.first.return_value = binding
        root, provider = svc._get_bound_case_root(1)
        assert root is None


class TestEmailFolderScanServiceImportEmailFolder:
    @patch.object(EmailFolderScanService, "_get_bound_case_root", return_value=(None, None))
    def test_no_root_raises(self, mock_root):
        svc = _make_service()
        with pytest.raises(NotFoundError, match="案件未绑定可用文件夹"):
            svc.import_email_folder(case_id=1, subfolder="test")

    @patch.object(EmailFolderScanService, "_get_bound_case_root")
    def test_nonexistent_subfolder_raises(self, mock_root):
        svc = _make_service()
        mock_root.return_value = (Path("/nonexistent"), None)
        with pytest.raises(ValidationException):
            svc.import_email_folder(case_id=1, subfolder="test")


class TestEmailFolderScanServiceUploadFileAsAttachment:
    def test_upload_failure_returns_none(self):
        svc = _make_service()
        log = MagicMock()
        log.id = 1
        with patch("builtins.open", side_effect=IOError("disk error")):
            result = svc._upload_file_as_attachment(log, Path("/fake/file.pdf"))
            assert result is None
