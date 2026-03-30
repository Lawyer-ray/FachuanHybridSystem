from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

import fitz
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.storage_service import normalize_to_media_rel, sanitize_upload_filename
from apps.pdf_splitting.models import (
    PdfSplitJob,
    PdfSplitJobStatus,
    PdfSplitMode,
    PdfSplitOcrProfile,
    PdfSplitReviewFlag,
    PdfSplitSegment,
    PdfSplitSegmentType,
    PdfSplitSourceType,
)

from .storage import PdfSplitStorage
from .template_registry import get_default_filename, get_segment_label, get_template_definition

logger = logging.getLogger("apps.pdf_splitting")

_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


class PdfSplitJobService:
    MAX_FILE_SIZE = 150 * 1024 * 1024
    MAX_PAGES = 300

    def create_job(
        self,
        *,
        file: UploadedFile | None,
        source_path: str | None,
        template_key: str,
        split_mode: str = PdfSplitMode.CONTENT_ANALYSIS,
        ocr_profile: str = PdfSplitOcrProfile.BALANCED,
        created_by: Any | None = None,
    ) -> PdfSplitJob:
        has_file = file is not None
        has_path = bool((source_path or "").strip())
        if has_file == has_path:
            raise ValidationException(message="file 与 source_path 必须二选一", errors={"input": "请仅提供一种来源"})

        template = get_template_definition(template_key)
        mode_key = self._normalize_split_mode(split_mode)
        profile_key = self._normalize_ocr_profile(ocr_profile)
        job_id = uuid.uuid4()
        storage = PdfSplitStorage(job_id)
        storage.ensure_dirs()
        job: PdfSplitJob | None = None

        original_name = ""
        original_abs_path = ""
        try:
            if file is not None:
                original_name = self._save_uploaded_pdf(file, storage.source_pdf_path)
                source_type = PdfSplitSourceType.UPLOAD
            else:
                resolved_path = self._validate_local_pdf_path(source_path or "")
                original_name = resolved_path.name
                original_abs_path = resolved_path.as_posix()
                shutil.copyfile(resolved_path, storage.source_pdf_path)
                source_type = PdfSplitSourceType.LOCAL_PATH

            total_pages = self._validate_pdf_file(storage.source_pdf_path)
            rel_path = normalize_to_media_rel(storage.source_pdf_path.as_posix())

            job = PdfSplitJob.objects.create(
                id=job_id,
                source_type=source_type,
                source_abs_path=original_abs_path,
                source_relpath=rel_path,
                source_original_name=original_name,
                split_mode=mode_key,
                template_key=template.key,
                template_version=template.version,
                ocr_profile=profile_key,
                status=PdfSplitJobStatus.PENDING,
                total_pages=total_pages,
                created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
                summary_payload={
                    "template_label": template.label,
                    "split_mode": mode_key,
                    "ocr_profile": profile_key,
                },
            )

            task_id = build_task_submission_service().submit(
                "apps.pdf_splitting.tasks.execute_pdf_split_job",
                args=[str(job.id)],
                task_name=f"pdf_split_{job.id}",
            )
            PdfSplitJob.objects.filter(id=job.id).update(task_id=str(task_id), started_at=timezone.now())
            job.refresh_from_db()
            return job
        except Exception:
            if job is not None:
                job.delete()
            storage.cleanup()
            raise

    def get_job(self, job_id: uuid.UUID) -> PdfSplitJob:
        try:
            return PdfSplitJob.objects.prefetch_related("segments").get(id=job_id)
        except PdfSplitJob.DoesNotExist:
            raise NotFoundError(message="拆解任务不存在", code="PDF_SPLIT_JOB_NOT_FOUND", errors={}) from None

    def build_job_payload(self, job: PdfSplitJob) -> dict[str, Any]:
        segments = [self._serialize_segment(item) for item in job.segments.order_by("order", "id")]
        download_url = ""
        if job.status == PdfSplitJobStatus.COMPLETED and job.export_zip_relpath:
            download_url = f"/api/v1/pdf-splitting/jobs/{job.id}/download"
        pdf_url = f"/api/v1/pdf-splitting/jobs/{job.id}/pdf"

        return {
            "job_id": str(job.id),
            "status": job.status,
            "split_mode": job.split_mode,
            "ocr_profile": job.ocr_profile,
            "progress": int(job.progress or 0),
            "total_pages": int(job.total_pages or 0),
            "processed_pages": int(job.processed_pages or 0),
            "current_page": int(job.current_page or 0),
            "summary": dict(job.summary_payload or {}),
            "segments": segments,
            "download_url": download_url,
            "pdf_url": pdf_url,
            "error_message": job.error_message or "",
        }

    @transaction.atomic
    def confirm_segments(self, *, job_id: uuid.UUID, items: list[dict[str, Any]]) -> PdfSplitJob:
        job = self.get_job(job_id)
        if job.status not in {PdfSplitJobStatus.REVIEW_REQUIRED, PdfSplitJobStatus.COMPLETED}:
            raise ValidationException(message="当前状态不允许确认导出", errors={"status": job.status})

        normalized = self._normalize_confirmed_segments(items=items, total_pages=job.total_pages)
        PdfSplitSegment.objects.filter(job=job).delete()
        PdfSplitSegment.objects.bulk_create(
            [
                PdfSplitSegment(
                    job=job,
                    order=index,
                    page_start=item["page_start"],
                    page_end=item["page_end"],
                    segment_type=item["segment_type"],
                    filename=item["filename"],
                    confidence=float(item.get("confidence", 0.0)),
                    source_method=str(item.get("source_method") or "manual"),
                    review_flag=str(item.get("review_flag") or PdfSplitReviewFlag.NORMAL),
                )
                for index, item in enumerate(normalized, start=1)
            ]
        )

        storage = PdfSplitStorage(job.id)
        storage.write_json(storage.segments_json_path, normalized)

        task_id = build_task_submission_service().submit(
            "apps.pdf_splitting.tasks.export_pdf_split_job",
            args=[str(job.id)],
            task_name=f"pdf_split_export_{job.id}",
        )
        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.EXPORTING,
            progress=0,
            task_id=str(task_id),
            cancel_requested=False,
            error_message="",
        )
        job.refresh_from_db()
        return job

    def request_cancel(self, *, job_id: uuid.UUID) -> PdfSplitJob:
        job = self.get_job(job_id)
        if job.status in {PdfSplitJobStatus.COMPLETED, PdfSplitJobStatus.FAILED, PdfSplitJobStatus.CANCELLED}:
            return job

        cancel_result: dict[str, Any] = {}
        if job.task_id:
            try:
                cancel_result = build_task_submission_service().cancel(job.task_id)
            except Exception:
                logger.exception("pdf_split_cancel_failed", extra={"job_id": str(job.id), "task_id": job.task_id})

        updates: dict[str, Any] = {"cancel_requested": True}
        can_mark_cancelled = job.status == PdfSplitJobStatus.PENDING and (
            not job.task_id
            or bool(cancel_result.get("queue_deleted"))
            or not bool(cancel_result.get("running"))
        )
        if can_mark_cancelled:
            updates.update(status=PdfSplitJobStatus.CANCELLED, finished_at=timezone.now())
        PdfSplitJob.objects.filter(id=job.id).update(**updates)
        job.refresh_from_db()
        return job

    def mark_completed(self, *, job_id: uuid.UUID, export_zip_relpath: str) -> None:
        PdfSplitJob.objects.filter(id=job_id).update(
            status=PdfSplitJobStatus.COMPLETED,
            progress=100,
            export_zip_relpath=export_zip_relpath,
            finished_at=timezone.now(),
            error_message="",
        )

    def mark_failed(self, *, job_id: uuid.UUID, error_message: str) -> None:
        PdfSplitJob.objects.filter(id=job_id).update(
            status=PdfSplitJobStatus.FAILED,
            error_message=error_message[:4000],
            finished_at=timezone.now(),
        )

    def _serialize_segment(self, segment: PdfSplitSegment) -> dict[str, Any]:
        return {
            "id": segment.id,
            "order": segment.order,
            "page_start": segment.page_start,
            "page_end": segment.page_end,
            "segment_type": segment.segment_type,
            "segment_label": get_segment_label(segment.segment_type),
            "filename": segment.filename,
            "confidence": round(float(segment.confidence or 0.0), 3),
            "review_flag": segment.review_flag,
            "review_flag_label": segment.get_review_flag_display(),
            "source_method": segment.source_method,
        }

    def _normalize_confirmed_segments(self, *, items: list[dict[str, Any]], total_pages: int) -> list[dict[str, Any]]:
        if not items:
            raise ValidationException(message="请至少保留一个片段", errors={"segments": "片段列表不能为空"})

        normalized_items: list[dict[str, Any]] = []
        for raw in items:
            try:
                page_start = int(raw.get("page_start"))
                page_end = int(raw.get("page_end"))
            except (TypeError, ValueError):
                raise ValidationException(message="页码必须为整数", errors={"segments": "页码必须为整数"}) from None
            if page_start < 1 or page_end < page_start or page_end > total_pages:
                raise ValidationException(message="片段页码非法", errors={"segments": "页码范围不合法"})

            segment_type = str(raw.get("segment_type") or PdfSplitSegmentType.UNRECOGNIZED)
            valid_segment_types = {choice for choice, _label in PdfSplitSegmentType.choices}
            if segment_type not in valid_segment_types:
                segment_type = PdfSplitSegmentType.UNRECOGNIZED

            filename = str(raw.get("filename") or "").strip()
            if not filename:
                default_name = get_default_filename(segment_type)
                if segment_type == PdfSplitSegmentType.UNRECOGNIZED:
                    default_name = f"未识别材料_{page_start}-{page_end}"
                filename = default_name
            filename = sanitize_upload_filename(filename)
            if not filename.lower().endswith(".pdf"):
                filename = f"{filename}.pdf"

            review_flag = str(raw.get("review_flag") or PdfSplitReviewFlag.NORMAL)
            if segment_type == PdfSplitSegmentType.UNRECOGNIZED:
                review_flag = PdfSplitReviewFlag.UNRECOGNIZED

            normalized_items.append(
                {
                    "page_start": page_start,
                    "page_end": page_end,
                    "segment_type": segment_type,
                    "filename": filename,
                    "confidence": float(raw.get("confidence") or 0.0),
                    "source_method": str(raw.get("source_method") or "manual"),
                    "review_flag": review_flag,
                }
            )

        normalized_items.sort(key=lambda item: (item["page_start"], item["page_end"]))
        previous_end = 0
        filled: list[dict[str, Any]] = []
        for item in normalized_items:
            if item["page_start"] <= previous_end:
                raise ValidationException(message="片段页码重叠", errors={"segments": "片段存在重叠"})
            if item["page_start"] > previous_end + 1:
                gap_start = previous_end + 1
                gap_end = item["page_start"] - 1
                filled.append(
                    {
                        "page_start": gap_start,
                        "page_end": gap_end,
                        "segment_type": PdfSplitSegmentType.UNRECOGNIZED,
                        "filename": f"未识别材料_{gap_start}-{gap_end}.pdf",
                        "confidence": 0.0,
                        "source_method": "gap_fill",
                        "review_flag": PdfSplitReviewFlag.UNRECOGNIZED,
                    }
                )
            filled.append(item)
            previous_end = item["page_end"]

        if previous_end < total_pages:
            gap_start = previous_end + 1
            filled.append(
                {
                    "page_start": gap_start,
                    "page_end": total_pages,
                    "segment_type": PdfSplitSegmentType.UNRECOGNIZED,
                    "filename": f"未识别材料_{gap_start}-{total_pages}.pdf",
                    "confidence": 0.0,
                    "source_method": "gap_fill",
                    "review_flag": PdfSplitReviewFlag.UNRECOGNIZED,
                }
            )
        return filled

    def _save_uploaded_pdf(self, file: UploadedFile, target_path: Path) -> str:
        file_name = file.name or "upload.pdf"
        ext = Path(file_name).suffix.lower()
        if ext != ".pdf":
            raise ValidationException(message="仅支持 PDF 文件", errors={"file": "文件扩展名必须为 .pdf"})
        file_size = int(file.size or 0)
        if file_size <= 0:
            raise ValidationException(message="上传文件为空", errors={"file": "文件不能为空"})
        if file_size > self.MAX_FILE_SIZE:
            raise ValidationException(
                message="文件大小超过限制",
                errors={"file": f"文件大小不能超过 {self.MAX_FILE_SIZE // 1024 // 1024}MB"},
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as output:
            for chunk in file.chunks():
                output.write(chunk)
        return sanitize_upload_filename(file_name)

    def _validate_local_pdf_path(self, source_path: str) -> Path:
        raw = (source_path or "").strip()
        if not raw:
            raise ValidationException(message="source_path 不能为空", errors={"source_path": "请输入本地PDF绝对路径"})
        if raw.lower().startswith("smb://"):
            raise ValidationException(message="不支持 smb:// 路径", errors={"source_path": "请提供本机可读取的绝对路径"})
        if not self._is_absolute_path(raw):
            raise ValidationException(message="source_path 必须为绝对路径", errors={"source_path": "请提供绝对路径"})

        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            raise ValidationException(message="路径无法访问", errors={"source_path": raw}) from None
        if not resolved.exists():
            raise ValidationException(message="路径不存在", errors={"source_path": raw})
        if not resolved.is_file():
            raise ValidationException(message="路径不是文件", errors={"source_path": raw})
        if resolved.suffix.lower() != ".pdf":
            raise ValidationException(message="仅支持 PDF 文件", errors={"source_path": raw})
        if not os.access(resolved, os.R_OK):
            raise ValidationException(message="文件不可读", errors={"source_path": raw})
        return resolved

    def _validate_pdf_file(self, source_pdf_path: Path) -> int:
        file_size = int(source_pdf_path.stat().st_size) if source_pdf_path.exists() else 0
        if file_size <= 0:
            raise ValidationException(message="PDF 文件为空", errors={"file": "PDF 文件不能为空"})
        if file_size > self.MAX_FILE_SIZE:
            raise ValidationException(
                message="文件大小超过限制",
                errors={"file": f"文件大小不能超过 {self.MAX_FILE_SIZE // 1024 // 1024}MB"},
            )
        try:
            with fitz.open(source_pdf_path) as doc:
                total_pages = int(doc.page_count)
        except Exception:
            raise ValidationException(message="PDF 无法打开", errors={"file": "PDF 文件损坏或格式不正确"}) from None

        if total_pages <= 0:
            raise ValidationException(message="PDF 没有页面", errors={"file": "PDF 页面数必须大于 0"})
        if total_pages > self.MAX_PAGES:
            raise ValidationException(message="PDF 页数超过限制", errors={"file": f"PDF 页数不能超过 {self.MAX_PAGES}"})
        return total_pages

    def _is_absolute_path(self, value: str) -> bool:
        return value.startswith("/") or value.startswith("\\") or bool(_WINDOWS_ABS_RE.match(value))

    def _normalize_ocr_profile(self, value: str | None) -> str:
        profile = str(value or "").strip().lower()
        valid_profiles = {choice for choice, _label in PdfSplitOcrProfile.choices}
        if profile in valid_profiles:
            return profile
        return PdfSplitOcrProfile.BALANCED

    def _normalize_split_mode(self, value: str | None) -> str:
        mode = str(value or "").strip().lower()
        valid_modes = {choice for choice, _label in PdfSplitMode.choices}
        if mode in valid_modes:
            return mode
        return PdfSplitMode.CONTENT_ANALYSIS
