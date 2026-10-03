import logging
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.http import FileResponse, HttpRequest
from ninja import Router

from apps.contract_review.schemas.format_schemas import FormatNormalizeIn, FormatNormalizeOut
from apps.contract_review.services.format_service import FormatTaskService

logger = logging.getLogger(__name__)
router = Router()


def _get_format_task_service() -> FormatTaskService:
    """工厂函数：创建格式规范化任务服务实例"""
    return FormatTaskService()


@router.post("/normalize", response=FormatNormalizeOut)
async def normalize_format(  # pragma: no cover
    request: HttpRequest,
    payload: FormatNormalizeIn,
) -> dict[str, Any]:
    """对合同文件进行格式规范化"""
    service = _get_format_task_service()
    return await sync_to_async(service.normalize_document, thread_sensitive=False)(
        task_id=payload.task_id,
        user=request.user,
        reference_file=payload.reference_file,
    )


@router.get("/{task_id}/download-normalized")
def download_normalized(request: HttpRequest, task_id: UUID) -> FileResponse:  # pragma: no cover
    """下载格式规范化后的文件"""
    service = _get_format_task_service()
    output_path = service.resolve_output_file(task_id=task_id, user=request.user)
    return FileResponse(
        output_path.open("rb"),
        as_attachment=True,
        filename=output_path.name,
    )
