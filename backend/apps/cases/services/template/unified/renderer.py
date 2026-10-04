"""Business logic services."""

from __future__ import annotations

import io
import logging
from typing import Any

from docxtpl import DocxTemplate

from apps.core.exceptions import ValidationException
from apps.core.exceptions.error_codes import TEMPLATE_RENDER_ERROR
from apps.core.utils.path import Path
from apps.documents.services.placeholders.fallback import SANDBOXED_JINJA_ENV, build_docx_render_context

logger = logging.getLogger("apps.cases.services")


class DocxRenderer:
    def render(self, *, template_path: Path, context: dict[str, Any]) -> bytes:  # pragma: no cover
        try:
            logger.info(
                "渲染模板",
                extra={
                    "template_path": str(template_path),
                    "context_keys": list(context.keys()),
                },
            )

            doc = DocxTemplate(str(template_path))
            doc.render(build_docx_render_context(doc=doc, context=context), jinja_env=SANDBOXED_JINJA_ENV)

            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error(
                "模板渲染失败",
                exc_info=True,
                extra={
                    "template_path": str(template_path),
                    "error": str(e),
                },
            )
            raise ValidationException(
                message="模板渲染失败: %(err)s" % {"err": str(e)},
                code=TEMPLATE_RENDER_ERROR,
                errors={"error": str(e)},
            ) from e
