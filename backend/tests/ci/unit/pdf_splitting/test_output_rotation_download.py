"""页旋转在**出口端点**上真的生效（单段 PDF / 多选 zip / extract-pages）。

`test_output_rotation.py` 只钉纯函数；这里钉接线：参数有没有从 HTTP 层
（表单字段 / query）一路传到切页之前。接线漏了的表现是「函数全绿、律师打开
收到的 PDF 还是倒的」——那正是我们要防的那类静默失败。
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf as fitz
import pytest
from django.test import RequestFactory, override_settings

from apps.pdf_splitting.api.pdf_splitting_api import get_pdf_split_download, get_pdf_split_segment_pdf
from apps.pdf_splitting.models import (
    PdfSplitJob,
    PdfSplitJobStatus,
    PdfSplitReviewFlag,
    PdfSplitSegment,
    PdfSplitSegmentType,
    PdfSplitSourceType,
)
from apps.pdf_splitting.services.storage import PdfSplitStorage

pytestmark = pytest.mark.django_db
_factory = RequestFactory()


def _pdf(page_count: int = 2, *, rotations: list[int] | None = None) -> bytes:
    doc = fitz.open()
    try:
        for no in range(1, page_count + 1):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), f"PAGE-{no}")
            deg = (rotations or [])[no - 1] if rotations and no - 1 < len(rotations) else 0
            if deg:
                page.set_rotation(deg)
        return doc.tobytes()  # type: ignore[no-any-return]
    finally:
        doc.close()


def _request() -> Any:
    return _factory.get("/")


def _job(tmp_path: Path, *, pages: int = 2, rotations: list[int] | None = None) -> PdfSplitJob:
    job = PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="卷宗示例.pdf",
        status=PdfSplitJobStatus.REVIEW_REQUIRED,
        total_pages=pages,
    )
    storage = PdfSplitStorage(job.id)
    storage.ensure_dirs()
    storage.source_pdf_path.write_bytes(_pdf(pages, rotations=rotations))
    return job


def _segment(job: PdfSplitJob, *, order: int, start: int, end: int, name: str) -> PdfSplitSegment:
    return PdfSplitSegment.objects.create(
        job=job,
        order=order,
        page_start=start,
        page_end=end,
        segment_type=PdfSplitSegmentType.COMPLAINT,
        filename=name,
        confidence=1.0,
        source_method="rule",
        review_flag=PdfSplitReviewFlag.NORMAL,
    )


def _read_pdf(content: bytes) -> Any:
    return fitz.open(stream=content, filetype="pdf")


@override_settings(MEDIA_ROOT="")
def _media(pytest_tmp: Path) -> Any:
    return override_settings()


class TestSegmentPdfDownload:
    def test_rotations_query_burns_into_downloaded_pdf(self, tmp_path: Path, settings: Any) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        job = _job(tmp_path)
        segment = _segment(job, order=1, start=1, end=2, name="起诉状.pdf")

        resp = get_pdf_split_segment_pdf(_request(), job.id, segment.id, rotations="1:90,2:180")
        assert resp.status_code == 200
        doc = _read_pdf(resp.content)
        assert [int(doc.load_page(i).rotation) for i in range(doc.page_count)] == [90, 180]
        doc.close()

    def test_without_rotations_page_orientation_is_untouched(self, tmp_path: Path, settings: Any) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        job = _job(tmp_path)
        segment = _segment(job, order=1, start=1, end=2, name="起诉状.pdf")

        resp = get_pdf_split_segment_pdf(_request(), job.id, segment.id)
        doc = _read_pdf(resp.content)
        assert [int(doc.load_page(i).rotation) for i in range(doc.page_count)] == [0, 0]
        doc.close()

    def test_rotation_stacks_on_source_rotate(self, tmp_path: Path, settings: Any) -> None:
        """源页本来就 /Rotate 90（歪着扫的法院件），人工再转 90 → 下载读回 180。"""
        settings.MEDIA_ROOT = str(tmp_path)
        job = _job(tmp_path, rotations=[90, 0])
        segment = _segment(job, order=1, start=1, end=2, name="告知书.pdf")

        resp = get_pdf_split_segment_pdf(_request(), job.id, segment.id, rotations="1:90")
        doc = _read_pdf(resp.content)
        assert int(doc.load_page(0).rotation) == 180
        assert int(doc.load_page(1).rotation) == 0
        doc.close()

    def test_out_of_range_rotation_does_not_fail_download(self, tmp_path: Path, settings: Any) -> None:
        """脏角度只告警：律师不该因为一个越界页号丢掉整份材料。"""
        settings.MEDIA_ROOT = str(tmp_path)
        job = _job(tmp_path)
        segment = _segment(job, order=1, start=1, end=2, name="起诉状.pdf")

        resp = get_pdf_split_segment_pdf(_request(), job.id, segment.id, rotations="99:90,bad")
        assert resp.status_code == 200
        doc = _read_pdf(resp.content)
        assert [int(doc.load_page(i).rotation) for i in range(doc.page_count)] == [0, 0]
        doc.close()


class TestZipDownload:
    def test_rotations_apply_to_every_segment_in_package(self, tmp_path: Path, settings: Any) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        job = _job(tmp_path, pages=4)
        _segment(job, order=1, start=1, end=2, name="起诉状.pdf")
        _segment(job, order=2, start=3, end=4, name="证据目录.pdf")

        resp = get_pdf_split_download(_request(), job.id, ids="", rotations="1:180,2:180,3:90,4:90")
        assert resp.status_code == 200

        package = zipfile.ZipFile(BytesIO(resp.content))
        pdfs = [name for name in package.namelist() if name.endswith(".pdf")]
        assert len(pdfs) == 2
        got: list[list[int]] = []
        for name in pdfs:
            doc = _read_pdf(package.read(name))
            got.append([int(doc.load_page(i).rotation) for i in range(doc.page_count)])
            doc.close()
        assert sorted(got) == [[90, 90], [180, 180]]


class TestExtractPagesEndpoint:
    """归案链路的切页端点：`rotations` 是 Form 字段，走真实 multipart 解析。"""

    def test_form_field_reaches_slicing(self, settings: Any, tmp_path: Path) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.pdf_splitting.api.pdf_splitting_api import extract_pdf_pages

        settings.MEDIA_ROOT = str(tmp_path)
        upload = SimpleUploadedFile("卷宗.pdf", _pdf(3), content_type="application/pdf")
        resp = extract_pdf_pages(_request(), file=upload, page_start=1, page_end=3, rotations="2:270")
        assert resp.status_code == 200
        doc = _read_pdf(resp.content)
        assert [int(doc.load_page(i).rotation) for i in range(doc.page_count)] == [0, 270, 0]
        doc.close()

    def test_default_keeps_behaviour_without_rotations(self, settings: Any, tmp_path: Path) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.pdf_splitting.api.pdf_splitting_api import extract_pdf_pages

        settings.MEDIA_ROOT = str(tmp_path)
        upload = SimpleUploadedFile("卷宗.pdf", _pdf(2), content_type="application/pdf")
        resp = extract_pdf_pages(_request(), file=upload, page_start=1, page_end=2, rotations="")
        doc = _read_pdf(resp.content)
        assert [int(doc.load_page(i).rotation) for i in range(doc.page_count)] == [0, 0]
        doc.close()
