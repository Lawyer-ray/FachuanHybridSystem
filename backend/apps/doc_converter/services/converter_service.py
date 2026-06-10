from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.storage_service import sanitize_upload_filename

from ..models import DocConverterItem, DocConverterJob, DocConverterJobStatus

logger = logging.getLogger("apps.doc_converter")


class DocConverterService:
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB per file
    ALLOWED_EXTENSIONS = {".doc"}

    @transaction.atomic
    def create_job(
        self,
        *,
        files: list[UploadedFile],
        created_by: Any | None = None,
    ) -> DocConverterJob:  # pragma: no cover
        if not files:
            raise ValidationException(message="请至少上传一个文件", errors={"files": "文件列表不能为空"})

        job_id = uuid.uuid4()
        job = DocConverterJob.objects.create(
            id=job_id,
            status=DocConverterJobStatus.PENDING,
            total_files=len(files),
            created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        )

        items: list[DocConverterItem] = []
        for f in files:
            self._validate_file(f)
            item = DocConverterItem(
                job=job,
                original_name=sanitize_upload_filename(f.name or "unknown.doc"),
                source_file=f,
                status=DocConverterJobStatus.PENDING,
            )
            items.append(item)
        DocConverterItem.objects.bulk_create(items)

        task_id = build_task_submission_service().submit(
            "apps.doc_converter.tasks.run_conversion_job",
            args=[str(job.id)],
            task_name=f"doc_converter_{job.id}",
            timeout=7200,
        )
        DocConverterJob.objects.filter(id=job.id).update(
            task_id=str(task_id),
            started_at=timezone.now(),
        )
        job.refresh_from_db()
        return job

    def get_job(self, job_id: uuid.UUID) -> DocConverterJob:
        try:
            return DocConverterJob.objects.get(id=job_id)
        except DocConverterJob.DoesNotExist:
            raise NotFoundError(message="转换任务不存在", code="DOC_CONVERTER_JOB_NOT_FOUND", errors={}) from None

    def get_job_progress(self, job_id: uuid.UUID) -> tuple[DocConverterJob, list[DocConverterItem]]:
        job = self.get_job(job_id)
        items = list(job.items.all())
        return job, items

    def request_cancel(self, *, job_id: uuid.UUID) -> DocConverterJob:  # pragma: no cover
        job = self.get_job(job_id)
        if job.status in {
            DocConverterJobStatus.COMPLETED,
            DocConverterJobStatus.FAILED,
            DocConverterJobStatus.CANCELLED,
        }:
            return job

        cancel_result: dict[str, Any] = {}
        if job.task_id:
            try:
                cancel_result = build_task_submission_service().cancel(job.task_id)
            except Exception:
                logger.exception("doc_converter_cancel_failed: job=%s task=%s", job.id, job.task_id)

        updates: dict[str, Any] = {"cancel_requested": True}
        can_mark_cancelled = job.status == DocConverterJobStatus.PENDING and (
            not job.task_id or bool(cancel_result.get("queue_deleted")) or not bool(cancel_result.get("running"))
        )
        if can_mark_cancelled:
            updates.update(status=DocConverterJobStatus.CANCELLED, finished_at=timezone.now())
        DocConverterJob.objects.filter(id=job.id).update(**updates)
        job.refresh_from_db()
        return job

    def mark_completed(self, *, job_id: uuid.UUID, zip_relpath: str) -> None:  # pragma: no cover
        DocConverterJob.objects.filter(id=job_id).update(
            status=DocConverterJobStatus.COMPLETED,
            progress=100,
            output_zip=zip_relpath,
            finished_at=timezone.now(),
            error_message="",
        )

    def mark_failed(self, *, job_id: uuid.UUID, error_message: str) -> None:  # pragma: no cover
        DocConverterJob.objects.filter(id=job_id).update(
            status=DocConverterJobStatus.FAILED,
            error_message=error_message[:4000],
            finished_at=timezone.now(),
        )

    def build_job_payload(self, job: DocConverterJob) -> dict[str, Any]:
        download_url = ""
        if job.status == DocConverterJobStatus.COMPLETED and job.output_zip:
            download_url = f"/api/v1/doc-converter/jobs/{job.id}/download"

        return {
            "id": job.id,
            "status": job.status,
            "total_files": job.total_files,
            "converted_files": job.converted_files,
            "failed_files": job.failed_files,
            "progress": job.progress,
            "error_message": job.error_message or "",
            "download_url": download_url,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
        }

    def build_item_payload(self, item: DocConverterItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "original_name": item.original_name,
            "status": item.status,
            "error": item.error or "",
            "duration_ms": item.duration_ms,
        }

    def save_job_to_directory(
        self,
        *,
        job_id: uuid.UUID,
        target_dir: str,
    ) -> dict[str, Any]:  # pragma: no cover
        job = self.get_job(job_id)
        if job.status != DocConverterJobStatus.COMPLETED:
            raise ValidationException(
                message="任务尚未完成", errors={"status": f"当前状态: {job.get_status_display()}"}
            )

        if not target_dir or not target_dir.strip():
            raise ValidationException(message="目标目录不能为空", errors={"target_dir": "请输入目录路径"})

        resolved = Path(target_dir).resolve()
        if ".." in Path(target_dir).parts:
            raise ValidationException(message="路径不合法", errors={"target_dir": "不允许包含 .."})

        media_root = Path(settings.MEDIA_ROOT).resolve()
        if resolved == media_root or media_root in resolved.parents:
            raise ValidationException(
                message="不能保存到媒体目录", errors={"target_dir": "目标目录不能在 MEDIA_ROOT 下"}
            )

        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValidationException(message="无法创建目录", errors={"target_dir": str(exc)}) from exc

        items = DocConverterItem.objects.filter(
            job=job,
            status=DocConverterJobStatus.COMPLETED,
        ).exclude(converted_file="")

        saved_files: list[str] = []
        for item in items:
            src = Path(item.converted_file.path)
            if not src.exists():
                continue
            dest_name = Path(item.original_name).stem + ".docx"
            dest = resolved / dest_name
            shutil.copy2(str(src), str(dest))
            saved_files.append(dest_name)

        if not saved_files:
            raise ValidationException(message="没有可保存的文件", errors={"files": "无已转换的文件"})

        return {
            "saved_files": saved_files,
            "total_saved": len(saved_files),
            "target_dir": str(resolved),
        }

    def _validate_file(self, f: UploadedFile) -> None:
        name = f.name or ""
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if f".{ext}" not in self.ALLOWED_EXTENSIONS:
            raise ValidationException(
                message=f"不支持的文件格式: .{ext}",
                errors={"files": f"仅支持 .doc 文件，收到: {name}"},
            )
        size = int(f.size or 0)
        if size <= 0:
            raise ValidationException(message="上传文件为空", errors={"files": f"{name} 为空文件"})
        if size > self.MAX_FILE_SIZE:
            raise ValidationException(
                message="文件大小超过限制",
                errors={"files": f"{name} 超过 {self.MAX_FILE_SIZE // 1024 // 1024}MB 限制"},
            )
