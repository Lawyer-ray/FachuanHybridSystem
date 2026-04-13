from __future__ import annotations

from typing import cast


class PdfExporter:
    def export(self, html_content: str) -> bytes:
        from weasyprint import HTML

        return cast(bytes, HTML(string=html_content, base_url=None).write_pdf())
