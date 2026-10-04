"""自动重命名后回写文书引用的测试。

修复背景：自动重命名流程（DocumentAttachmentService.rename_documents）此前只做
物理 rename 与写 scraper_task.result，不更新 CourtDocument.local_file_path 等引用，
导致下载 404、删除时原件成孤儿。现在重命名完成后调用
CourtSMSDocumentReferenceService.sync_document_references 回写引用。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.automation.models import (
    CourtDocument,
    CourtSMS,
    CourtSMSStatus,
    DocumentDownloadStatus,
    ScraperTask,
    ScraperTaskType,
)


def _make_service(tmp_path):
    from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService

    renamer = MagicMock()
    service = DocumentAttachmentService(case_service=MagicMock(), renamer=renamer)
    return service, renamer


@pytest.mark.django_db
class TestRenameDocumentsSyncsReferences:
    def test_syncs_court_document_local_file_path(self, tmp_path) -> None:
        """自动重命名后必须回写 CourtDocument.local_file_path 与任务结果 files。"""
        service, renamer = _make_service(tmp_path)

        old_pdf = tmp_path / "original.pdf"
        old_pdf.write_bytes(b"old")
        new_pdf = tmp_path / "renamed.pdf"
        new_pdf.write_bytes(b"new")
        old_abs = str(old_pdf.resolve())
        new_abs = str(new_pdf.resolve())

        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": [old_abs]},
        )
        CourtDocument.objects.create(
            scraper_task=task,
            c_sdbh="SD001",
            c_stbh="ST001",
            wjlj="https://example.com/doc.pdf",
            c_wsbh="WS001",
            c_wsmc="测试文书",
            c_fybh="FY001",
            c_fymc="测试法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
            download_status=DocumentDownloadStatus.SUCCESS,
            local_file_path=old_abs,
        )
        sms = CourtSMS.objects.create(
            content="测试短信",
            received_at=timezone.now(),
            status=CourtSMSStatus.RENAMING,
            scraper_task=task,
        )

        renamer.rename_with_fallback.return_value = new_abs

        renamed = service.rename_documents(sms, [old_abs])

        assert renamed == [new_abs]

        # CourtDocument 引用必须指向新路径
        doc = CourtDocument.objects.get()
        assert doc.local_file_path == new_abs

        # 任务结果 files 同步更新为新路径
        task.refresh_from_db()
        assert task.result["files"] == [new_abs]

    def test_no_rename_no_sync(self, tmp_path) -> None:
        """重命名失败返回原路径（新旧一致）时不应触发引用回写。"""
        service, renamer = _make_service(tmp_path)

        old_pdf = tmp_path / "same.pdf"
        old_pdf.write_bytes(b"same")
        old_abs = str(old_pdf.resolve())

        task = ScraperTask.objects.create(
            task_type=ScraperTaskType.COURT_DOCUMENT,
            url="https://example.com",
            result={"files": [old_abs]},
        )
        CourtDocument.objects.create(
            scraper_task=task,
            c_sdbh="SD002",
            c_stbh="ST002",
            wjlj="https://example.com/doc2.pdf",
            c_wsbh="WS002",
            c_wsmc="测试文书2",
            c_fybh="FY002",
            c_fymc="测试法院",
            c_wjgs="pdf",
            dt_cjsj=timezone.now(),
            download_status=DocumentDownloadStatus.SUCCESS,
            local_file_path=old_abs,
        )
        sms = CourtSMS.objects.create(
            content="测试短信2",
            received_at=timezone.now(),
            status=CourtSMSStatus.RENAMING,
            scraper_task=task,
        )

        # 降级方案返回原路径（新旧一致）
        renamer.rename_with_fallback.return_value = old_abs

        renamed = service.rename_documents(sms, [old_abs])

        assert renamed == [old_abs]
        doc = CourtDocument.objects.get()
        assert doc.local_file_path == old_abs


class TestSyncDocumentReferencesService:
    """CourtSMSDocumentReferenceService.sync_document_references 单元行为。"""

    def test_updates_sms_document_file_paths(self) -> None:
        from pathlib import Path

        from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

        sms = MagicMock()
        sms.document_file_paths = ["/tmp/media/old.pdf", "/tmp/media/other.pdf"]
        sms.scraper_task = None
        sms.case_log = None
        sms.save = MagicMock()

        CourtSMSDocumentReferenceService().sync_document_references(
            sms, "/tmp/media/old.pdf", "/tmp/media/new.pdf", None
        )

        # 回写的是规范化（resolve）后的新路径
        expected_new = Path("/tmp/media/new.pdf").resolve(strict=False).as_posix()
        assert sms.document_file_paths == [expected_new, "/tmp/media/other.pdf"]
        sms.save.assert_called_once()

    def test_without_court_document_id_skips_court_document_update(self) -> None:
        """court_document_id 为空时不更新 CourtDocument（避免误清空）。"""
        from unittest.mock import patch

        from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

        sms = MagicMock()
        sms.document_file_paths = []
        sms.scraper_task = None
        sms.case_log = None

        with patch("apps.automation.models.CourtDocument.objects") as mock_objects:
            CourtSMSDocumentReferenceService().sync_document_references(
                sms, "/tmp/media/old.pdf", "/tmp/media/new.pdf", None
            )
            mock_objects.filter.assert_not_called()
