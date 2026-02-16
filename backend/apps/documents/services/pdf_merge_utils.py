"""Business logic services."""

from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Any

from apps.core.exceptions import BusinessException

logger = logging.getLogger(__name__)


def convert_image_to_pdf(image_path: str) -> str:
    try:
        from PIL import Image
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        img = Image.open(image_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")  # type: ignore[assignment]

        page_width, page_height = A4
        margin = 50
        max_width = page_width - 2 * margin
        max_height = page_height - 2 * margin

        img_width, img_height = img.size
        scale = min(max_width / img_width, max_height / img_height)
        new_width = img_width * scale
        new_height = img_height * scale

        c = canvas.Canvas(pdf_path, pagesize=A4)
        x = (page_width - new_width) / 2
        y = (page_height - new_height) / 2

        fd, temp_img_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        img.save(temp_img_path, "JPEG", quality=95)

        c.drawImage(temp_img_path, x, y, new_width, new_height)
        c.save()

        os.remove(temp_img_path)
        return pdf_path

    except Exception as e:
        raise BusinessException(
            message=f"图片转换 PDF 失败: {e!s}",
            code="IMAGE_CONVERSION_FAILED",
            errors={"image_path": image_path, "error": str(e)},
        ) from e


def convert_docx_to_pdf(docx_path: str) -> str:
    try:
        try:
            from docx2pdf import convert

            fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            convert(docx_path, pdf_path)
            return pdf_path
        except ImportError:
            pass

        from docx import Document
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate

        doc = Document(docx_path)
        fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        pdf_doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story: list[Any] = []

        for para in doc.paragraphs:
            if para.text.strip():
                story.append(Paragraph(para.text, styles["Normal"]))

        if story:
            pdf_doc.build(story)
        else:
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(pdf_path, pagesize=A4)
            c.save()

        return pdf_path

    except Exception as e:
        raise BusinessException(
            message=f"Word 转换 PDF 失败: {e!s}",
            code="DOCX_CONVERSION_FAILED",
            errors={"docx_path": docx_path, "error": str(e)},
        ) from e


def add_page_numbers(pdf_input: io.BytesIO, start_page: int = 1) -> bytes:
    try:
        from io import BytesIO

        import pikepdf
        from reportlab.pdfgen import canvas

        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont

            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            font_name = "STSong-Light"
        except Exception:
            logger.exception("操作失败")
            font_name = "Helvetica"

        pdf_input.seek(0)
        original_pdf = pikepdf.open(pdf_input)

        output_pdf = pikepdf.Pdf.new()

        for i, page in enumerate(original_pdf.pages):
            page_num = start_page + i

            mediabox = page.mediabox
            page_width = float(mediabox[2] - mediabox[0])  # type: ignore[operator]
            page_height = float(mediabox[3] - mediabox[1])  # type: ignore[operator]

            overlay_buffer = BytesIO()
            c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
            c.setFont(font_name, 10)

            if font_name == "STSong-Light":
                page_text = f"第 {page_num} 页"
            else:
                page_text = f"- {page_num} -"

            text_width = c.stringWidth(page_text, font_name, 10)
            x = (page_width - text_width) / 2
            y = 30

            c.drawString(x, y, page_text)
            c.save()

            overlay_buffer.seek(0)
            overlay_pdf = pikepdf.open(overlay_buffer)
            overlay_page = overlay_pdf.pages[0]

            page.add_overlay(overlay_page)  # type: ignore[call-arg]
            output_pdf.pages.append(page)

        output_buffer = BytesIO()
        output_pdf.save(output_buffer)
        output_buffer.seek(0)

        return output_buffer.read()

    except Exception:
        logger.exception("操作失败")

        pdf_input.seek(0)
        return pdf_input.read()
