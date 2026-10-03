import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.http import FileResponse, HttpRequest
from ninja import Router

from apps.contract_review.models import ReviewTask
from apps.contract_review.schemas.format_schemas import FormatNormalizeIn, FormatNormalizeOut
from apps.core.exceptions import ValidationException
from apps.core.services.storage_service import to_media_abs

logger = logging.getLogger(__name__)
router = Router()


def _check_task_access(task: Any, user: Any) -> bool:
    """检查用户是否有权限访问任务"""
    if user is None:
        return False
    if user.is_superuser:
        return True
    return bool(task.user_id == user.id)


@router.post("/normalize", response=FormatNormalizeOut)
async def normalize_format(  # pragma: no cover
    request: HttpRequest,
    payload: FormatNormalizeIn,
) -> dict[str, Any]:
    """对合同文件进行格式规范化"""

    def _do_normalize() -> dict[str, Any]:
        try:
            task = ReviewTask.objects.get(id=payload.task_id)
        except ReviewTask.DoesNotExist:
            # 与同文件 download_normalized 一致：不存在/无权用 404，而非 200+failed
            from django.http import Http404

            raise Http404("任务不存在")

        # 权限检查
        if not _check_task_access(task, request.user):
            from django.http import Http404

            raise Http404("无权操作此任务")

        # 检查原始文件是否存在
        if not task.original_file:
            return {
                "task_id": task.id,
                "status": "failed",
                "message": "原始文件不存在",
            }

        try:
            original_path = to_media_abs(task.original_file)
        except ValidationException:
            return {
                "task_id": task.id,
                "status": "failed",
                "message": f"原始文件路径无效: {task.original_file}",
            }
        if not original_path.exists():
            return {
                "task_id": task.id,
                "status": "failed",
                "message": f"原始文件不存在: {original_path}",
            }

        try:
            # 执行格式规范化（产物经 default_storage 落盘，落库存相对路径）
            from apps.contract_review.services.format_normalizer import normalize_to_media

            # 获取参考文档路径（to_media_abs 保证路径在 MEDIA_ROOT 内，防止路径遍历攻击）
            reference_path: Path | None = None
            if payload.reference_file:
                try:
                    reference_path = to_media_abs(payload.reference_file)
                except ValidationException:
                    return {
                        "task_id": task.id,
                        "status": "failed",
                        "message": "无效的参考文档路径",
                    }
                if not reference_path.exists():
                    return {
                        "task_id": task.id,
                        "status": "failed",
                        "message": f"参考文档不存在: {reference_path}",
                    }

            saved_name = normalize_to_media(original_path, reference_path=reference_path)

            # 更新任务的输出文件
            task.output_file = saved_name
            task.save(update_fields=["output_file"])

            return {
                "task_id": task.id,
                "status": "success",
                "output_file": saved_name,
                "message": "格式规范化完成",
            }

        except Exception as e:
            logger.exception("格式规范化失败: %s", e)
            return {
                "task_id": task.id,
                "status": "failed",
                "message": f"格式规范化失败: {e!s}",
            }

    return await sync_to_async(_do_normalize, thread_sensitive=False)()


@router.get("/{task_id}/download-normalized")
def download_normalized(request: HttpRequest, task_id: UUID) -> FileResponse:  # pragma: no cover
    """下载格式规范化后的文件"""
    try:
        task = ReviewTask.objects.get(id=task_id)
    except ReviewTask.DoesNotExist:
        from django.http import Http404

        raise Http404("任务不存在")

    # 权限检查
    if not _check_task_access(task, request.user):
        from django.http import Http404

        raise Http404("无权下载此文件")

    if not task.output_file:
        from django.http import Http404

        raise Http404("输出文件不存在")

    try:
        output_path = to_media_abs(task.output_file)
    except ValidationException:
        from django.http import Http404

        raise Http404("输出文件不存在")
    if not output_path.exists():
        from django.http import Http404

        raise Http404("输出文件不存在")

    return FileResponse(
        output_path.open("rb"),
        as_attachment=True,
        filename=output_path.name,
    )
