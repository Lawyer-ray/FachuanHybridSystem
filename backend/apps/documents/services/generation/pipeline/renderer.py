"""Business logic services."""

from io import BytesIO
from typing import Any


class DocxRenderer:
    def render(self, template_path: str, context: dict[str, Any]) -> bytes:
        from docxtpl import DocxTemplate

        doc = DocxTemplate(template_path)
        doc.render(context)
        output = BytesIO()
        doc.save(output)
        return output.getvalue()
