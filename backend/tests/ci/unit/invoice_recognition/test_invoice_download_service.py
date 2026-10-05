"""InvoiceDownloadService 单元测试。

覆盖归属过滤（superuser / 普通用户 / 越权）、download_single 的
文件命中与缺失、类目/全部下载的打包分发与文件名生成（含非法字符替换）。
合并与打包内部函数以 mock 替代，文件落盘走 tmp_path MEDIA_ROOT。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.invoice_recognition.models import InvoiceCategory, InvoiceRecognitionTask, InvoiceRecord
from apps.invoice_recognition.services.invoice_download_service import InvoiceDownloadService
from apps.testing.factories import LawyerFactory


@pytest.fixture
def svc() -> InvoiceDownloadService:
    return InvoiceDownloadService()


@pytest.fixture
def owner(db: None):
    return LawyerFactory()


@pytest.fixture
def other_user(db: None):
    return LawyerFactory()


@pytest.fixture
def task(db: None, owner) -> InvoiceRecognitionTask:
    return InvoiceRecognitionTask.objects.create(name="2026年6月报销", created_by=owner)


def _record(
    task: InvoiceRecognitionTask,
    *,
    name: str = "发票.pdf",
    category: str = InvoiceCategory.OTHER,
    duplicate: bool = False,
) -> InvoiceRecord:
    return InvoiceRecord.objects.create(
        task=task,
        file_path=f"invoices/{name}",
        original_filename=name,
        category=category,
        is_duplicate=duplicate,
        invoice_date=date(2026, 6, 1),
    )


@pytest.mark.django_db
class TestGetTaskForUser:
    def test_owner_can_fetch(self, svc, task, owner) -> None:
        assert svc._get_task_for_user(task.id, owner).id == task.id

    def test_superuser_can_fetch_any(self, svc, task) -> None:
        superuser = LawyerFactory(is_superuser=True)
        assert svc._get_task_for_user(task.id, superuser).id == task.id

    def test_other_user_treated_as_missing(self, svc, task, other_user) -> None:
        with pytest.raises(InvoiceRecognitionTask.DoesNotExist):
            svc._get_task_for_user(task.id, other_user)

    def test_anonymous_can_fetch(self, svc, task) -> None:
        # user=None 表示匿名（admin 定时任务）调用：不做归属过滤
        assert svc._get_task_for_user(task.id, None).id == task.id


@pytest.mark.django_db
class TestDownloadSingle:
    def test_returns_existing_file(self, svc, task, owner, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        record = _record(task, name="票1.pdf")
        stored = tmp_path / "invoices" / "票1.pdf"
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(b"pdf-bytes")

        path, filename = svc.download_single(record.id, task.id, user=owner)

        assert path == stored
        assert filename == "票1.pdf"

    def test_missing_file_raises(self, svc, task, owner, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        record = _record(task, name="缺失.pdf")

        with pytest.raises(FileNotFoundError, match="文件不存在"):
            svc.download_single(record.id, task.id, user=owner)

    def test_other_user_cannot_download(self, svc, task, other_user, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = tmp_path
        record = _record(task, name="越权.pdf")
        stored = tmp_path / "invoices" / "越权.pdf"
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(b"x")

        with pytest.raises(InvoiceRecord.DoesNotExist):
            svc.download_single(record.id, task.id, user=other_user)

    def test_task_filter_applied(self, svc, task, owner, settings, tmp_path, db) -> None:
        """task_id 不匹配时（记录属于其他任务）按不存在处理。"""
        settings.MEDIA_ROOT = tmp_path
        record = _record(task, name="隔离.pdf")
        other_task = InvoiceRecognitionTask.objects.create(name="别的任务", created_by=owner)

        with pytest.raises(InvoiceRecord.DoesNotExist):
            svc.download_single(record.id, other_task.id, user=owner)


@pytest.mark.django_db
class TestDownloadByCategory:
    def test_zip_pack_with_known_category_label(self, svc, task, owner) -> None:
        _record(task, name="a.pdf", category=InvoiceCategory.VAT_SPECIAL)
        with (
            patch.object(svc, "_pack_to_zip", return_value=b"zip-bytes") as mock_zip,
            patch.object(svc, "_merge_to_pdf") as mock_pdf,
        ):
            data, filename = svc.download_by_category(task.id, InvoiceCategory.VAT_SPECIAL, fmt="zip", user=owner)

        assert data == b"zip-bytes"
        assert "增值税专用发票" in filename
        assert filename.endswith(".zip")
        mock_zip.assert_called_once()
        mock_pdf.assert_not_called()
        records = mock_zip.call_args.args[0]
        assert len(records) == 1

    def test_pdf_merge_branch(self, svc, task, owner) -> None:
        _record(task, name="b.pdf", category=InvoiceCategory.TRAIN_TICKET)
        with (
            patch.object(svc, "_merge_to_pdf", return_value=b"pdf-bytes") as mock_pdf,
            patch.object(svc, "_pack_to_zip") as mock_zip,
        ):
            data, filename = svc.download_by_category(task.id, InvoiceCategory.TRAIN_TICKET, fmt="pdf", user=owner)

        assert data == b"pdf-bytes"
        assert filename.endswith(".pdf")
        mock_pdf.assert_called_once()
        mock_zip.assert_not_called()

    def test_unknown_category_label_falls_back_to_raw(self, svc, task, owner) -> None:
        _record(task, name="c.pdf", category="custom_cat")
        with patch.object(svc, "_pack_to_zip", return_value=b"zip"):
            _, filename = svc.download_by_category(task.id, "custom_cat", fmt="zip", user=owner)

        assert "custom_cat" in filename

    def test_duplicates_excluded(self, svc, task, owner) -> None:
        _record(task, name="d1.pdf", category=InvoiceCategory.OTHER)
        _record(task, name="d2.pdf", category=InvoiceCategory.OTHER, duplicate=True)
        with patch.object(svc, "_pack_to_zip", return_value=b"zip") as mock_zip:
            svc.download_by_category(task.id, InvoiceCategory.OTHER, fmt="zip", user=owner)

        records = mock_zip.call_args.args[0]
        assert [r.original_filename for r in records] == ["d1.pdf"]

    def test_other_user_denied(self, svc, task, other_user) -> None:
        with pytest.raises(InvoiceRecognitionTask.DoesNotExist):
            svc.download_by_category(task.id, InvoiceCategory.OTHER, user=other_user)


@pytest.mark.django_db
class TestDownloadAll:
    def test_all_categories_with_duplicates_excluded(self, svc, task, owner) -> None:
        _record(task, name="e1.pdf", category=InvoiceCategory.VAT_NORMAL)
        _record(task, name="e2.pdf", category=InvoiceCategory.TAXI_RECEIPT)
        _record(task, name="dup.pdf", category=InvoiceCategory.OTHER, duplicate=True)

        with (
            patch.object(svc, "_pack_to_zip", return_value=b"zip-all") as mock_zip,
        ):
            data, filename = svc.download_all(task.id, fmt="zip", user=owner)

        assert data == b"zip-all"
        assert "全部" in filename
        records = mock_zip.call_args.args[0]
        assert {r.original_filename for r in records} == {"e1.pdf", "e2.pdf"}

    def test_pdf_branch(self, svc, task, owner) -> None:
        _record(task, name="f.pdf")
        with (
            patch.object(svc, "_merge_to_pdf", return_value=b"pdf-all") as mock_pdf,
            patch.object(svc, "_pack_to_zip") as mock_zip,
        ):
            data, filename = svc.download_all(task.id, fmt="pdf", user=owner)

        assert data == b"pdf-all"
        assert filename.endswith(".pdf")
        mock_pdf.assert_called_once()
        mock_zip.assert_not_called()


class TestGenerateFilename:
    def test_category_none_uses_all_label(self) -> None:
        svc = InvoiceDownloadService()
        filename = svc._generate_filename("任务A", None, "zip")
        assert "全部" in filename
        assert filename.endswith(".zip")

    def test_illegal_chars_replaced(self) -> None:
        svc = InvoiceDownloadService()
        filename = svc._generate_filename("任务/名:2026?", "增值税专用发票", "pdf")
        assert "/" not in filename
        assert ":" not in filename
        assert "?" not in filename
        assert "_" in filename
        assert filename.endswith(".pdf")

    def test_contains_local_date(self) -> None:
        from django.utils import timezone

        svc = InvoiceDownloadService()
        filename = svc._generate_filename("T", "C", "zip")
        assert timezone.localdate().strftime("%Y%m%d") in filename
