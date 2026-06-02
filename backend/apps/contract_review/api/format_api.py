import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from django.http import FileResponse, HttpRequest
from ninja import Router

from apps.contract_review.models import ReviewTask
from apps.contract_review.schemas.format_schemas import FormatNormalizeIn, FormatNormalizeOut

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
def normalize_format(
    request: HttpRequest,
    payload: FormatNormalizeIn,
) -> dict[str, Any]:
    """对合同文件进行格式规范化"""
    try:
        task = ReviewTask.objects.get(id=payload.task_id)
    except ReviewTask.DoesNotExist:
        return {
            "task_id": payload.task_id,
            "status": "failed",
            "message": "任务不存在",
        }

    # 权限检查
    if not _check_task_access(task, request.user):
        return {
            "task_id": payload.task_id,
            "status": "failed",
            "message": "无权操作此任务",
        }

    # 检查原始文件是否存在
    if not task.original_file:
        return {
            "task_id": task.id,
            "status": "failed",
            "message": "原始文件不存在",
        }

    original_path = Path(task.original_file)
    if not original_path.exists():
        return {
            "task_id": task.id,
            "status": "failed",
            "message": f"原始文件不存在: {original_path}",
        }

    try:
        # 执行格式规范化
        from apps.contract_review.services.format_normalizer import DocxFormatNormalizer

        # 生成输出文件路径
        output_dir = original_path.parent
        output_filename = f"{original_path.stem}_规范化{original_path.suffix}"
        output_path = output_dir / output_filename

        # 获取参考文档路径
        reference_path = None
        if payload.reference_file:
            reference_path = Path(payload.reference_file)
            if not reference_path.exists():
                return {
                    "task_id": task.id,
                    "status": "failed",
                    "message": f"参考文档不存在: {reference_path}",
                }

        normalizer = DocxFormatNormalizer(original_path, output_path, reference_path)
        result_path = normalizer.normalize()

        # 更新任务的输出文件
        task.output_file = str(result_path)
        task.save(update_fields=["output_file"])

        return {
            "task_id": task.id,
            "status": "success",
            "output_file": str(result_path),
            "message": "格式规范化完成",
        }

    except Exception as e:
        logger.exception("格式规范化失败: %s", e)
        return {
            "task_id": task.id,
            "status": "failed",
            "message": f"格式规范化失败: {e!s}",
        }


@router.get("/{task_id}/download-normalized")
def download_normalized(request: HttpRequest, task_id: UUID) -> FileResponse:
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

    output_path = Path(task.output_file)
    if not output_path.exists():
        from django.http import Http404

        raise Http404("输出文件不存在")

    return FileResponse(
        output_path.open("rb"),
        as_attachment=True,
        filename=output_path.name,
    )
