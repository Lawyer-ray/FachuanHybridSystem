from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFTextExtractor:
    """使用 pdfplumber 从电子发票 PDF 中提取文本层内容"""

    MIN_TEXT_THRESHOLD: int = 50

    def extract(self, pdf_path: Path) -> str | None:  # pragma: no cover
        """
        提取 PDF 文本层内容。
        若总字符数 <= MIN_TEXT_THRESHOLD 返回 None（表示需要 OCR 兜底）。
        """
        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                pages_text: list[str] = []
                for page in pdf.pages:
                    text: str | None = page.extract_text()
                    if text:
                        pages_text.append(text)
                full_text = "\n".join(pages_text)

            if len(full_text) <= self.MIN_TEXT_THRESHOLD:
                return None
            return full_text
        except Exception as exc:
            logger.warning("PDFTextExtractor.extract 失败: %s, 文件: %s", exc, pdf_path)
            return None

    def pdf_to_images(self, pdf_path: Path) -> tuple[list[Path], Path]:  # pragma: no cover
        """
        将 PDF 每页转换为临时 PNG 图片文件，供 OCR 使用。
        使用 PyMuPDF (fitz) 渲染，dpi=150。

        Returns:
            (image_paths, tmp_dir) — 调用方用完后需调用 shutil.rmtree(tmp_dir) 清理。
        """
        try:
            import fitz

            doc = fitz.open(str(pdf_path))
            image_paths: list[Path] = []
            tmp_dir = Path(tempfile.mkdtemp())

            for page_index in range(len(doc)):
                page = doc[page_index]
                pixmap = page.get_pixmap(dpi=150)
                img_path = tmp_dir / f"page_{page_index}.png"
                pixmap.save(str(img_path))
                image_paths.append(img_path)

            doc.close()
            return image_paths, tmp_dir
        except Exception as exc:
            logger.warning("PDFTextExtractor.pdf_to_images 失败: %s, 文件: %s", exc, pdf_path)
            return [], Path()
