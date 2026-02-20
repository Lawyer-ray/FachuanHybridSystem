"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from dataclasses import dataclass
from typing import Any, cast

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.path import Path

from .wiring import get_document_service

logger = logging.getLogger("apps.cases.services")


@dataclass(frozen=True)
class ResolvedTemplate:
    template: Any
    template_path: Path
    effective_function_code: str | None


class TemplateResolver:
    def __init__(self, *, document_service: Any | None = None) -> None:
        self._document_service = document_service

    @property
    def document_service(self) -> Any:
        if self._document_service is None:
            self._document_service = get_document_service()
        return self._document_service

    def resolve(
        self,
        *,
        template_id: int | None,
        function_code: str | None,
    ) -> ResolvedTemplate:
        if template_id is None and not function_code:
            raise ValidationException(
                message=_("必须提供 template_id 或 function_code"),
                code="INVALID_PARAMS",
                errors={"params": "必须提供 template_id 或 function_code"},
            )

        if template_id is not None:
            template = self._get_template_by_id(template_id)
            effective_function_code = getattr(template, "function_code", None) or function_code
        else:
            template = self._get_template_by_function_code(function_code)
            effective_function_code = function_code

        template_path = self._get_template_path(template)
        return ResolvedTemplate(
            template=template, template_path=template_path, effective_function_code=effective_function_code
        )

    def get_template_info(self, *, template_id: int | None, function_code: str | None) -> dict[str, Any]:
        resolved = self.resolve(template_id=template_id, function_code=function_code)
        template = resolved.template
        return {
            "id": template.id,
            "name": template.name,
            "function_code": getattr(template, "function_code", None),
            "description": template.description or "",
            "template_type": template.template_type,
            "is_active": template.is_active,
        }

    def _get_template_by_function_code(self, function_code: str) -> Any:
        template = self.document_service.get_template_by_function_code_internal(
            function_code=function_code, is_active=True
        )
        if not template:
            raise NotFoundError(
                message=f"未找到功能标识为 {function_code} 的活跃模板",
                code="TEMPLATE_NOT_FOUND",
                errors={"function_code": f"未找到功能标识为 {function_code} 的活跃模板"},
            )

        logger.info(
            "通过 function_code 查找模板",
            extra={
                "function_code": function_code,
                "template_id": cast(int, template.id),
                "template_name": template.name,
            },
        )
        return template

    def _get_template_by_id(self, template_id: int) -> Any:
        template = self.document_service.get_template_by_id_internal(template_id)
        if not template:
            raise NotFoundError(
                message=_("模板不存在"),
                code="TEMPLATE_NOT_FOUND",
                errors={"template_id": f"ID 为 {template_id} 的模板不存在"},
            )
        return template

    def _get_template_path(self, template: Any) -> Path:
        location = (getattr(template, "file_path", None) or "").strip()
        if not location:
            raise ValidationException(
                message=_("模板文件路径为空"),
                code="TEMPLATE_FILE_EMPTY",
                errors={"template_id": str(template.id)},
            )

        path = Path(location)
        if not path.exists():
            raise ValidationException(
                message=f"模板文件不存在: {location}",
                code="TEMPLATE_FILE_NOT_FOUND",
                errors={"template_path": location},
            )
        return path
