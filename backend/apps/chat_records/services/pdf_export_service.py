"""PDF 导出服务 —— 负责将截图列表渲染为 PDF 字节流。"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from typing import Any

from django.core.files.base import ContentFile

from apps.chat_records.models import ChatRecordProject, ChatRecordScreenshot
from apps.core.exceptions import ValidationException

from .export_service import ExportLayout

logger = logging.getLogger(__name__)

_LANCZOS: Any = None


def _get_lanczos() -> Any:
    """延迟获取 Pillow LANCZOS 常量，避免模块级副作用。"""
    global _LANCZOS  # noqa: PLW0603
    if _LANCZOS is None:
        from PIL import Image as _Img

        _LANCZOS = getattr(_Img, "Resampling", _Img).LANCZOS
    return _LANCZOS


class PdfExportService:
    """单一职责：生成 PDF 导出文件。"""

    def export_pdf(
        self,
        *,
        project: ChatRecordProject,
        screenshots: list[ChatRecordScreenshot],
        layout: ExportLayout,
        filename: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ContentFile[bytes]:
        content = self._build_pdf_bytes(
            project=project,
            screenshots=screenshots,
            layout=layout,
            progress_callback=progress_callback,
        )
        return ContentFile(content, name=filename)

    def _build_pdf_bytes(
        self,
        *,
        project: ChatRecordProject,
        screenshots: list[ChatRecordScreenshot],
        layout: ExportLayout,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> bytes:
        if not screenshots:
            raise ValidationException("没有截图,无法导出")

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        page_width, page_height = A4
        margin = 36
        header_height = 24 if layout.header_text else 0
        footer_height = 24 if layout.show_page_number else 0
        content_top = page_height - margin - header_height
        content_bottom = margin + footer_height
        content_height = max(1, content_top - content_bottom)
        content_width = page_width - margin * 2

        cols = 1 if layout.images_per_page == 1 else 2
        cell_w = content_width / cols
        cell_h = content_height / 1  # rows=1

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        font_name = self._register_pdf_font()

        total_pages = (len(screenshots) + layout.images_per_page - 1) // layout.images_per_page
        processed = 0
        total = len(screenshots)

        for page_index, i in enumerate(range(0, len(screenshots), layout.images_per_page), 1):
            batch = screenshots[i : i + layout.images_per_page]

            if layout.header_text:
                c.setFont(font_name, 12)
                c.drawString(margin, page_height - margin - 12, layout.header_text)

            for j, shot in enumerate(batch):
                col = j % cols
                x0 = margin + col * cell_w
                y0 = content_top - cell_h
                processed += self._draw_pdf_image(c, shot, x0, y0, cell_w, cell_h, font_name)
                if progress_callback:
                    progress_callback(processed, total, "生成中")

            if layout.show_page_number:
                c.setFont(font_name, 9)
                page_text = (
                    f"第 {page_index}/{total_pages} 页"
                    if font_name == "STSong-Light"
                    else f"{page_index}/{total_pages}"
                )
                c.drawRightString(page_width - margin, margin - 4, page_text)

            c.showPage()

        c.save()
        return buf.getvalue()

    def _register_pdf_font(self) -> str:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont

            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            return "STSong-Light"
        except Exception:
            logger.exception(
                "PDF 字体注册失败，回退到 Helvetica",
                extra={"font": "STSong-Light"},
            )
            return "Helvetica"

    def _draw_pdf_image(
        self,
        c: Any,
        shot: Any,
        x0: float,
        y0: float,
        cell_w: float,
        cell_h: float,
        font_name: str,
    ) -> int:
        from PIL import Image
        from reportlab.lib.utils import ImageReader

        try:
            with Image.open(shot.image.path) as img:
                rgb_img = img.convert("RGB")
                iw, ih = rgb_img.size
        except Exception:
            logger.exception(
                "PDF 截图图片打开失败",
                extra={"screenshot_id": getattr(shot, "id", None)},
            )
            return 1

        max_w = cell_w - 12
        max_h = cell_h - 28
        scale = min(max_w / iw, max_h / ih, 1.0)
        draw_w = iw * scale
        draw_h = ih * scale
        draw_x = x0 + (cell_w - draw_w) / 2
        draw_y = y0 + (cell_h - draw_h) / 2

        try:
            with Image.open(shot.image.path) as img:
                rgb_img = img.convert("RGB")
                rgb_img.thumbnail(
                    (max(1, int(draw_w * 2)), max(1, int(draw_h * 2))),
                    _get_lanczos(),
                )
                img_buf = io.BytesIO()
                rgb_img.save(img_buf, format="JPEG", quality=82, optimize=True)
                img_buf.seek(0)
                img_reader = ImageReader(img_buf)
        except Exception:
            logger.exception(
                "PDF 截图缩略图生成失败",
                extra={"screenshot_id": getattr(shot, "id", None)},
            )
            return 1

        c.drawImage(
            img_reader, draw_x, draw_y,
            width=draw_w, height=draw_h, preserveAspectRatio=True,
        )

        caption = (shot.title or "").strip()
        if caption:
            c.setFont(font_name, 10)
            c.drawString(x0 + 6, y0 + 12, caption[:60])

        return 1
