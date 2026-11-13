"""`POST /pdf-splitting/extract-pages`：按页范围切出小 PDF。

归案时前端拿它把材料包的分段切成独立 PDF 再上传，否则每份「材料」都是同一份
完整卷宗。测试用的 PDF 由 pymupdf 现场生成，不依赖任何真实卷宗文件。
"""

from __future__ import annotations

from typing import Any

import pymupdf as fitz
import pytest
from django.test import RequestFactory

from apps.core.exceptions import ValidationException
from apps.pdf_splitting.api.pdf_splitting_api import extract_pdf_pages
from apps.pdf_splitting.services.job_service import PdfSplitJobService

_factory = RequestFactory()

PAGE_COUNT = 5


def _build_pdf(page_count: int = PAGE_COUNT) -> bytes:
    """造一份每页自带页号的 PDF：切完后按文本就能验出切的是哪几页。"""
    doc = fitz.open()
    try:
        for no in range(1, page_count + 1):
            page = doc.new_page()
            page.insert_text((72, 72), f"PAGE-{no}")
        return doc.tobytes()  # type: ignore[no-any-return]
    finally:
        doc.close()


class _Upload:
    """UploadedFile 的最小替身：端点只用到 size 与 read()。"""

    def __init__(self, content: bytes, name: str = "pack.pdf") -> None:
        self.name = name
        self.size = len(content)
        self._content = content

    def read(self, size: int = -1) -> bytes:
        return self._content


def _extract(content: bytes, page_start: int, page_end: int) -> Any:
    request = _factory.post("/")
    return extract_pdf_pages(request, file=_Upload(content), page_start=page_start, page_end=page_end)


def _texts(pdf_bytes: bytes) -> list[str]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [page.get_text().strip() for page in doc]


def _errors(exc: pytest.ExceptionInfo[ValidationException]) -> dict[str, Any]:
    return dict(exc.value.errors)


class TestExtractPdfPages:
    def test_returns_pdf_bytes_for_whole_range(self) -> None:
        response = _extract(_build_pdf(), 1, PAGE_COUNT)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert "pages_1-5.pdf" in response["Content-Disposition"]
        assert _texts(response.content) == [f"PAGE-{no}" for no in range(1, PAGE_COUNT + 1)]

    def test_cuts_exact_page_window(self) -> None:
        """中间一段：只要 2..4 页，且首尾都对（1 起、含两端）。"""
        response = _extract(_build_pdf(), 2, 4)

        assert _texts(response.content) == ["PAGE-2", "PAGE-3", "PAGE-4"]

    def test_single_page_segment(self) -> None:
        response = _extract(_build_pdf(), 3, 3)

        assert _texts(response.content) == ["PAGE-3"]

    def test_rejects_page_start_below_one(self) -> None:
        with pytest.raises(ValidationException) as exc:
            _extract(_build_pdf(), 0, 2)

        assert _errors(exc) == {"page_start": 0}

    def test_rejects_page_end_before_page_start(self) -> None:
        with pytest.raises(ValidationException) as exc:
            _extract(_build_pdf(), 3, 2)

        assert _errors(exc) == {"page_end": 2}

    def test_rejects_range_beyond_page_count(self) -> None:
        with pytest.raises(ValidationException) as exc:
            _extract(_build_pdf(), 1, PAGE_COUNT + 1)

        errors = _errors(exc)
        assert errors["page_end"] == PAGE_COUNT + 1
        assert errors["total_pages"] == PAGE_COUNT

    def test_rejects_empty_upload(self) -> None:
        with pytest.raises(ValidationException) as exc:
            _extract(b"", 1, 1)

        assert _errors(exc) == {"file": "文件不能为空"}

    def test_rejects_upload_over_size_limit(self) -> None:
        # 只改 size，不真造 1GB 字节（口径与 /jobs 共用同一个常量）
        oversized = _Upload(b"%PDF-1.4")
        oversized.size = PdfSplitJobService.MAX_FILE_SIZE + 1

        with pytest.raises(ValidationException) as exc:
            extract_pdf_pages(_factory.post("/"), file=oversized, page_start=1, page_end=1)

        limit_mb = PdfSplitJobService.MAX_FILE_SIZE // 1024 // 1024
        assert _errors(exc) == {"file": f"文件大小不能超过 {limit_mb}MB"}

    def test_rejects_broken_pdf(self) -> None:
        with pytest.raises(ValidationException) as exc:
            _extract(b"not a pdf at all", 1, 1)

        assert _errors(exc) == {"file": "PDF 文件损坏或格式不正确"}


@pytest.mark.django_db
def test_route_accepts_multipart_upload(authenticated_client: Any) -> None:
    """走真实路由：`file` + `page_start/page_end` 三个表单字段能正常绑定。"""
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("pack.pdf", _build_pdf(), content_type="application/pdf")
    resp = authenticated_client.post(
        "/api/v1/pdf-splitting/extract-pages", {"file": upload, "page_start": 2, "page_end": 3}
    )

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert _texts(resp.content) == ["PAGE-2", "PAGE-3"]
