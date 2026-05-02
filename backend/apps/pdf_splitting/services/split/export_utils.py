"""PDF 导出 + 文件名去重。"""

from __future__ import annotations

from pathlib import Path

import fitz


class ExportUtils:
    """PDF 片段导出与文件名去重工具。"""

    @staticmethod
    def render_page_bytes(page: fitz.Page, *, dpi: int) -> bytes:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        return pix.tobytes("png")  # type: ignore[no-any-return]

    @staticmethod
    def export_segment_pdf(source_doc: fitz.Document, page_start: int, page_end: int, output_path: Path) -> None:
        segment_doc = fitz.open()
        try:
            segment_doc.insert_pdf(source_doc, from_page=page_start - 1, to_page=page_end - 1)
            segment_doc.save(output_path.as_posix())
        finally:
            segment_doc.close()

    @staticmethod
    def deduplicate_filename(display_name: str, seen_names: set[str]) -> str:
        path = Path(display_name)
        stem = path.stem or "片段"
        suffix = path.suffix or ".pdf"
        candidate = f"{stem}{suffix}"
        counter = 2
        while candidate in seen_names:
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        seen_names.add(candidate)
        return candidate
