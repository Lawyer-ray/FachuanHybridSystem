"""Business logic services."""

from io import BytesIO
from typing import Any

from apps.documents.services.placeholders.fallback import build_docx_render_context


class DocxRenderer:
    def render(self, template_path: str, context: dict[str, Any]) -> bytes:
        from docxtpl import DocxTemplate

        doc = DocxTemplate(template_path)
        doc.render(build_docx_render_context(doc=doc, context=context))
        output = BytesIO()
        doc.save(output)
        return output.getvalue()
