"""P05-01 回归：孤立文书清理的数据安全（默认 dry-run / 在飞任务 / 绝对与相对路径 / 被引用副本）。

旧实现（`cleanup_orphaned_files`）白名单只认 `status=success` 且路径字符串逐字相等，
其余 `media/court_documents/` 下的文件**立即物理删除**。下面 6 条覆盖审计点名的三类误删
（在飞任务、绝对路径存量、被短信/案件日志引用的副本）以及两个新默认值（dry-run、min_age）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from apps.automation.models import CourtDocument, CourtSMS, DocumentDownloadStatus, ScraperTask, ScraperTaskType
from apps.automation.services.admin.court_document_admin_service import CourtDocumentAdminService
from apps.cases.models import CaseLogAttachment
from apps.testing.factories import CaseLogFactory

# 比默认 min_age_hours=24 更旧，保证不会被「太新则跳过」挡住
_OLD_FILE_AGE_SECONDS = 3 * 24 * 3600


def _write_old_file(path: Path) -> Path:
    """写一个 3 天前落盘的文件（mtime 决定 min_age_hours 是否跳过它）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"doc")
    old_mtime = timezone.now().timestamp() - _OLD_FILE_AGE_SECONDS
    os.utime(path, (old_mtime, old_mtime))
    return path


def _make_document(
    scraper_task: ScraperTask,
    serial: str,
    download_status: str,
    local_file_path: str,
) -> CourtDocument:
    return CourtDocument.objects.create(
        scraper_task=scraper_task,
        c_sdbh=f"SD{serial}",
        c_stbh=f"ST{serial}",
        wjlj=f"https://example.com/{serial}.pdf",
        c_wsbh=f"WS{serial}",
        c_wsmc=f"文书{serial}",
        c_fybh="FY001",
        c_fymc="测试法院",
        c_wjgs="pdf",
        dt_cjsj=timezone.now(),
        download_status=download_status,
        local_file_path=local_file_path,
    )


@pytest.fixture
def media_root(tmp_path: Path, settings: Any) -> Path:
    root = tmp_path / "media"
    (root / "court_documents").mkdir(parents=True)
    settings.MEDIA_ROOT = str(root)
    return root


@pytest.fixture
def court_documents_dir(media_root: Path) -> Path:
    return media_root / "court_documents"


@pytest.fixture
def service() -> CourtDocumentAdminService:
    return CourtDocumentAdminService()


@pytest.fixture
def scraper_task(db: Any) -> ScraperTask:
    return ScraperTask.objects.create(task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com/sms")


@pytest.mark.django_db
def test_default_run_is_dry_run(service: CourtDocumentAdminService, court_documents_dir: Path) -> None:
    """默认 dry_run=True：只返回将被删除的清单，文件必须还在。"""
    orphan = _write_old_file(court_documents_dir / "orphan.pdf")

    result = service.cleanup_orphaned_files()

    assert result["dry_run"] is True
    assert result["orphaned_paths"] == [orphan.resolve().as_posix()]
    assert result["deleted_files"] == 0
    assert orphan.exists()


@pytest.mark.django_db
def test_dry_run_false_deletes_orphan(service: CourtDocumentAdminService, court_documents_dir: Path) -> None:
    """显式 dry_run=False 时才真的删除（证明清理本身仍然有效）。"""
    orphan = _write_old_file(court_documents_dir / "orphan.pdf")

    result = service.cleanup_orphaned_files(dry_run=False)

    assert result["deleted_files"] == 1
    assert result["delete_errors"] == []
    assert not orphan.exists()


@pytest.mark.django_db
def test_in_flight_documents_are_protected(
    service: CourtDocumentAdminService, scraper_task: ScraperTask, court_documents_dir: Path
) -> None:
    """pending / downloading 的任务可能正在往这份文件里写，不能当孤儿删。"""
    pending_file = _write_old_file(court_documents_dir / "pending.pdf")
    downloading_file = _write_old_file(court_documents_dir / "downloading.pdf")
    _make_document(scraper_task, "P1", DocumentDownloadStatus.PENDING, "court_documents/pending.pdf")
    _make_document(scraper_task, "D1", DocumentDownloadStatus.DOWNLOADING, "court_documents/downloading.pdf")

    result = service.cleanup_orphaned_files(dry_run=False)

    assert result["orphaned_paths"] == []
    assert result["deleted_files"] == 0
    assert pending_file.exists()
    assert downloading_file.exists()


@pytest.mark.django_db
def test_absolute_and_relative_db_paths_are_both_protected(
    service: CourtDocumentAdminService, scraper_task: ScraperTask, court_documents_dir: Path
) -> None:
    """库里存绝对路径的存量数据，不能因为扫描侧用相对路径而被判成孤儿。"""
    absolute_file = _write_old_file(court_documents_dir / "absolute.pdf")
    relative_file = _write_old_file(court_documents_dir / "relative.pdf")
    _make_document(scraper_task, "A1", DocumentDownloadStatus.SUCCESS, absolute_file.resolve().as_posix())
    _make_document(scraper_task, "R1", DocumentDownloadStatus.SUCCESS, "court_documents/relative.pdf")

    result = service.cleanup_orphaned_files(dry_run=False)

    assert result["deleted_files"] == 0
    assert absolute_file.exists()
    assert relative_file.exists()


@pytest.mark.django_db
def test_files_referenced_by_sms_and_case_log_are_protected(
    service: CourtDocumentAdminService, court_documents_dir: Path
) -> None:
    """CourtSMS.document_file_paths 与 CaseLogAttachment 引用的副本都不是孤儿。"""
    sms_referenced = _write_old_file(court_documents_dir / "sms-ref.pdf")
    case_log_referenced = _write_old_file(court_documents_dir / "case-log-ref.pdf")

    CourtSMS.objects.create(
        content="【法院】判决书已送达，请及时查收",
        received_at=timezone.now(),
        document_file_paths=["court_documents/sms-ref.pdf"],
    )
    CaseLogAttachment.objects.create(
        log=CaseLogFactory(),
        file="court_documents/case-log-ref.pdf",
        original_filename="case-log-ref.pdf",
    )

    result = service.cleanup_orphaned_files(dry_run=False)

    assert result["orphaned_paths"] == []
    assert result["deleted_files"] == 0
    assert sms_referenced.exists()
    assert case_log_referenced.exists()


@pytest.mark.django_db
def test_new_files_are_skipped_by_min_age(service: CourtDocumentAdminService, court_documents_dir: Path) -> None:
    """刚落盘的文件（mtime 现在）可能正在下载/归档，min_age_hours 必须挡住它。"""
    fresh_file = court_documents_dir / "just-written.pdf"
    fresh_file.write_bytes(b"doc")

    result = service.cleanup_orphaned_files(dry_run=False, min_age_hours=24)

    assert result["orphaned_paths"] == []
    assert fresh_file.exists()
