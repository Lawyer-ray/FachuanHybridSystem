"""Business logic services."""

import io
import logging
from typing import Any

from django.utils.translation import gettext_lazy as _
from docxtpl import DocxTemplate

from apps.core.exceptions import ValidationException
from apps.core.path import Path

logger = logging.getLogger("apps.cases.services")


class DocxRenderer:
    def render(self, *, template_path: Path, context: dict[str, Any]) -> bytes:
        try:
            logger.info(
                "渲染模板",
                extra={
                    "template_path": str(template_path),
                    "context_keys": list(context.keys()),
                },
            )

            doc = DocxTemplate(str(template_path))
            doc.render(context)

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
                message=_("模板渲染失败: %(err)s") % {"err": str(e)},
                code="TEMPLATE_RENDER_ERROR",
                errors={"error": str(e)},
            ) from e
