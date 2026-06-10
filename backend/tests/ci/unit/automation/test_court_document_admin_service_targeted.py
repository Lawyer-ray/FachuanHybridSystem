"""Targeted tests for CourtDocumentAdminService covering batch operations, stats, cleanup."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.models import CourtDocument, DocumentDownloadStatus, ScraperTask, ScraperTaskType
from apps.automation.services.admin.court_document_admin_service import CourtDocumentAdminService
from apps.core.exceptions import BusinessException, ValidationException


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def service():
    return CourtDocumentAdminService()


@pytest.fixture
def scraper_task(db):
    return ScraperTask.objects.create(
        task_type=ScraperTaskType.COURT_DOCUMENT,
        url="https://example.com",
    )


@pytest.fixture
def pending_doc(scraper_task):
    return CourtDocument.objects.create(
        scraper_task=scraper_task,
        c_sdbh="SD001",
        c_stbh="ST001",
        wjlj="https://example.com/doc1.pdf",
        c_wsbh="WS001",
        c_wsmc="测试文书1",
        c_fybh="FY001",
        c_fymc="测试法院",
        c_wjgs="pdf",
        dt_cjsj=timezone.now(),
        download_status=DocumentDownloadStatus.PENDING,
    )


@pytest.fixture
def failed_doc(scraper_task):
    return CourtDocument.objects.create(
        scraper_task=scraper_task,
        c_sdbh="SD002",
        c_stbh="ST002",
        wjlj="https://example.com/doc2.pdf",
        c_wsbh="WS002",
        c_wsmc="测试文书2",
        c_fybh="FY001",
        c_fymc="测试法院",
        c_wjgs="pdf",
        dt_cjsj=timezone.now(),
        download_status=DocumentDownloadStatus.FAILED,
        error_message="下载失败",
    )


@pytest.fixture
def success_doc(scraper_task, tmp_path):
    file_path = tmp_path / "doc3.pdf"
    file_path.write_bytes(b"test content")
    return CourtDocument.objects.create(
        scraper_task=scraper_task,
        c_sdbh="SD003",
        c_stbh="ST003",
        wjlj="https://example.com/doc3.pdf",
        c_wsbh="WS003",
        c_wsmc="测试文书3",
        c_fybh="FY002",
        c_fymc="另一个法院",
        c_wjgs="pdf",
        dt_cjsj=timezone.now(),
        download_status=DocumentDownloadStatus.SUCCESS,
        local_file_path=str(file_path),
        file_size=12,
    )


# ── batch_download_documents ──────────────────────────────────────


@pytest.mark.django_db
class TestBatchDownloadDocuments:
    def test_empty_ids_raises(self, service):
        with pytest.raises(ValidationException, match="没有选中任何文书"):
            service.batch_download_documents([])

    def test_no_downloadable_docs_raises(self, service, success_doc):
        with pytest.raises((ValidationException, BusinessException)):
            service.batch_download_documents([success_doc.id])

    def test_starts_download_for_pending(self, service, pending_doc):
        result = service.batch_download_documents([pending_doc.id])
        assert result["started_download"] == 1
        assert result["total_requested"] == 1
        pending_doc.refresh_from_db()
        assert pending_doc.download_status == DocumentDownloadStatus.DOWNLOADING

    def test_starts_download_for_failed(self, service, failed_doc):
        result = service.batch_download_documents([failed_doc.id])
        assert result["started_download"] == 1
        failed_doc.refresh_from_db()
        assert failed_doc.download_status == DocumentDownloadStatus.DOWNLOADING

    def test_mixed_status_counts_correctly(self, service, pending_doc, success_doc):
        result = service.batch_download_documents([pending_doc.id, success_doc.id])
        assert result["started_download"] == 1
        assert result["already_downloaded"] == 1

    def test_nonexistent_ids_raise(self, service):
        with pytest.raises((ValidationException, BusinessException)):
            service.batch_download_documents([999999])


# ── batch_delete_documents ────────────────────────────────────────


@pytest.mark.django_db
class TestBatchDeleteDocuments:
    def test_empty_ids_raises(self, service):
        with pytest.raises(ValidationException, match="没有选中任何文书"):
            service.batch_delete_documents([])

    def test_nonexistent_raises(self, service):
        with pytest.raises((ValidationException, BusinessException)):
            service.batch_delete_documents([999999])

    def test_deletes_records(self, service, pending_doc, failed_doc):
        result = service.batch_delete_documents([pending_doc.id, failed_doc.id])
        assert result["deleted_records"] == 2
        assert result["deleted_files"] == 0
        assert CourtDocument.objects.count() == 0

    def test_deletes_with_files(self, service, success_doc, tmp_path):
        file_path = Path(success_doc.local_file_path)
        assert file_path.exists()
        result = service.batch_delete_documents([success_doc.id], delete_files=True)
        assert result["deleted_records"] == 1
        assert result["deleted_files"] == 1
        assert not file_path.exists()

    def test_delete_files_handles_missing(self, service, pending_doc):
        pending_doc.local_file_path = "/nonexistent/path/file.pdf"
        pending_doc.save()
        result = service.batch_delete_documents([pending_doc.id], delete_files=True)
        assert result["deleted_records"] == 1
        assert result["deleted_files"] == 0


# ── get_document_statistics ───────────────────────────────────────


@pytest.mark.django_db
class TestGetDocumentStatistics:
    def test_empty_queryset(self, service):
        result = service.get_document_statistics()
        assert result["total_documents"] == 0
        assert isinstance(result["status_stats"], dict)
        assert isinstance(result["court_stats"], list)
        assert isinstance(result["format_stats"], list)
        assert isinstance(result["date_stats"], list)

    def test_with_documents(self, service, pending_doc, failed_doc, success_doc):
        result = service.get_document_statistics()
        assert result["total_documents"] == 3
        assert result["status_stats"][DocumentDownloadStatus.PENDING]["count"] == 1
        assert result["status_stats"][DocumentDownloadStatus.SUCCESS]["count"] == 1
        assert result["status_stats"][DocumentDownloadStatus.FAILED]["count"] == 1

    def test_with_custom_queryset(self, service, pending_doc, failed_doc, success_doc):
        qs = CourtDocument.objects.filter(download_status=DocumentDownloadStatus.PENDING)
        result = service.get_document_statistics(queryset=qs)
        assert result["total_documents"] == 1

    def test_court_stats_present(self, service, pending_doc, success_doc):
        result = service.get_document_statistics()
        assert len(result["court_stats"]) > 0

    def test_format_stats_present(self, service, pending_doc):
        result = service.get_document_statistics()
        assert len(result["format_stats"]) > 0

    def test_date_stats_length(self, service, pending_doc):
        result = service.get_document_statistics()
        assert len(result["date_stats"]) == 30

    def test_file_size_stats(self, service, success_doc):
        result = service.get_document_statistics()
        assert result["file_size_stats"]["count"] == 1
        assert result["file_size_stats"]["total_size"] == 12


# ── retry_failed_downloads ────────────────────────────────────────


@pytest.mark.django_db
class TestRetryFailedDownloads:
    def test_no_failed_returns_zero(self, service, pending_doc):
        result = service.retry_failed_downloads()
        assert result["retried_count"] == 0

    def test_retries_all_failed(self, service, failed_doc):
        result = service.retry_failed_downloads()
        assert result["retried_count"] == 1
        failed_doc.refresh_from_db()
        assert failed_doc.download_status == DocumentDownloadStatus.PENDING
        assert failed_doc.error_message is None

    def test_retries_specific_ids(self, service, failed_doc, scraper_task):
        another_failed = CourtDocument.objects.create(
            scraper_task=scraper_task,
            c_sdbh="SD010",
            c_stbh="ST010",
            wjlj="https://example.com/doc10.pdf",
            c_wsbh="WS010",
            c_wsmc="测试文书10",
            c_fybh="FY001",
            c_fymc="测试法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
            download_status=DocumentDownloadStatus.FAILED,
        )
        result = service.retry_failed_downloads(document_ids=[failed_doc.id])
        assert result["retried_count"] == 1
        another_failed.refresh_from_db()
        assert another_failed.download_status == DocumentDownloadStatus.FAILED


# ── get_download_progress ─────────────────────────────────────────


@pytest.mark.django_db
class TestGetDownloadProgress:
    def test_empty(self, service):
        result = service.get_download_progress()
        assert result["total"] == 0
        assert result["progress_percentage"] == 0

    def test_with_documents(self, service, pending_doc, failed_doc, success_doc):
        result = service.get_download_progress()
        assert result["total"] == 3
        assert result["pending"] == 1
        assert result["success"] == 1
        assert result["failed"] == 1
        assert result["downloading"] == 0

    def test_with_task_filter(self, service, pending_doc, success_doc, scraper_task):
        other_task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com/other"
        )
        CourtDocument.objects.create(
            scraper_task=other_task,
            c_sdbh="SD999",
            c_stbh="ST999",
            wjlj="https://example.com/doc999.pdf",
            c_wsbh="WS999",
            c_wsmc="其他文书",
            c_fybh="FY001",
            c_fymc="测试法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
        )
        result = service.get_download_progress(task_id=scraper_task.id)
        assert result["total"] == 2
        assert result["task_id"] == scraper_task.id


# ── cleanup_orphaned_files ────────────────────────────────────────


@pytest.mark.django_db
class TestCleanupOrphanedFiles:
    def test_no_directory(self, service):
        with patch("apps.automation.services.admin.court_document_admin_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = "/nonexistent_root"
            result = service.cleanup_orphaned_files()
            assert result["orphaned_files"] == 0

    def test_no_orphans(self, service, success_doc, tmp_path):
        with patch("apps.automation.services.admin.court_document_admin_service.settings") as mock_settings:
            media = str(tmp_path)
            # Create the doc file under media/court_documents/
            court_dir = tmp_path / "court_documents"
            court_dir.mkdir()
            doc_file = court_dir / "doc3.pdf"
            doc_file.write_bytes(b"test")
            success_doc.local_file_path = f"court_documents/doc3.pdf"
            success_doc.save()
            mock_settings.MEDIA_ROOT = media
            result = service.cleanup_orphaned_files()
            assert result["orphaned_files"] == 0

    def test_with_orphan_file(self, service, tmp_path):
        with patch("apps.automation.services.admin.court_document_admin_service.settings") as mock_settings:
            media = str(tmp_path)
            court_dir = tmp_path / "court_documents"
            court_dir.mkdir()
            orphan = court_dir / "orphan.pdf"
            orphan.write_bytes(b"orphan content")
            mock_settings.MEDIA_ROOT = media
            result = service.cleanup_orphaned_files()
            assert result["orphaned_files"] == 1
            assert result["deleted_files"] == 1
