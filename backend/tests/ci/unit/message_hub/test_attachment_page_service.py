"""附件页数维护测试：PyMuPDF 数页、详情回填、上传即算、公共元信息透出。"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.message_hub.models import InboxMessage
from apps.message_hub.services.attachment_page_service import count_pdf_pages, ensure_page_counts, fill_page_counts
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import create_manual_message, get_or_create_manual_source

pytestmark = pytest.mark.django_db


def _make_pdf(path: Path, pages: int = 3) -> Path:
    import pymupdf as fitz

    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()
    return path


def _make_message(tmp_path: Path, pdf_path: Path | None) -> InboxMessage:
    source = get_or_create_manual_source()
    local_path = str(pdf_path) if pdf_path else ""
    return InboxMessage.objects.create(
        source=source,
        message_id=f"t-pagecount-{timezone.now().timestamp()}",
        subject="页数回填测试",
        received_at=timezone.now(),
        attachments_meta=[
            {
                "filename": "扫描件.pdf",
                "original_filename": "扫描件.pdf",
                "content_type": "application/pdf",
                "size": 1024,
                "part_index": 0,
                "local_path": local_path,
            },
            {
                "filename": "照片.jpg",
                "original_filename": "照片.jpg",
                "content_type": "image/jpeg",
                "size": 2048,
                "part_index": 1,
                "local_path": "",
            },
        ],
        draft_state={},
    )


class TestCountPdfPages:

    def test_counts_real_pdf(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "a.pdf", pages=5)
        assert count_pdf_pages(pdf) == 5

    def test_invalid_file_returns_none(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        assert count_pdf_pages(bad) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert count_pdf_pages(tmp_path / "ghost.pdf") is None


class TestFillPageCounts:

    def test_fills_pdf_only_and_skips_existing(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "a.pdf", pages=3)
        metas = [
            {"filename": "a.pdf", "content_type": "application/pdf", "part_index": 0, "local_path": str(pdf)},
            {"filename": "b.pdf", "content_type": "application/pdf", "part_index": 1, "local_path": str(pdf), "page_count": 7},
            {"filename": "c.jpg", "content_type": "image/jpeg", "part_index": 2, "local_path": str(pdf)},
            {"filename": "d.pdf", "content_type": "application/pdf", "part_index": 3, "local_path": ""},
        ]
        assert fill_page_counts(metas) is True
        assert metas[0]["page_count"] == 3
        # 已有页数的不覆盖
        assert metas[1]["page_count"] == 7
        # 非 PDF 与无文件的补不了页数
        assert "page_count" not in metas[2]
        assert "page_count" not in metas[3]
        # 全部命中后再跑：无改动
        assert fill_page_counts(metas) is False

    def test_filename_suffix_counts_as_pdf(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "a.pdf", pages=2)
        metas = [{"filename": "a.pdf", "content_type": "", "part_index": 0, "local_path": str(pdf)}]
        assert fill_page_counts(metas) is True
        assert metas[0]["page_count"] == 2


class TestEnsurePageCounts:

    def test_backfills_and_persists(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "scan.pdf", pages=4)
        msg = _make_message(tmp_path, pdf)
        ensure_page_counts(msg)
        fresh = InboxMessage.objects.get(pk=msg.pk)
        assert fresh.attachments_meta[0]["page_count"] == 4
        # 非 PDF 附件不动
        assert "page_count" not in fresh.attachments_meta[1]
        msg.delete()

    def test_missing_file_no_write(self, tmp_path: Path) -> None:
        msg = _make_message(tmp_path, None)
        ensure_page_counts(msg)
        fresh = InboxMessage.objects.get(pk=msg.pk)
        assert "page_count" not in fresh.attachments_meta[0]
        msg.delete()

    def test_public_meta_exposes_page_count(self, tmp_path: Path) -> None:
        pdf = _make_pdf(tmp_path / "scan.pdf", pages=9)
        msg = _make_message(tmp_path, pdf)
        ensure_page_counts(msg)
        public = msg.get_public_attachments_meta()
        assert public[0]["page_count"] == 9
        assert public[0].get("local_path") is None  # 本地路径不外泄
        assert "page_count" not in public[1] or public[1]["page_count"] is None
        msg.delete()


class TestUploadPathIntegration:

    def test_create_manual_message_has_page_count(self, tmp_path: Path) -> None:
        pdf_bytes = _make_pdf(tmp_path / "up.pdf", pages=6).read_bytes()
        up = SimpleUploadedFile("up.pdf", pdf_bytes, content_type="application/pdf")
        msg = create_manual_message([up], subject="上传即算页数")
        try:
            assert msg.attachments_meta[0].get("page_count") == 6
        finally:
            for att in msg.attachments_meta:
                path = resolve_media_attachment_path(str(att.get("local_path", "")))
                if path is not None and path.exists():
                    path.unlink()
            msg.delete()
