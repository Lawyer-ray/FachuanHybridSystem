"""收件箱附件缩略图：渲染、缓存、拒单三件事。

为什么这组用例值得存在（不是为覆盖率补作业）：

* **缓存命中是真的「不重算」** —— 第一次生成后把 fetcher 换成「一调就炸」的替身，
  第二次仍要成功。只断言「文件存在」证明不了缓存，重算一次也一样存在。
* **不支持的类型必须在取字节之前被拒** —— 否则为了一枚缩略图会去 IMAP 拉一份
  20MB 的 docx。这条只能靠「fetcher 未被调用」来钉。
* **同名替换要换图** —— 缓存键含 size / 文件名 / content_type，否则客户重传
  同名扫描件后列表里永远显示上一版。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.core.exceptions import NotFoundError, ValidationException
from apps.message_hub.models import InboxMessage
from apps.message_hub.services import attachment_thumbnail_service as svc
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import create_manual_message


def _pdf_bytes(*, pages: int = 2, text: str = "民事起诉状") -> bytes:
    """造一份有文字层的合成 PDF（真实 fitz 产物，不用假字节糊弄解析器）。"""
    import pymupdf as fitz

    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 96), f"{text} 第 {index + 1} 页")
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (600, 800), (250, 250, 250)).save(buf, format="PNG")
    return buf.getvalue()


def _cleanup(message: InboxMessage) -> None:
    for att in message.attachments_meta or []:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    svc.purge_message_thumbnails(message.pk)
    message.delete()


@pytest.fixture
def media_root(tmp_path: Path) -> Any:
    """附件与缩略图都落临时 MEDIA_ROOT，绝不写进工作库的 media/。"""
    with override_settings(MEDIA_ROOT=str(tmp_path / "media")):
        yield tmp_path / "media"


def _manual_message(filename: str, content: bytes) -> InboxMessage:
    return create_manual_message([SimpleUploadedFile(filename, content)])


class TestThumbnailKind:
    def test_pdf_by_content_type_or_suffix(self) -> None:
        assert svc.thumbnail_kind({"content_type": "application/pdf", "filename": "a"}) == "pdf"
        assert svc.thumbnail_kind({"content_type": "", "filename": "a.PDF"}) == "pdf"

    def test_images_by_content_type_or_suffix(self) -> None:
        assert svc.thumbnail_kind({"content_type": "image/jpeg", "filename": "a.bin"}) == "image"
        assert svc.thumbnail_kind({"content_type": "", "filename": "扫描件/1.png"}) == "image"

    def test_office_and_unknown_are_unsupported(self) -> None:
        assert svc.thumbnail_kind({"content_type": "application/msword", "filename": "a.docx"}) is None
        assert svc.thumbnail_kind({"content_type": "", "filename": "a.zip"}) is None

    def test_width_is_clamped_to_service_bounds(self) -> None:
        # 前端传 0 / 负数 / 巨大值时不该打穿服务
        assert svc.clamp_width(0) == svc.MIN_THUMB_WIDTH
        assert svc.clamp_width(-100) == svc.MIN_THUMB_WIDTH
        assert svc.clamp_width(10_000) == svc.MAX_THUMB_WIDTH
        assert svc.clamp_width(320) == 320


class TestPdfThumbnail:
    @pytest.mark.django_db
    def test_generates_jpeg_of_requested_width(self, media_root: Path) -> None:
        from PIL import Image

        msg = _manual_message("起诉状.pdf", _pdf_bytes())
        try:
            path, etag = svc.build_attachment_thumbnail(msg, 0, width=240)
            assert path.is_file()
            assert etag == path.stem
            with Image.open(path) as image:
                assert image.format == "JPEG"
                assert image.width == 240
                # 竖版 A4：高度必须比宽度大（比例没被压扁）
                assert image.height > image.width
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_second_call_hits_cache_without_touching_fetcher(
        self, media_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        msg = _manual_message("起诉状.pdf", _pdf_bytes())
        try:
            first, etag = svc.build_attachment_thumbnail(msg, 0)
            mtime = first.stat().st_mtime_ns

            def _boom(*_args: Any, **_kwargs: Any) -> Any:
                raise AssertionError("命中缓存时不该再去取附件字节")

            monkeypatch.setattr(svc, "_load_attachment_bytes", _boom)
            monkeypatch.setattr(svc, "_render_jpeg", _boom)

            second, etag2 = svc.build_attachment_thumbnail(msg, 0)
            assert (second, etag2) == (first, etag)
            assert second.stat().st_mtime_ns == mtime
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_page_out_of_range_is_rejected(self, media_root: Path) -> None:
        msg = _manual_message("起诉状.pdf", _pdf_bytes(pages=2))
        try:
            with pytest.raises(ValidationException) as exc:
                svc.build_attachment_thumbnail(msg, 0, page=9)
            assert exc.value.code == "INBOX_THUMBNAIL_PAGE_OUT_OF_RANGE"
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_second_page_can_be_requested(self, media_root: Path) -> None:
        msg = _manual_message("起诉状.pdf", _pdf_bytes(pages=3))
        try:
            page1, etag1 = svc.build_attachment_thumbnail(msg, 0, page=1)
            page2, etag2 = svc.build_attachment_thumbnail(msg, 0, page=2)
            assert page1.is_file() and page2.is_file()
            # 不同页必须是不同缓存条目，否则第 2 页会拿到第 1 页的图
            assert etag1 != etag2
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_corrupt_pdf_fails_with_render_error_not_500(self, media_root: Path) -> None:
        msg = _manual_message("坏件.pdf", b"%PDF-1.4 not really a pdf")
        try:
            with pytest.raises(ValidationException) as exc:
                svc.build_attachment_thumbnail(msg, 0)
            assert exc.value.code in {"INBOX_THUMBNAIL_RENDER_FAILED", "INBOX_THUMBNAIL_FETCH_FAILED"}
        finally:
            _cleanup(msg)


class TestImageThumbnail:
    @pytest.mark.django_db
    def test_png_becomes_jpeg(self, media_root: Path) -> None:
        from PIL import Image

        msg = _manual_message("现场照片.png", _png_bytes())
        try:
            path, _etag = svc.build_attachment_thumbnail(msg, 0, width=200)
            with Image.open(path) as image:
                assert image.format == "JPEG"
                assert image.width == 200
        finally:
            _cleanup(msg)


class TestRejections:
    @pytest.mark.django_db
    def test_unsupported_type_rejected_before_fetching_bytes(
        self, media_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        msg = _manual_message("判决书.docx", b"PK\x03\x04fake-docx")
        try:

            def _boom(*_args: Any, **_kwargs: Any) -> Any:
                raise AssertionError("不支持的类型必须在取字节之前就被拒")

            monkeypatch.setattr(svc, "_load_attachment_bytes", _boom)
            with pytest.raises(ValidationException) as exc:
                svc.build_attachment_thumbnail(msg, 0)
            assert exc.value.code == "INBOX_NO_THUMBNAIL"
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_missing_part_index_is_404(self, media_root: Path) -> None:
        msg = _manual_message("起诉状.pdf", _pdf_bytes())
        try:
            with pytest.raises(NotFoundError):
                svc.build_attachment_thumbnail(msg, 7)
        finally:
            _cleanup(msg)


class TestCacheKey:
    def test_key_changes_when_content_identity_changes(self) -> None:
        base = {"size": 100, "filename": "a.pdf", "content_type": "application/pdf"}
        key = svc.thumbnail_cache_key(1, 0, base, page=1, width=320)
        # 同名重传（size 变了）：必须换键，否则永远显示上一版
        replaced = dict(base, size=101)
        assert svc.thumbnail_cache_key(1, 0, replaced, page=1, width=320) != key
        # 渲染参数变了也要换键
        assert svc.thumbnail_cache_key(1, 0, base, page=2, width=320) != key
        assert svc.thumbnail_cache_key(1, 0, base, page=1, width=640) != key
        # 同样的输入必须稳定
        assert svc.thumbnail_cache_key(1, 0, base, page=1, width=320) == key


class TestPurge:
    @pytest.mark.django_db
    def test_purge_removes_message_directory(self, media_root: Path) -> None:
        msg = _manual_message("起诉状.pdf", _pdf_bytes())
        try:
            path, _etag = svc.build_attachment_thumbnail(msg, 0)
            assert path.is_file()
            removed = svc.purge_message_thumbnails(msg.pk)
            assert removed == 1
            assert not svc.thumbnail_dir(msg.pk).exists()
            # 幂等：没有目录时返回 0，不抛
            assert svc.purge_message_thumbnails(msg.pk) == 0
        finally:
            _cleanup(msg)
