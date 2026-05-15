"""Business logic services."""

from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image as _PILImage

from apps.core.exceptions import BusinessException

logger = logging.getLogger(__name__)


def convert_image_to_pdf(image_path: str) -> str:
    try:
        from PIL import Image
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        img: _PILImage.Image = Image.open(image_path)
        if img.mode == "RGBA":
            img = img.convert("RGB")

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

        Path(temp_img_path).unlink(missing_ok=True)
        return pdf_path

    except Exception as e:
        raise BusinessException(
            message=f"图片转换 PDF 失败: {e!s}",
            code="IMAGE_CONVERSION_FAILED",
            errors={"image_path": image_path, "error": str(e)},
        ) from e


def _find_libreoffice() -> str | None:
    """查找本机 LibreOffice 可执行文件路径"""
    import platform
    import shutil

    # 1. PATH 中查找
    path = shutil.which("soffice") or shutil.which("libreoffice")
    if path:
        return path

    # 2. macOS 标准安装路径
    if platform.system() == "Darwin":
        mac_paths = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/Applications/OpenOffice.app/Contents/MacOS/soffice",
        ]
        for p in mac_paths:
            if Path(p).exists():
                return p

    # 3. Linux 标准安装路径
    if platform.system() == "Linux":
        linux_paths = [
            "/usr/bin/libreoffice",
            "/usr/bin/soffice",
            "/usr/local/bin/libreoffice",
            "/snap/bin/libreoffice",
        ]
        for p in linux_paths:
            if Path(p).exists():
                return p

    return None


def _convert_via_libreoffice(docx_path: str) -> str | None:
    """使用 LibreOffice headless 模式转换 docx → pdf（最高质量）"""
    import subprocess

    soffice = _find_libreoffice()
    if not soffice:
        return None

    # LibreOffice 输出到临时目录，文件名与源文件相同但后缀为 .pdf
    output_dir = tempfile.mkdtemp()
    try:
        cmd = [
            soffice,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            str(docx_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("LibreOffice 转换失败: %s", result.stderr)
            return None

        # 找到输出文件
        src_stem = Path(docx_path).stem
        pdf_path = Path(output_dir) / f"{src_stem}.pdf"
        if not pdf_path.exists():
            logger.warning("LibreOffice 未生成 PDF: %s", output_dir)
            return None

        # 移动到标准临时文件（避免目录残留）
        fd, final_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        import shutil as shutil_mod
        shutil_mod.move(str(pdf_path), final_path)
        return final_path

    except subprocess.TimeoutExpired:
        logger.warning("LibreOffice 转换超时: %s", docx_path)
        return None
    except Exception as e:
        logger.warning("LibreOffice 转换异常: %s", e)
        return None
    finally:
        import shutil as shutil_mod
        shutil_mod.rmtree(output_dir, ignore_errors=True)


def convert_docx_to_pdf(docx_path: str) -> str:
    try:
        # 1. 优先使用本机 LibreOffice（最高质量，完美保留原始排版）
        lo_result = _convert_via_libreoffice(docx_path)
        if lo_result:
            return lo_result

        # 2. 回退：mammoth + weasyprint（中等质量，中文支持良好）
        try:
            import mammoth
            import weasyprint

            with open(docx_path, "rb") as f:
                result = mammoth.convert_to_html(f)
                html_body = result.value

            html_doc = (
                '<!DOCTYPE html><html><head><meta charset="utf-8">'
                '<style>'
                'body { font-family: "SimSun", "STSong", "PingFang SC", "Microsoft YaHei", serif; font-size: 12pt; margin: 2cm; }'
                'p { margin: 0.5em 0; text-indent: 2em; }'
                'h1, h2, h3 { text-align: center; }'
                'table { border-collapse: collapse; width: 100%; }'
                'td, th { border: 1px solid #000; padding: 4px 8px; }'
                '</style></head><body>'
                + html_body +
                '</body></html>'
            )

            fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            weasyprint.HTML(string=html_doc).write_pdf(pdf_path)
            return pdf_path
        except ImportError:
            pass

        # 3. 最终回退：reportlab（中文支持差，仅作为兜底）
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
            page_width = float(mediabox[2]) - float(mediabox[0])
            page_height = float(mediabox[3]) - float(mediabox[1])

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
