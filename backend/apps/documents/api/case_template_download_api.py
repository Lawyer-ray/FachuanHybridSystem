"""案件文件模板渲染下载 API"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone
from ninja import Router

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth

from .download_response_factory import build_download_response

logger = logging.getLogger("apps.documents.api")
router = Router(auth=JWTOrSessionAuth())


async def _ensure_case_access(request: Any, case_id: int) -> None:
    """校验当前用户对案件的访问权（安全审计 A-05/A-06）。"""
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    await sync_to_async(CaseAccessPolicy().ensure_access_ctx)(case_id=case_id, ctx=ctx)


@router.post("/cases/{case_id}/templates/{template_id}/download")
@rate_limit_from_settings("EXPORT", by_user=True)
async def download_case_template(request: Any, case_id: int, template_id: int) -> Any:  # pragma: no cover
    """渲染案件文件模板并下载"""
    await _ensure_case_access(request, case_id)
    from apps.documents.services.case_contract_query import aget_active_template_or_none, aget_case_or_none
    from apps.documents.services.generation.pipeline import DocxRenderer
    from apps.documents.services.placeholders import EnhancedContextBuilder

    case = await aget_case_or_none(case_id)
    if not case:
        raise NotFoundError(message="案件不存在", code="CASE_NOT_FOUND", errors={"case_id": str(case_id)})

    template = await aget_active_template_or_none(template_id)
    if not template:
        raise NotFoundError(message="模板不存在", code="TEMPLATE_NOT_FOUND", errors={"template_id": str(template_id)})

    file_path = template.get_file_location()
    if not file_path:
        raise ValidationException(message="模板文件路径为空", code="TEMPLATE_FILE_EMPTY", errors={})

    context_builder = EnhancedContextBuilder()
    context = await asyncio.to_thread(context_builder.build_context, {"case": case, "case_id": case.id})
    renderer = DocxRenderer()
    content = await asyncio.to_thread(renderer.render, file_path, context)

    date_str = timezone.now().strftime("%Y%m%d")
    filename = f"{template.name}({case.name or '案件'})V1_{date_str}.docx"

    logger.info("案件模板下载成功", extra={"case_id": case_id, "template_id": template_id, "doc_filename": filename})

    return build_download_response(
        content=content,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
