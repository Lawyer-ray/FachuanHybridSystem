"""附件页图渲染 —— 扫描件/图片不该对模型不可见。

本轮 ``chars: 0`` 故障的三层根因里，这一层是「扫描件压根没有任何文本」：
PDF 无文字层 → ``page.get_text()`` 空串 → 解析端点仍报 ``success=True`` →
模型拿到空正文。修法是把它渲染成图片走视觉通道，本文件验证该通道的每个
口径都站得住：页粒度文字层判断、加密/空/超大/越界各自不同的错误码、
体积约束（长边 1568px、单页 1.5MB、dpi 降档）、以及缓存的命中与淘汰。

测试 PDF 全部用 PyMuPDF **现场生成**（文字层 / 纯图片扫描版 / 加密），
不引入外部 fixture 文件——fixture 二进制在大仓里既难看 diff 又不可审。
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings

from apps.agent.services import attachment_render as render

pytestmark = pytest.mark.django_db


#: 每个用例独立 MEDIA_ROOT，缓存互不串味。
@pytest.fixture(autouse=True)
def _isolated_media(tmp_path: Path) -> Any:
    media = tmp_path / "media"
    with override_settings(MEDIA_ROOT=str(media)):
        yield media


# ── PDF 生成工具 ──────────────────────────────────────────────────


#: 一份「有真实文字层」的正文，长度明显超过 MIN_TEXT_CHARS（50）
_TEXT_LAYER_BODY = "甲方应按约定支付价款，逾期承担违约责任。" * 6


def _text_pdf(pages: int = 3) -> bytes:
    """带真实文字层的 PDF（每页正文远超 MIN_TEXT_CHARS）。

    必须指定 CJK 字体（``fontname="china-s"``）：PyMuPDF 默认 Helvetica 没有中文字形，
    写进去只是一串 ``·``——既不真实，也会让「文字层长度」判断在中文材料上失真。
    """
    import pymupdf as fitz

    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((72, 80), f"第 {index + 1} 页", fontsize=11, fontname="china-s")
        page.insert_text((72, 110), _TEXT_LAYER_BODY, fontsize=9, fontname="china-s")
    payload = doc.tobytes()
    doc.close()
    return payload


def _scanned_pdf(pages: int = 1, *, size: tuple[int, int] = (800, 1100), noise: bool = False) -> bytes:
    """只有一张位图、没有文字层的 PDF —— 模拟扫描件。"""
    import pymupdf as fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(0, 0, 595, 842), stream=_jpeg_image(size, noise=noise))
    payload = doc.tobytes()
    doc.close()
    return payload


def _jpeg_image(size: tuple[int, int] = (800, 1100), *, noise: bool = False, quality: int = 70) -> bytes:
    from PIL import Image, ImageDraw

    if noise:
        # 随机噪点最吃体积：用来逼出「降 dpi 仍然超限」与「必须降档」的分支
        import random

        rng = random.Random(20260601)
        raw = bytes(rng.getrandbits(8) for _ in range(size[0] * size[1] * 3))
        image = Image.frombytes("RGB", size, raw)
    else:
        image = Image.new("RGB", size, (250, 250, 250))
        ImageDraw.Draw(image).text((60, 60), "SCANNED CONTRACT PAGE", fill=(10, 10, 10))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _encrypted_pdf() -> bytes:
    """需要用户口令才能打开（``authenticate("")`` 过不去）。"""
    import pymupdf as fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "机密条款 " * 12, fontname="china-s")
    payload = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="user-secret")
    doc.close()
    return payload


def _mixed_pdf() -> bytes:
    """第 1 页有文字层、第 2 页纯扫描 —— 验证文字层判断是按页而不是按文档。"""
    import pymupdf as fitz

    text_doc = fitz.open(stream=_text_pdf(1), filetype="pdf")
    scan_doc = fitz.open(stream=_scanned_pdf(1), filetype="pdf")
    text_doc.insert_pdf(scan_doc)
    payload = text_doc.tobytes()
    text_doc.close()
    scan_doc.close()
    return payload


# ── 页范围解析 ────────────────────────────────────────────────────


class TestParsePages:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("1-3", [1, 2, 3]),
            ([1, 5], [1, 5]),
            (7, [7]),
            ("7", [7]),
            ("1,3,5", [1, 3, 5]),
            ("3-1", None),
            (None, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
            ("all", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
        ],
    )
    def test_supported_forms(self, spec: Any, expected: list[int] | None) -> None:
        if expected is None:
            # 区间逆序是用户错误，不能悄悄交换端点（会让模型读错页）
            with pytest.raises(ValueError):
                render.parse_pages(spec, total_pages=10, max_pages=10)
            return
        pages, truncated = render.parse_pages(spec, total_pages=10, max_pages=10)
        assert pages == expected
        assert truncated == 0

    def test_out_of_range_raises(self) -> None:
        for spec in ("11", "0", "1-12", [1, 99], "-1"):
            with pytest.raises(ValueError):
                render.parse_pages(spec, total_pages=10, max_pages=10)

    def test_truncates_beyond_max_pages(self) -> None:
        pages, truncated = render.parse_pages("all", total_pages=10, max_pages=4)
        assert pages == [1, 2, 3, 4]
        # 截断必须报数，否则调用方会以为「文档就 4 页」
        assert truncated == 6

    def test_garbage_spec_raises(self) -> None:
        with pytest.raises(ValueError):
            render.parse_pages("上", total_pages=10, max_pages=10)


# ── PDF 渲染 ──────────────────────────────────────────────────────


class TestRenderPdfTextLayer:
    def test_text_page_returns_text_not_image(self) -> None:
        pages = render.render_pdf_pages(_text_pdf(2), [1, 2])
        assert [p.strategy for p in pages] == [render.RenderStrategy.TEXT, render.RenderStrategy.TEXT]
        assert all(len(p.text) >= render.MIN_TEXT_CHARS for p in pages)
        # 有文字层的页不该烧视觉 token
        assert all(p.image_bytes is None for p in pages)

    def test_text_layer_judged_per_page(self) -> None:
        pages = render.render_pdf_pages(_mixed_pdf(), [1, 2])
        assert pages[0].strategy is render.RenderStrategy.TEXT
        assert pages[1].strategy is render.RenderStrategy.PAGE_IMAGE
        assert pages[1].image_bytes

    def test_short_text_under_threshold_gets_image(self) -> None:
        """页脚只有「第 1 页」这类零星文字的扫描页，仍必须出图。"""
        import pymupdf as fitz

        doc = fitz.open()
        scan = fitz.open(stream=_scanned_pdf(1), filetype="pdf")
        doc.insert_pdf(scan)
        doc[0].insert_text((72, 800), "第 1 页", fontname="china-s")
        payload = doc.tobytes()
        doc.close()
        scan.close()

        (page,) = render.render_pdf_pages(payload, [1])
        assert page.strategy is render.RenderStrategy.PAGE_IMAGE
        assert page.image_bytes


class TestRenderPdfScanned:
    def test_scanned_page_rendered_as_png(self) -> None:
        (page,) = render.render_pdf_pages(_scanned_pdf(1), [1], dpi=150)
        assert page.strategy is render.RenderStrategy.PAGE_IMAGE
        assert page.mime == "image/png"
        assert page.image_bytes
        assert page.image_bytes.startswith(b"\x89PNG")
        assert page.dpi == 150
        assert page.error is None

    def test_jpeg_format(self) -> None:
        (page,) = render.render_pdf_pages(_scanned_pdf(1), [1], dpi=150, fmt="jpeg")
        assert page.mime == "image/jpeg"
        assert page.image_bytes and page.image_bytes.startswith(b"\xff\xd8")

    def test_long_edge_capped_at_1568(self) -> None:
        """A4 在 300dpi 下是 2480×3508，必须被压到长边 1568。"""
        (page,) = render.render_pdf_pages(_scanned_pdf(1), [1], dpi=300)
        assert page.image_bytes
        assert max(page.width, page.height) == render.MAX_EDGE_PX

    def test_dpi_ladder_downshifts_until_under_byte_limit(self) -> None:
        """噪点扫描页在 300dpi 下远超 1.5MB，必须逐档降到能过的第一档。"""
        payload = _scanned_pdf(1, size=(2550, 3300), noise=True)
        (page,) = render.render_pdf_pages(payload, [1], dpi=300)
        assert page.error is None
        assert page.image_bytes
        assert len(page.image_bytes) <= render.MAX_PAGE_BYTES
        # 每档都超限时一直降到 72 才不会掉页；这里锁「确实降过档」而不是猜降了几档
        assert page.dpi in render.DPI_LADDER

    def test_dpi_ladder_stops_at_first_passing_level(self) -> None:
        """首档就合格时不该继续降档（dpi 越高模型看得越清）。"""
        payload = _scanned_pdf(1)
        (page,) = render.render_pdf_pages(payload, [1], dpi=150)
        assert page.dpi == 150

    def test_too_large_page_reported_not_dropped(self) -> None:
        """把字节上限压到不可能达标，该页必须留在结果里并带 too_large。"""
        payload = _scanned_pdf(1, size=(800, 1100), noise=True)
        (page,) = render.render_pdf_pages(payload, [1], dpi=96, size_limit=512)
        assert page.error is render.RenderError.TOO_LARGE
        assert page.image_bytes is None
        assert page.detail


class TestRenderPdfEncrypted:
    def test_encrypted_pdf_returns_encrypted_error(self) -> None:
        pages = render.render_pdf_pages(_encrypted_pdf(), [1])
        assert pages[0].error is render.RenderError.ENCRYPTED
        assert pages[0].image_bytes is None

    def test_empty_password_encryption_is_unlocked(self) -> None:
        """权限加密（无口令）要能读，不要把它也当 encrypted 拒掉。"""
        import pymupdf as fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 100), _TEXT_LAYER_BODY, fontsize=9, fontname="china-s")
        payload = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="")
        doc.close()

        (page,) = render.render_pdf_pages(payload, [1])
        assert page.error is None
        assert page.strategy is render.RenderStrategy.TEXT

    def test_page_beyond_eof_marked_out_of_range(self) -> None:
        (page,) = render.render_pdf_pages(_text_pdf(1), [5])
        assert page.error is render.RenderError.PAGE_OUT_OF_RANGE


# ── 图片附件 ──────────────────────────────────────────────────────


class TestRenderImage:
    def test_jpeg_passthrough_untouched(self) -> None:
        """合规尺寸的 JPEG 原样交付：重编码只会掉质量。"""
        source = _jpeg_image((900, 1200))
        page = render.render_image(source, "image/jpeg")
        assert page.strategy is render.RenderStrategy.SOURCE_IMAGE
        assert page.image_bytes == source
        assert (page.width, page.height) == (900, 1200)
        assert page.error is None

    def test_png_passthrough(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (600, 800), (30, 60, 90)).save(buf, format="PNG")
        source = buf.getvalue()
        page = render.render_image(source, "image/png")
        assert page.image_bytes == source

    def test_oversized_image_downscaled(self) -> None:
        source = _jpeg_image((3000, 4000))
        page = render.render_image(source, "image/jpeg")
        assert page.image_bytes
        assert max(page.width, page.height) <= render.MAX_EDGE_PX

    def test_tiff_converted(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (700, 900), (200, 200, 200)).save(buf, format="TIFF")
        page = render.render_image(buf.getvalue(), "image/tiff")
        assert page.error is None
        assert page.image_bytes and page.image_bytes.startswith(b"\x89PNG")

    def test_corrupt_image_reports_error_not_blank(self) -> None:
        page = render.render_image(b"not-an-image", "image/tiff")
        assert page.error is render.RenderError.UNSUPPORTED_MIME
        assert page.image_bytes is None


# ── 缓存 ──────────────────────────────────────────────────────────


class TestRenderCache:
    def test_second_render_hits_cache_and_is_much_faster(self) -> None:
        payload = _scanned_pdf(1, size=(2550, 3300))
        first = render.render_pdf_pages(payload, [1], attachment_id="att-1", dpi=300)[0]
        started = time.monotonic()
        second = render.render_pdf_pages(payload, [1], attachment_id="att-1", dpi=300)[0]
        cached_ms = (time.monotonic() - started) * 1000

        assert second.cached is True
        assert second.image_bytes == first.image_bytes
        # 命中缓存 = 读盘 + 返回，不该再走 pixmap 渲染（渲染这一页实测数百毫秒）
        assert cached_ms < 100, f"缓存命中也花了 {cached_ms:.1f}ms"

    def test_text_page_bypasses_cache(self) -> None:
        """文字页不出图，自然也不写缓存（否则缓存里全是没人用的图）。"""
        render.render_pdf_pages(_text_pdf(1), [1], attachment_id="att-text")
        assert list(render.cache_root().rglob("*.bin")) == []

    def test_lru_eviction_removes_oldest_first(self) -> None:
        cache = render.RenderCache(render.cache_root(), ttl_seconds=3600, max_bytes=2000)
        cache.put("a" * 64, b"x" * 900, 10, 10)
        cache.put("b" * 64, b"y" * 900, 10, 10)
        # 把 a 的 mtime 拨到 1 小时前，让「最旧」与「最早写入」区分开
        old = time.time() - 3600
        import os

        os.utime(cache.path_for("a" * 64), (old, old))

        cache.put("c" * 64, b"z" * 900, 10, 10)  # 触发淘汰：3×908 > 2000
        assert cache.get("a" * 64) is None
        assert cache.get("b" * 64) is not None
        assert cache.get("c" * 64) is not None

    def test_ttl_expiry(self) -> None:
        cache = render.RenderCache(render.cache_root(), ttl_seconds=60, max_bytes=10**6)
        cache.put("d" * 64, b"payload", 4, 4)
        assert cache.get("d" * 64, now=time.time() + 10) is not None
        assert cache.get("d" * 64, now=time.time() + 600) is None

    def test_key_changes_with_source_fingerprint(self) -> None:
        """覆盖写入后必须失配，否则模型会看到上一份文件的图。"""
        cache = render.RenderCache(render.cache_root())
        k1 = cache.key("att", 1, 150, "png", source_size=100, source_mtime=1000.0)
        k2 = cache.key("att", 1, 150, "png", source_size=200, source_mtime=1000.0)
        k3 = cache.key("att", 1, 150, "png", source_size=100, source_mtime=2000.0)
        assert len({k1, k2, k3}) == 3

    def test_cache_dir_separate_from_attachments(self, _isolated_media: Path) -> None:
        """缓存独立于 agent_attachments/：附件清理按该目录扫物理文件，混在一起会被误删。"""
        assert render.cache_root().parent == _isolated_media
        assert render.cache_root().name == "agent_attachment_cache"


# ── 服务入口（attachments.render_attachment_pages）────────────────


def _make_attachment(payload: bytes, *, filename: str, mime: str) -> Any:
    """真实落盘 + 落库的附件，走 default_storage 读回（和线上路径一致）。"""
    from apps.agent.models import AgentAttachment, AgentSession
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name=f"渲染-{filename}")
    user = Lawyer.objects.create_user(username=f"u-{filename}", password="x-test-12345678", law_firm=firm)
    session = AgentSession.objects.create(user=user, origin=AgentSession.Origin.CHAT)
    path = f"agent_attachments/2026/06/{filename}"
    default_storage.save(path, io.BytesIO(payload))
    attachment = AgentAttachment.objects.create(
        session=session,
        user=user,
        filename=filename,
        storage_path=path,
        mime=mime,
        size=len(payload),
    )
    return attachment


class TestRenderAttachmentPages:
    def test_pdf_scanned_attachment(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_scanned_pdf(1), filename="scan.pdf", mime="application/pdf")
        result = render_attachment_pages(attachment, pages="1", dpi=150, user_id=7)

        assert result.ok
        assert result.total_pages == 1
        assert result.error is None
        assert result.pages[0].strategy is render.RenderStrategy.PAGE_IMAGE

    def test_pdf_text_attachment_returns_text(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_text_pdf(2), filename="contract.pdf", mime="application/pdf")
        result = render_attachment_pages(attachment, pages="1-2", user_id=7)

        assert result.ok
        assert [p.strategy for p in result.pages] == [render.RenderStrategy.TEXT] * 2

    def test_page_out_of_range_is_error(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_text_pdf(2), filename="short.pdf", mime="application/pdf")
        result = render_attachment_pages(attachment, pages="9", user_id=7)

        assert result.error is render.RenderError.PAGE_OUT_OF_RANGE
        assert not result.ok
        assert result.total_pages == 2

    def test_encrypted_attachment_is_error(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_encrypted_pdf(), filename="locked.pdf", mime="application/pdf")
        result = render_attachment_pages(attachment, pages="1", user_id=7)

        assert result.error is render.RenderError.ENCRYPTED
        assert not result.ok

    def test_image_attachment(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        source = _jpeg_image((900, 1200))
        attachment = _make_attachment(source, filename="photo.jpg", mime="image/jpeg")
        result = render_attachment_pages(attachment, user_id=7)

        assert result.ok
        assert result.pages[0].image_bytes == source

    def test_image_page_out_of_range(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_jpeg_image(), filename="one.jpg", mime="image/jpeg")
        result = render_attachment_pages(attachment, pages="2", user_id=7)
        assert result.error is render.RenderError.PAGE_OUT_OF_RANGE

    def test_unsupported_mime_is_error(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(b"hello", filename="note.txt", mime="text/plain")
        result = render_attachment_pages(attachment, user_id=7)
        assert result.error is render.RenderError.UNSUPPORTED_MIME
        assert not result.ok

    def test_missing_physical_file_is_not_found(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_text_pdf(1), filename="gone.pdf", mime="application/pdf")
        # 模拟「记录在、文件已丢」：直接删物理文件，不碰记录
        Path(default_storage.path(attachment.storage_path)).unlink()
        result = render_attachment_pages(attachment, user_id=7)
        assert result.error is render.RenderError.NOT_FOUND

    def test_truncated_pages_reported(self) -> None:
        from apps.agent.services.attachments import render_attachment_pages

        attachment = _make_attachment(_text_pdf(5), filename="long.pdf", mime="application/pdf")
        result = render_attachment_pages(attachment, pages="all", max_pages=2, user_id=7)

        assert [p.page_no for p in result.pages] == [1, 2]
        assert result.truncated_pages == 3
