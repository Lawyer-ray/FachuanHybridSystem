"""案件文件模板渲染下载 API"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from ninja import Router

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


@router.post("/cases/{case_id}/templates/{template_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
def download_case_template(request: Any, case_id: int, template_id: int) -> Any:
    """渲染案件文件模板并下载"""
    from apps.documents.services.case_contract_query import get_active_template_or_none, get_case_or_none
    from apps.documents.services.generation.pipeline import DocxRenderer
    from apps.documents.services.placeholders import EnhancedContextBuilder

    case = get_case_or_none(case_id)
    if not case:
        raise NotFoundError(message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": str(case_id)})

    template = get_active_template_or_none(template_id)
    if not template:
        raise NotFoundError(message="模板不存在", code="TEMPLATE_NOT_FOUND", errors={"template_id": str(template_id)})

    file_path = template.get_file_location()
    if not file_path:
        raise ValidationException(message="模板文件路径为空", code="TEMPLATE_FILE_EMPTY", errors={})

    context = EnhancedContextBuilder().build_context({"case": case, "case_id": case.id})
    content = DocxRenderer().render(file_path, context)

    date_str = timezone.now().strftime("%Y%m%d")
    filename = f"{template.name}({case.name or '案件'})V1_{date_str}.docx"

    logger.info("案件模板下载成功", extra={"case_id": case_id, "template_id": template_id, "doc_filename": filename})

    return build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
