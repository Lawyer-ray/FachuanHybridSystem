from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.batch_printing.models import (
    BatchPrintFileType,
    BatchPrintItem,
    BatchPrintItemStatus,
    BatchPrintJob,
    BatchPrintJobStatus,
)
from apps.batch_printing.services.file_prepare_service import FilePrepareService
from apps.batch_printing.services.mac_print_executor_service import MacPrintExecutorService
from apps.batch_printing.services.preset_discovery_service import PresetDiscoveryService
from apps.batch_printing.services.rule_service import RuleService
from apps.batch_printing.services.storage import BatchPrintStorage
from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.storage_service import normalize_to_media_rel, sanitize_upload_filename

logger = logging.getLogger("apps.batch_printing")

_ALLOWED_SUFFIX = {".pdf", ".docx"}


class BatchPrintJobService:
    def __init__(
        self,
        *,
        rule_service: RuleService,
        preset_discovery_service: PresetDiscoveryService,
        file_prepare_service: FilePrepareService,
        print_executor_service: MacPrintExecutorService,
    ) -> None:
        self._rule_service = rule_service
        self._preset_discovery_service = preset_discovery_service
        self._file_prepare_service = file_prepare_service
        self._print_executor_service = print_executor_service

    def list_jobs(self, *, status: str = "", keyword: str = "") -> list[BatchPrintJob]:
        queryset = BatchPrintJob.objects.select_related("created_by").order_by("-created_at")

        normalized_status = status.strip()
        if normalized_status:
            queryset = queryset.filter(status=normalized_status)

        normalized_keyword = keyword.strip()
        if normalized_keyword:
            queryset = queryset.filter(
                Q(task_id__icontains=normalized_keyword)
                | Q(error_message__icontains=normalized_keyword)
                | Q(items__source_original_name__icontains=normalized_keyword)
            ).distinct()

        return list(queryset)

    def create_job(self, *, files: list[UploadedFile], created_by: Any | None = None) -> BatchPrintJob:
        if not files:
            raise ValidationException(message="请至少上传一个文件", errors={"files": "不能为空"})

        self._preset_discovery_service.sync_presets()

        job = BatchPrintJob.objects.create(
            status=BatchPrintJobStatus.PENDING,
            created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
            capability_payload=self._file_prepare_service.get_capability_snapshot(),
        )

        storage = BatchPrintStorage(job.id)
        storage.ensure_dirs()
        items: list[BatchPrintItem] = []

        try:
            for index, upload in enumerate(files, start=1):
                original_name = sanitize_upload_filename(upload.name or f"upload_{index}.pdf")
                suffix = Path(original_name).suffix.lower()
                if suffix not in _ALLOWED_SUFFIX:
                    raise ValidationException(
                        message="仅支持 PDF 与 DOCX",
                        errors={"file": f"{original_name} 扩展名不受支持"},
                    )

                source_path = storage.source_file_path(order=index, filename=original_name)
                source_path.parent.mkdir(parents=True, exist_ok=True)
                with source_path.open("wb") as fp:
                    for chunk in upload.chunks():
                        fp.write(chunk)

                relpath = normalize_to_media_rel(source_path.as_posix())
                file_type = BatchPrintFileType.PDF if suffix == ".pdf" else BatchPrintFileType.DOCX

                matched = self._rule_service.find_target(filename=original_name)
                matched_rule = matched[0] if matched else None
                matched_preset = matched[1] if matched else None

                items.append(
                    BatchPrintItem(
                        job=job,
                        order=index,
                        source_original_name=original_name,
                        source_relpath=relpath,
                        file_type=file_type,
                        matched_rule=matched_rule,
                        matched_keyword=(matched_rule.keyword if matched_rule else ""),
                        target_preset=matched_preset,
                        target_printer_name=(matched_preset.printer_name if matched_preset else ""),
                        target_preset_name=(matched_preset.preset_name if matched_preset else ""),
                    )
                )

            BatchPrintItem.objects.bulk_create(items)
            BatchPrintJob.objects.filter(id=job.id).update(total_count=len(items))

            task_id = build_task_submission_service().submit(
                "apps.batch_printing.tasks.execute_batch_print_job",
                args=[str(job.id)],
                task_name=f"batch_print_{job.id}",
            )
            BatchPrintJob.objects.filter(id=job.id).update(task_id=str(task_id))
            job.refresh_from_db()
            return job
        except Exception:
            storage.cleanup()
            job.delete()
            raise

    def get_job(self, job_id: uuid.UUID) -> BatchPrintJob:
        try:
            return (
                BatchPrintJob.objects.select_related("created_by")
                .prefetch_related("items__matched_rule", "items__target_preset")
                .get(id=job_id)
            )
        except BatchPrintJob.DoesNotExist:
            raise NotFoundError(message="批量打印任务不存在", code="BATCH_PRINT_JOB_NOT_FOUND", errors={}) from None

    def request_cancel(self, *, job_id: uuid.UUID) -> BatchPrintJob:
        job = self.get_job(job_id)
        if job.status in {BatchPrintJobStatus.COMPLETED, BatchPrintJobStatus.FAILED, BatchPrintJobStatus.CANCELLED}:
            return job

        cancel_result: dict[str, Any] = {}
        if job.task_id:
            try:
                cancel_result = build_task_submission_service().cancel(job.task_id)
            except Exception:
                logger.exception("batch_print_cancel_failed", extra={"job_id": str(job.id), "task_id": job.task_id})

        updates: dict[str, Any] = {"cancel_requested": True}
        can_mark_cancelled = job.status == BatchPrintJobStatus.PENDING and (
            not job.task_id or bool(cancel_result.get("queue_deleted")) or not bool(cancel_result.get("running"))
        )
        if can_mark_cancelled:
            updates.update(status=BatchPrintJobStatus.CANCELLED, finished_at=timezone.now())

        BatchPrintJob.objects.filter(id=job.id).update(**updates)
        job.refresh_from_db()
        return job

    def delete_job(self, *, job_id: uuid.UUID) -> None:
        job = self.get_job(job_id)
        if job.status in {BatchPrintJobStatus.PENDING, BatchPrintJobStatus.PROCESSING}:
            raise ValidationException(
                message="请先等待任务结束或取消后再删除",
                errors={"status": job.status},
            )
        job.delete()

    def build_job_summary_payload(self, *, job: BatchPrintJob) -> dict[str, Any]:
        created_by_name = ""
        if job.created_by is not None:
            created_by_name = str(
                getattr(job.created_by, "username", "")
                or getattr(job.created_by, "name", "")
                or getattr(job.created_by, "full_name", "")
                or ""
            )

        return {
            "job_id": str(job.id),
            "status": job.status,
            "total_count": int(job.total_count),
            "processed_count": int(job.processed_count),
            "success_count": int(job.success_count),
            "failed_count": int(job.failed_count),
            "progress": int(job.progress),
            "cancel_requested": bool(job.cancel_requested),
            "task_id": job.task_id or "",
            "created_by_id": job.created_by_id,
            "created_by_name": created_by_name,
            "capability_payload": job.capability_payload or {},
            "summary_payload": job.summary_payload or {},
            "error_message": job.error_message or "",
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }

    def build_job_item_payload(self, *, item: BatchPrintItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "order": item.order,
            "filename": item.source_original_name,
            "source_relpath": item.source_relpath,
            "prepared_relpath": item.prepared_relpath or "",
            "file_type": item.file_type,
            "status": item.status,
            "matched_rule_id": item.matched_rule_id,
            "matched_keyword": item.matched_keyword,
            "target_preset_id": item.target_preset_id,
            "target_printer_name": item.target_printer_name,
            "target_preset_name": item.target_preset_name,
            "cups_job_id": item.cups_job_id or "",
            "error_message": item.error_message or "",
            "started_at": item.started_at,
            "finished_at": item.finished_at,
        }

    def build_job_payload(self, *, job: BatchPrintJob) -> dict[str, Any]:
        payload = self.build_job_summary_payload(job=job)
        payload["items"] = [
            self.build_job_item_payload(item=item)
            for item in job.items.order_by("order", "id")
        ]
        return payload

    @transaction.atomic
    def execute_job(self, *, job_id: uuid.UUID) -> None:
        job = self.get_job(job_id)
        if job.status in {BatchPrintJobStatus.COMPLETED, BatchPrintJobStatus.CANCELLED}:
            return

        BatchPrintJob.objects.filter(id=job.id).update(
            status=BatchPrintJobStatus.PROCESSING,
            started_at=timezone.now(),
            error_message="",
        )
        job.refresh_from_db()

        items = list(job.items.select_related("target_preset").order_by("order", "id"))
        storage = BatchPrintStorage(job.id)

        processed = 0
        success = 0
        failed = 0

        for item in items:
            job.refresh_from_db(fields=["cancel_requested"])
            if job.cancel_requested:
                BatchPrintItem.objects.filter(id=item.id, status=BatchPrintItemStatus.PENDING).update(
                    status=BatchPrintItemStatus.CANCELLED,
                    finished_at=timezone.now(),
                )
                continue

            started = timezone.now()
            BatchPrintItem.objects.filter(id=item.id).update(status=BatchPrintItemStatus.PROCESSING, started_at=started)

            try:
                if not item.target_preset:
                    raise ValidationException(message="未命中关键词规则", errors={"filename": item.source_original_name})

                prepared_path = self._file_prepare_service.prepare_for_print(item=item, storage=storage)
                cups_job_id = self._print_executor_service.print_pdf(
                    printer_name=item.target_preset.printer_name,
                    options={k: str(v) for k, v in (item.target_preset.executable_options_payload or {}).items()},
                    pdf_path=prepared_path,
                )
                BatchPrintItem.objects.filter(id=item.id).update(
                    status=BatchPrintItemStatus.COMPLETED,
                    prepared_relpath=normalize_to_media_rel(prepared_path.as_posix()),
                    cups_job_id=cups_job_id,
                    error_message="",
                    finished_at=timezone.now(),
                )
                success += 1
            except Exception as exc:
                BatchPrintItem.objects.filter(id=item.id).update(
                    status=BatchPrintItemStatus.FAILED,
                    error_message=str(exc)[:1000],
                    finished_at=timezone.now(),
                )
                failed += 1
                logger.exception("batch_print_item_failed", extra={"job_id": str(job.id), "item_id": item.id})

            processed += 1
            progress = int((processed / max(1, len(items))) * 100)
            BatchPrintJob.objects.filter(id=job.id).update(
                processed_count=processed,
                success_count=success,
                failed_count=failed,
                progress=progress,
            )

        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            final_status = BatchPrintJobStatus.CANCELLED
        elif failed == 0:
            final_status = BatchPrintJobStatus.COMPLETED
        elif success > 0:
            final_status = BatchPrintJobStatus.PARTIAL_FAILED
        else:
            final_status = BatchPrintJobStatus.FAILED

        BatchPrintJob.objects.filter(id=job.id).update(
            status=final_status,
            finished_at=timezone.now(),
            progress=100 if processed else 0,
            summary_payload={
                "processed_count": processed,
                "success_count": success,
                "failed_count": failed,
            },
        )
