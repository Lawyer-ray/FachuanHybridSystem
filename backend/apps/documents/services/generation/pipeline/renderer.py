"""Business logic services."""

from io import BytesIO
from typing import Any

from apps.documents.services.placeholders.fallback import SANDBOXED_JINJA_ENV, build_docx_render_context
from apps.documents.services.placeholders.long_text import apply_bold_sentinels


class DocxRenderer:
    def render(self, template_path: str, context: dict[str, Any]) -> bytes:  # pragma: no cover
        from docxtpl import DocxTemplate

        from apps.documents.services.placeholders.archive import unwrap_archive_rich_text

        render_context = unwrap_archive_rich_text(context)
        doc = DocxTemplate(template_path)
        doc.render(
            build_docx_render_context(doc=doc, context=render_context),
            jinja_env=SANDBOXED_JINJA_ENV,
        )
        output = BytesIO()
        doc.save(output)
        # 长正文产出方把 `**x**` 改写成私用区哨兵（占位符服务 → long_text.markdown_bold_to_sentinel），
        # 所有 docx 渲染出口都在这里统一收尾成 <w:b/>；值里没有哨兵时原字节返回。
        return apply_bold_sentinels(output.getvalue())
