"""Business logic services."""

from io import BytesIO
from typing import Any

from apps.documents.services.placeholders.fallback import build_docx_render_context


class DocxRenderer:
    def render(self, template_path: str, context: dict[str, Any]) -> bytes:  # pragma: no cover
        from docxtpl import DocxTemplate

        from apps.documents.services.placeholders.archive import unwrap_archive_rich_text

        render_context = unwrap_archive_rich_text(context)
        doc = DocxTemplate(template_path)
        doc.render(build_docx_render_context(doc=doc, context=render_context))
        output = BytesIO()
        doc.save(output)
        return output.getvalue()
