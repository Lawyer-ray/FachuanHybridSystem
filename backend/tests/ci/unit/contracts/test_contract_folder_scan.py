"""Tests for ContractFolderScanService - pure logic methods."""

import re
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from apps.contracts.services.contract.integrations.folder_scan_service import (
    ContractFolderScanService,
    _normalize_docx_name,
)


class TestNormalizeScanSubfolder:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_empty(self):
        assert self.service._normalize_scan_subfolder("") == ""

    def test_none(self):
        assert self.service._normalize_scan_subfolder(None) == ""

    def test_relative_path(self):
        assert self.service._normalize_scan_subfolder("subfolder") == "subfolder"

    def test_backslash_normalized(self):
        assert self.service._normalize_scan_subfolder("a\\b") == "a/b"

    def test_absolute_raises(self):
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("/absolute")

    def test_tilde_raises(self):
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("~/path")

    def test_dotdot_raises(self):
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            self.service._normalize_scan_subfolder("../escape")

    def test_dot_segments_removed(self):
        assert self.service._normalize_scan_subfolder("a/./b") == "a/b"


class TestIsWithinRoot:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_within(self):
        assert self.service._is_within_root(Path("/a/b"), Path("/a/b/c")) is True

    def test_outside(self):
        assert self.service._is_within_root(Path("/a/b"), Path("/x/y")) is False


class TestExtractScanSubfolder:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_with_scope(self):
        payload = {"scan_scope": {"scan_subfolder": "sub"}}
        assert self.service._extract_scan_subfolder(payload) == "sub"

    def test_empty(self):
        assert self.service._extract_scan_subfolder({}) == ""

    def test_none(self):
        assert self.service._extract_scan_subfolder(None) == ""


class TestBuildStatusPayload:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_basic_payload(self):
        session = MagicMock()
        session.id = "test-id"
        session.status = "completed"
        session.progress = 100
        session.current_file = ""
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 5, "deduped_files": 4, "classified_files": 3},
            "candidates": [],
            "archive_category": "litigation",
            "archive_item_options": [],
            "work_log_suggestions": [],
        }
        result = self.service.build_status_payload(session=session)
        assert result["session_id"] == "test-id"
        assert result["status"] == "completed"
        assert result["archive_category"] == "litigation"

    def test_empty_payload(self):
        session = MagicMock()
        session.id = "id"
        session.status = "pending"
        session.progress = 0
        session.current_file = ""
        session.error_message = ""
        session.result_payload = None
        result = self.service.build_status_payload(session=session)
        assert result["summary"]["total_files"] == 0


class TestMakeProviderForBinding:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_local_returns_none(self):
        binding = MagicMock()
        binding.storage_type = "local"
        assert self.service._make_provider_for_binding(binding) is None


class TestResolveScanScope:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_local_root_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.service._resolve_scan_scope(tmpdir, "")
            assert result["scan_subfolder"] == ""

    def test_local_subfolder(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "sub").mkdir()
            result = self.service._resolve_scan_scope(tmpdir, "sub")
            assert result["scan_subfolder"] == "sub"

    def test_traversal_blocked(self):
        import tempfile
        from apps.core.exceptions import ValidationException
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValidationException, match="路径非法"):
                self.service._resolve_scan_scope(tmpdir, "../escape")

    def test_not_exist_raises(self):
        import tempfile
        from apps.core.exceptions import ValidationException
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValidationException):
                self.service._resolve_scan_scope(tmpdir, "nonexistent")


class TestRelativePathStr:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_relative_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "sub").mkdir()
            (root / "sub" / "file.txt").touch()
            result = self.service._relative_path_str(
                source_path=str(root / "sub" / "file.txt"),
                scan_root=root,
            )
            assert result == "sub"

    def test_file_in_root(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "file.txt").touch()
            result = self.service._relative_path_str(
                source_path=str(root / "file.txt"),
                scan_root=root,
            )
            assert result == ""


class TestNormalizeDocxName:
    def test_basic(self):
        assert _normalize_docx_name("Test File.DOCX") == "testfile.docx"

    def test_whitespace(self):
        assert _normalize_docx_name("  file  name  ") == "filename"

    def test_empty(self):
        assert _normalize_docx_name("") == ""

    def test_none(self):
        assert _normalize_docx_name(None) == ""


class TestEnsureContractExists:
    @patch("apps.contracts.services.contract.integrations.folder_scan_service.Contract")
    def test_raises_for_missing(self, mock_contract):
        from apps.core.exceptions import NotFoundError
        mock_contract.objects.filter.return_value.exists.return_value = False
        service = ContractFolderScanService(scan_service=MagicMock())
        with pytest.raises(NotFoundError):
            service._ensure_contract_exists(999999)


class TestMakeProviderForBindingCloud:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    @patch("apps.core.cloud_storage.factory.create_provider_for_binding")
    def test_cloud_returns_provider(self, mock_create):
        binding = MagicMock()
        binding.storage_type = "webdav"
        mock_provider = MagicMock()
        mock_create.return_value = mock_provider

        provider = self.service._make_provider_for_binding(binding)
        assert provider is mock_provider


class TestPostProcessCandidates:
    def setup_method(self):
        self.service = ContractFolderScanService(scan_service=MagicMock())

    def test_insurance_files_deselected(self):
        candidates = [
            {"source_path": "/path/保单.pdf", "filename": "保单.pdf", "suggested_category": "other"},
            {"source_path": "/path/保函.pdf", "filename": "保函.pdf", "suggested_category": "other"},
            {"source_path": "/path/normal.pdf", "filename": "normal.pdf", "suggested_category": "other"},
        ]
        result = self.service._post_process_candidates(
            candidates=candidates,
            archive_category="litigation",
            scan_folder="/path",
            contract_id=0,
        )
        # Insurance files should be deselected
        insurance_files = [c for c in result if "保" in c.get("filename", "")]
        for f in insurance_files:
            assert f.get("selected") is False

    def test_empty_candidates(self):
        result = self.service._post_process_candidates(
            candidates=[],
            archive_category="litigation",
            scan_folder="/path",
        )
        assert result == []
