"""批量分析任务服务层

遵循 PdfSplitJobService 的生命周期模式：create → get_progress → cancel → mark_completed/failed。
"""

from __future__ import annotations

import logging
from datetime import timezone as dt_timezone
from typing import Any
from uuid import UUID

from django.utils import timezone

from ..models import BatchJob, BatchJobItem, BatchJobStatus

logger = logging.getLogger(__name__)


class BatchAnalysisService:
    """批量分析任务服务"""

    def create_job(
        self,
        *,
        session_id: int,
        prompt: str,
        llm_model: str,
        files: list[Any],
        concurrency: int = 50,
    ) -> BatchJob:
        """创建批量分析任务

        Args:
            session_id: 关联的工作台会话 ID
            prompt: 分析要求
            llm_model: LLM 模型名称
            files: 上传的文件列表（Django UploadedFile）
            concurrency: 并发数

        Returns:
            创建的 BatchJob
        """
        job = BatchJob.objects.create(
            session_id=session_id,
            job_type="doc_analysis",
            prompt=prompt,
            llm_model=llm_model,
            total_items=len(files),
            metadata={"concurrency": concurrency},
        )

        # 创建子项
        items = []
        for f in files:
            items.append(
                BatchJobItem(
                    job=job,
                    file_name=f.name,
                    file=f,
                )
            )
        BatchJobItem.objects.bulk_create(items)

        # 提交 Django Q2 任务
        from apps.core.dependencies.core import build_task_submission_service

        task_id = build_task_submission_service().submit(
            "apps.workbench.tasks.run_batch_analysis",
            args=[str(job.id)],
            task_name=f"batch_analysis_{job.id}",
            timeout=3600,  # 1 小时超时
        )
        BatchJob.objects.filter(id=job.id).update(
            task_id=str(task_id),
            started_at=timezone.now(),
        )
        job.refresh_from_db()

        logger.info("批量分析任务已创建: job=%s, files=%d, model=%s", job.id, len(files), llm_model)
        return job

    def get_job_progress(self, job_id: UUID) -> tuple[BatchJob, list[BatchJobItem]]:
        """查询任务进度，包含计算字段（ETA、速度）"""
        job = BatchJob.objects.get(id=job_id)
        items = list(BatchJobItem.objects.filter(job_id=job_id))

        # 计算 ETA 和速度
        processed = job.completed_items + job.failed_items
        if job.started_processing_at and processed > 0 and job.status == BatchJobStatus.RUNNING:
            now = timezone.now()
            elapsed = (now - job.started_processing_at).total_seconds()
            if elapsed > 0:
                job.speed_per_minute = processed / elapsed * 60  # type: ignore[attr-defined]
                remaining = job.total_items - processed
                if job.speed_per_minute > 0:  # type: ignore[attr-defined]
                    job.eta_seconds = remaining / (job.speed_per_minute / 60)  # type: ignore[attr-defined]

        return job, items

    def get_failed_items_detail(self, job_id: UUID) -> list[dict[str, Any]]:
        """获取失败项的详细信息"""
        items = BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.FAILED)
        return [{"id": str(item.id), "file_name": item.file_name, "error": item.error} for item in items]

    def request_cancel(self, job_id: UUID) -> BatchJob:
        """请求取消任务（协作式）

        遵循 PdfSplitJobService.request_cancel 的模式：
        1. 设置 cancel_requested = True
        2. 尝试从 Django Q 队列中移除
        3. 如果任务还在排队，立即标记为 CANCELLED
        """
        job = BatchJob.objects.get(id=job_id)
        if job.status in {BatchJobStatus.COMPLETED, BatchJobStatus.FAILED, BatchJobStatus.CANCELLED}:
            return job

        # 尝试即时取消 asyncio task
        from apps.workbench.tasks import _active_tasks

        active_task = _active_tasks.get(str(job_id))
        if active_task and not active_task.done():
            active_task.cancel()
            logger.info("已取消 asyncio task: job=%s", job_id)

        cancel_result: dict[str, Any] = {}
        if job.task_id:
            try:
                from apps.core.dependencies.core import build_task_submission_service

                cancel_result = build_task_submission_service().cancel(job.task_id)
            except Exception:
                logger.exception("批量任务取消失败: job=%s, task_id=%s", job.id, job.task_id)

        updates: dict[str, Any] = {"cancel_requested": True}
        can_mark_cancelled = job.status == BatchJobStatus.PENDING and (
            not job.task_id or bool(cancel_result.get("queue_deleted")) or not bool(cancel_result.get("running"))
        )
        if can_mark_cancelled:
            updates.update(status=BatchJobStatus.CANCELLED, finished_at=timezone.now())

        BatchJob.objects.filter(id=job.id).update(**updates)
        job.refresh_from_db()
        return job

    def retry_failed(self, job_id: UUID) -> dict[str, Any]:
        """重试失败的 item

        1. 查找所有 FAILED items
        2. 重置为 PENDING
        3. 调整 job 计数器
        4. 提交新的 Q2 任务
        """
        job = BatchJob.objects.get(id=job_id)
        if job.status not in {BatchJobStatus.COMPLETED, BatchJobStatus.FAILED}:
            return {"success": False, "message": "只能重试已完成或已失败的任务"}

        failed_items = list(BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.FAILED))
        if not failed_items:
            return {"success": False, "message": "没有失败的文件需要重试"}

        failed_ids = [str(item.id) for item in failed_items]

        # 重置失败 items
        BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.FAILED).update(
            status=BatchJobStatus.PENDING,
            error="",
        )

        # 调整 job 计数器和状态
        BatchJob.objects.filter(id=job_id).update(
            status=BatchJobStatus.RUNNING,
            failed_items=0,
            finished_at=None,
            error_message="",
        )

        # 提交重试任务
        from apps.core.dependencies.core import build_task_submission_service

        task_id = build_task_submission_service().submit(
            "apps.workbench.tasks.run_batch_retry",
            args=[str(job_id), failed_ids],
            task_name=f"batch_retry_{job_id}",
            timeout=3600,
        )
        BatchJob.objects.filter(id=job_id).update(task_id=str(task_id))
        job.refresh_from_db()

        logger.info("批量重试已提交: job=%s, items=%d", job_id, len(failed_ids))
        return {"success": True, "message": f"已提交 {len(failed_ids)} 个文件的重试", "retry_count": len(failed_ids)}

    def mark_completed(self, job_id: UUID, summary: str) -> None:
        """标记任务完成"""
        BatchJob.objects.filter(id=job_id).update(
            status=BatchJobStatus.COMPLETED,
            summary=summary,
            progress=100,
            finished_at=timezone.now(),
            error_message="",
        )

    def mark_failed(self, job_id: UUID, error_message: str) -> None:
        """标记任务失败"""
        BatchJob.objects.filter(id=job_id).update(
            status=BatchJobStatus.FAILED,
            error_message=error_message[:4000],
            finished_at=timezone.now(),
        )
