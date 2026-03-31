from __future__ import annotations


class PdfExporter:
    def export(self, html_content: str) -> bytes:
        from weasyprint import HTML

        return HTML(string=html_content, base_url=None).write_pdf()
