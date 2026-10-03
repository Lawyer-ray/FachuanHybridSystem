"""格式规范化任务服务层。

承载 format_api 下沉的任务级业务：任务获取、权限校验、规范化执行与
产物落库、输出文件解析。404 / 权限拒绝语义沿用 API 时期的约定——
不存在与无权均抛 ``NotFoundError``（HTTP 404），权限拒绝不走 403，
避免向未授权用户泄露任务存在性。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from apps.contract_review.models import ReviewTask
from apps.contract_review.services.format_normalizer import normalize_to_media
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.storage_service import to_media_abs

logger = logging.getLogger(__name__)


class FormatTaskService:
    """格式规范化任务服务：任务获取 / 权限校验 / 规范化执行 / 输出解析。"""

    def check_task_access(self, task: ReviewTask, user: Any) -> bool:
        """检查用户是否有权限访问任务（超级用户放行，否则仅限本人任务）。"""
        if user is None:
            return False
        if user.is_superuser:
            return True
        return bool(task.user_id == user.id)

    def get_task_for_user(self, task_id: UUID, user: Any, *, denied_message: str) -> ReviewTask:
        """获取任务并校验访问权限。

        Raises:
            NotFoundError: 任务不存在，或用户无权访问（均映射 HTTP 404，
                denied_message 用于区分文案但不泄露存在性语义）。
        """
        try:
            task = ReviewTask.objects.get(id=task_id)
        except ReviewTask.DoesNotExist:
            raise NotFoundError("任务不存在") from None
        if not self.check_task_access(task, user):
            raise NotFoundError(denied_message)
        return task

    def normalize_document(self, *, task_id: UUID, user: Any, reference_file: str | None) -> dict[str, Any]:
        """对任务原始文件执行格式规范化并回写输出文件。

        同步阻塞（内部含文件 IO 与落库），API 层需用 sync_to_async 包装调用。
        失败语义与既有行为一致：除 404（不存在/无权）外返回 200 + status=failed。
        """
        # 与 download_normalized 一致：不存在/无权用 404，而非 200+failed
        task = self.get_task_for_user(task_id, user, denied_message="无权操作此任务")

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
            # 获取参考文档路径（to_media_abs 保证路径在 MEDIA_ROOT 内，防止路径遍历攻击）
            reference_path: Path | None = None
            if reference_file:
                try:
                    reference_path = to_media_abs(reference_file)
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

            # 执行格式规范化（产物经 default_storage 落盘，落库存相对路径）
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

    def resolve_output_file(self, *, task_id: UUID, user: Any) -> Path:
        """解析格式规范化产物路径供下载。

        Raises:
            NotFoundError: 任务不存在 / 无权下载 / 输出文件不存在（含路径无效）。
        """
        task = self.get_task_for_user(task_id, user, denied_message="无权下载此文件")

        if not task.output_file:
            raise NotFoundError("输出文件不存在")

        try:
            output_path = to_media_abs(task.output_file)
        except ValidationException:
            raise NotFoundError("输出文件不存在") from None
        if not output_path.exists():
            raise NotFoundError("输出文件不存在")
        return output_path
