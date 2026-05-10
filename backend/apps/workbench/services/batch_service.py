"""批量分析任务服务层

遵循 PdfSplitJobService 的生命周期模式：create → get_progress → cancel → mark_completed/failed。
"""

from __future__ import annotations

import logging
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.security.permissions import AccessContext, PermissionMixin

from ..models import BatchJob, BatchJobItem, BatchJobStatus

logger = logging.getLogger(__name__)

_EXCEL_EXTS = {".xls", ".xlsx"}


def _is_excel(filename: str) -> bool:
    """判断文件是否为 Excel 格式"""
    if not filename or "." not in filename:
        return False
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    return ext in _EXCEL_EXTS


def _split_excel_rows(uploaded_file: Any) -> list[tuple[str, str]]:
    """将 Excel 文件拆分为多行文本

    每非空行生成一个 (file_name, text_content) 元组。
    文本格式为 "列名: 值" 的结构化文本。
    """
    import io

    import pandas as pd

    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()

    ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"

    # 读取 Excel，不指定 header，先探测表头行
    df_raw = pd.read_excel(io.BytesIO(file_bytes), engine=engine, header=None, dtype=str)

    # 自动检测表头行：找到第一个非空行且包含 >=3 个非空单元格的行
    header_row_idx = 0
    for idx in range(min(10, len(df_raw))):
        row = df_raw.iloc[idx]
        non_empty = row.dropna().shape[0]
        if non_empty >= 3:
            header_row_idx = idx
            break

    # 用检测到的表头行重新读取
    df = pd.read_excel(io.BytesIO(file_bytes), engine=engine, header=header_row_idx, dtype=str)

    # 清理列名
    df.columns = [str(c).strip() if str(c).strip() != "nan" else f"列{i + 1}" for i, c in enumerate(df.columns)]

    # 去掉全空行
    df = df.dropna(how="all").reset_index(drop=True)

    base_name = Path(uploaded_file.name).stem
    results: list[tuple[str, str]] = []

    for row_idx, row in df.iterrows():
        # 跳过全空行
        non_null = row.dropna()
        if non_null.empty or all(str(v).strip() in ("", "nan", "None") for v in row.values):
            continue

        # 格式化为 "列名: 值" 文本
        lines: list[str] = []
        for col_name, value in row.items():
            val_str = str(value).strip()
            if val_str in ("", "nan", "None"):
                continue
            lines.append(f"{col_name}: {val_str}")

        if not lines:
            continue

        text_content = "\n".join(lines)
        file_name = f"{base_name}_第{row_idx + 1}行.txt"
        results.append((file_name, text_content))

    logger.info("Excel 拆分完成: %s → %d 行", uploaded_file.name, len(results))
    return results


class BatchAnalysisService(PermissionMixin):
    """批量分析任务服务"""

    ALLOWED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx"}

    def validate_files(self, files: list[Any]) -> None:
        """校验上传文件"""
        if not files:
            raise ValidationException(_("请上传至少一个文件"))
        for f in files:
            ext = f".{f.name.rsplit('.', 1)[-1].lower()}" if f.name and "." in f.name else ""
            if ext not in self.ALLOWED_EXTENSIONS:
                raise ValidationException(
                    _("不支持的文件格式: %(name)s") % {"name": f.name},
                    errors={"file": "支持 .doc、.docx、.xls、.xlsx"},
                )

    def get_job_by_id(self, job_id: UUID) -> BatchJob:
        """获取任务，不存在时抛 NotFoundError"""
        try:
            return BatchJob.objects.get(id=job_id)
        except BatchJob.DoesNotExist:
            raise NotFoundError(_("任务不存在")) from None

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

        支持 .doc/.docx（每文件 = 一个 item）和 .xls/.xlsx（每行 = 一个 item）。

        Args:
            session_id: 关联的工作台会话 ID
            prompt: 分析要求
            llm_model: LLM 模型名称
            files: 上传的文件列表（Django UploadedFile）
            concurrency: 并发数

        Returns:
            创建的 BatchJob
        """
        # 分离 Word 文件和 Excel 文件
        word_files = [f for f in files if not _is_excel(f.name)]
        excel_files = [f for f in files if _is_excel(f.name)]

        # Excel 拆分：每行 → 一个 .txt 文件内容
        excel_items_data: list[tuple[str, str]] = []
        for ef in excel_files:
            try:
                rows = _split_excel_rows(ef)
                excel_items_data.extend(rows)
            except Exception:
                logger.exception("Excel 文件拆分失败: %s", ef.name)
                # 作为单个文件处理（fallback）
                word_files.append(ef)

        total = len(word_files) + len(excel_items_data)

        job = BatchJob.objects.create(
            session_id=session_id,
            job_type="doc_analysis",
            prompt=prompt,
            llm_model=llm_model,
            total_items=total,
            metadata={"concurrency": concurrency},
        )

        # 创建 Word items（原逻辑）
        items: list[BatchJobItem] = []
        for f in word_files:
            items.append(
                BatchJobItem(
                    job=job,
                    file_name=f.name,
                    file=f,
                )
            )

        # 创建 Excel row items（每行一个 .txt 文件）
        for file_name, text_content in excel_items_data:
            txt_file = ContentFile(text_content.encode("utf-8"), name=file_name)
            item = BatchJobItem(job=job, file_name=file_name)
            item.file.save(file_name, txt_file, save=False)
            items.append(item)

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
        from ..tasks import task_registry

        task_registry.cancel(str(job_id))

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

    def save_batch_messages(
        self,
        job_id: UUID,
        items: list[dict[str, Any]],
        *,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> int:
        """将批量分析结果持久化为工作台消息，返回创建数量"""
        from ..models import WorkbenchMessage
        from .session_service import WorkbenchSessionService, _calc_message_bytes

        job = self.get_job_by_id(job_id)
        messages = []
        total_bytes = 0
        for item in items:
            content = item["content"]
            metadata = {**item.get("metadata", {}), "job_id": str(job_id)}
            messages.append(
                WorkbenchMessage(
                    session_id=job.session_id,
                    role="assistant",
                    content=content,
                    metadata=metadata,
                )
            )
            total_bytes += _calc_message_bytes(content=content, metadata=metadata)

        WorkbenchMessage.objects.bulk_create(messages, batch_size=100)
        WorkbenchSessionService.increment_storage(job.session_id, total_bytes)
        return len(messages)

    def list_batch_jobs(
        self,
        session_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """获取会话的批量分析任务历史"""
        qs = BatchJob.objects.filter(session_id=session_id).order_by("-created_at")
        offset = (page - 1) * page_size
        total = qs.count()
        items = list(qs[offset : offset + page_size])
        return {
            "items": [self._job_to_dict(j) for j in items],
            "count": total,
        }

    @staticmethod
    def _job_to_dict(job: BatchJob) -> dict[str, Any]:
        """将 BatchJob 转换为字典"""
        from ..schemas import BatchJobOut

        return BatchJobOut.model_validate(job).model_dump()
