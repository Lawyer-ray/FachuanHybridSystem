"""Phase 1 cloud storage import pipeline unit tests."""

from __future__ import annotations

from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.services.contract.integrations.file_hash_utils import (
    compute_file_hash,
    compute_file_hash_from_bytes,
)


class TestComputeFileHashFromBytes:
    def test_empty_bytes(self):
        result = compute_file_hash_from_bytes(b"")
        assert result == hashlib_sha256(b"")

    def test_normal_bytes(self):
        data = b"hello world"
        result = compute_file_hash_from_bytes(data)
        assert result == hashlib_sha256(data)
        assert len(result) == 64  # SHA-256 hex digest

    def test_large_bytes(self):
        data = b"x" * 1_000_000
        result = compute_file_hash_from_bytes(data)
        assert len(result) == 64

    def test_matches_file_hash(self, tmp_path):
        """Verify bytes hash matches file hash for same content."""
        data = b"test content for hash comparison"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        assert compute_file_hash_from_bytes(data) == compute_file_hash(f)

    def test_none_returns_empty(self):
        result = compute_file_hash_from_bytes(None)  # type: ignore[arg-type]
        assert result == ""


def hashlib_sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _make_cloud_file(name: str, path: str, size: int = 100, is_dir: bool = False, modified_at: float = 1000.0):
    """Helper to create mock CloudFileInfo-like objects."""
    return SimpleNamespace(name=name, path=path, is_dir=is_dir, size=size, modified_at=modified_at)


def _make_mock_provider(files: list | None = None, dirs: list | None = None):
    """Create a mock CloudStorageProvider."""
    provider = MagicMock()
    all_items = []
    if dirs:
        all_items.extend(dirs)
    if files:
        all_items.extend(files)
    provider.list_directory.return_value = all_items
    provider.walk.return_value = [("/", [d.name for d in (dirs or [])], files or [])]
    provider.read_file.return_value = b"mock file content"
    provider.exists.return_value = True
    provider.is_dir.return_value = True
    return provider


class TestCollectDocxFilesCloud:
    """Test the cloud variant of _collect_docx_files."""

    def _get_service(self):
        from unittest.mock import MagicMock

        from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
        return CandidatePostProcessor(scan_service=MagicMock())

    def test_returns_empty_for_litigation(self):
        service = self._get_service()
        result = service._collect_docx_files("/", "litigation", storage_provider=_make_mock_provider())
        assert result == []

    def test_collects_revision_docx(self):
        service = self._get_service()
        provider = _make_mock_provider(
            files=[
                _make_cloud_file("合同修订版V2.docx", "/docs/合同修订版V2.docx"),
                _make_cloud_file("普通文件.pdf", "/docs/普通文件.pdf"),
                _make_cloud_file("批注版-修改稿.docx", "/docs/批注版-修改稿.docx"),
            ]
        )
        result = service._collect_docx_files_cloud("/docs", provider, ("修订版", "批注版", "律师修订"))
        assert len(result) == 2
        names = {r["filename"] for r in result}
        assert "合同修订版V2.docx" in names
        assert "批注版-修改稿.docx" in names
        assert "普通文件.pdf" not in names

    def test_deduplicates_by_name(self):
        service = self._get_service()
        provider = _make_mock_provider(
            files=[
                _make_cloud_file("合同修订版.docx", "/docs/合同修订版.docx", size=100, modified_at=2000.0),
                _make_cloud_file("合同修订版.docx", "/docs/sub/合同修订版.docx", size=200, modified_at=3000.0),
            ]
        )
        result = service._collect_docx_files_cloud("/docs", provider, ("修订版",))
        assert len(result) == 1  # deduplicated

    def test_empty_folder(self):
        service = self._get_service()
        provider = _make_mock_provider(files=[])
        result = service._collect_docx_files_cloud("/docs", provider, ("修订版",))
        assert result == []


class TestConvertDocxToTempPdfFromBytes:
    """Test the bytes-based docx→PDF conversion."""

    def _get_service(self):
        from apps.contracts.services.contract.integrations._import_pipeline import ImportPipeline
        return ImportPipeline()

    @patch("apps.contracts.services.contract.integrations._import_pipeline.ImportPipeline._convert_docx_to_temp_pdf_from_bytes")
    def test_returns_none_on_conversion_failure(self, mock_convert):
        mock_convert.return_value = None
        service = self._get_service()
        result = service._convert_docx_to_temp_pdf_from_bytes(b"fake docx", "test.docx")
        assert result is None


class TestConfirmImportProviderThreading:
    """Test that confirm_import properly threads storage_provider."""

    def test_signature_accepts_storage_provider(self):
        import inspect

        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        sig = inspect.signature(ContractFolderScanService.confirm_import)
        assert "storage_provider" in sig.parameters

    def test_mark_already_imported_accepts_storage_provider(self):
        import inspect

        from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
        sig = inspect.signature(CandidatePostProcessor._mark_already_imported)
        assert "storage_provider" in sig.parameters

    def test_collect_docx_files_accepts_storage_provider(self):
        import inspect

        from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor
        sig = inspect.signature(CandidatePostProcessor._collect_docx_files)
        assert "storage_provider" in sig.parameters


class TestCollectWorkLogSuggestionsCloud:
    """Test the cloud variant of collect_work_log_suggestions."""

    def test_returns_empty_on_provider_error(self):
        from apps.contracts.services.contract.integrations.archive_classifier import _collect_work_log_suggestions_cloud
        provider = MagicMock()
        provider.list_directory.side_effect = ConnectionError("timeout")
        result = _collect_work_log_suggestions_cloud("/", "litigation", provider)
        assert result == []

    def test_collects_date_prefixed_dirs(self):
        from apps.contracts.services.contract.integrations.archive_classifier import _collect_work_log_suggestions_cloud
        provider = _make_mock_provider(
            dirs=[
                _make_cloud_file("2026.01.15-立案", "/2026.01.15-立案", is_dir=True),
                _make_cloud_file("2026.03.20-开庭", "/2026.03.20-开庭", is_dir=True),
                _make_cloud_file("其他文件夹", "/其他文件夹", is_dir=True),
            ]
        )
        result = _collect_work_log_suggestions_cloud("/", "litigation", provider)
        assert len(result) == 2
        dates = {r["date"] for r in result}
        assert "2026-01-15" in dates
        assert "2026-03-20" in dates
