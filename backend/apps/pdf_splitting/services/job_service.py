from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import pymupdf as fitz
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.services.storage_service import normalize_to_media_rel, sanitize_upload_filename
from apps.pdf_splitting.models import (
    PdfSplitCloudBackend,
    PdfSplitJob,
    PdfSplitJobStatus,
    PdfSplitLayoutMode,
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


def _stale_seconds_for(job: PdfSplitJob) -> int | None:
    """任务已静默多少秒；非 processing 态返回 None。

    前端拿它跟超时阈值比，就能在“还在跑”与“大概卡死了”之间区分，
    而不是靠盲等。口径与 `job_recovery._last_liveness` 保持一致（心跳优先）。
    """
    if job.status != PdfSplitJobStatus.PROCESSING:
        return None
    candidates = [job.heartbeat_at, job.updated_at, job.started_at, job.created_at]
    last = max((item for item in candidates if item is not None), default=None)
    if last is None:
        return None
    return max(0, int((timezone.now() - last).total_seconds()))


class PdfSplitJobService:
    # 收件箱单文件上限已放宽到 1GB（整卷客户材料），这里必须跟上——否则
    # 材料包里的文件能传进来、却在自动分段时被拒，白上传一次。
    # 直连 pdf_splitting 的旧调用方（后台工作台）也跟着放宽，口径统一。
    MAX_FILE_SIZE = 1024 * 1024 * 1024
    # 页数：164 页的全彩诉讼卷宗是常态，整卷上报 500 页也不罕见。
    MAX_PAGES = 1000

    def create_job(
        self,
        *,
        file: UploadedFile | None,
        source_path: str | None,
        template_key: str,
        split_mode: str = PdfSplitMode.CONTENT_ANALYSIS,
        ocr_profile: str = PdfSplitOcrProfile.BALANCED,
        layout_mode: str = PdfSplitLayoutMode.FAST_TEXT,
        cloud_backend: str = PdfSplitCloudBackend.AUTO,
        created_by: Any | None = None,
    ) -> PdfSplitJob:  # pragma: no cover
        has_file = file is not None
        has_path = bool((source_path or "").strip())
        if has_file == has_path:
            raise ValidationException(message="file 与 source_path 必须二选一", errors={"input": "请仅提供一种来源"})

        template = get_template_definition(template_key)
        mode_key = self._normalize_split_mode(split_mode)
        profile_key = self._normalize_ocr_profile(ocr_profile)
        layout_key = self._normalize_layout_mode(layout_mode)
        cloud_key = self._normalize_cloud_backend(cloud_backend)
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
                storage.save_overwrite(storage.source_pdf_path, ContentFile(resolved_path.read_bytes()))
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
                layout_mode=layout_key,
                cloud_backend=cloud_key,
                status=PdfSplitJobStatus.PENDING,
                total_pages=total_pages,
                created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
                summary_payload={
                    "template_label": template.label,
                    "split_mode": mode_key,
                    "ocr_profile": profile_key,
                    "layout_mode": layout_key,
                    "cloud_backend": cloud_key,
                },
            )

            # 内容分析走**两阶段任务链**（取字 → 分段），每段各有 600s 预算。
            #
            # 单任务版本在 164 页真实卷宗上会被 Django-Q 的 worker 超时杀掉
            # （实测 164 页任务跑到 499s 被杀），而且杀掉后 OCR 成果全丢。拆分后
            # 取字产物落 pages.json + 逐页缓存，第二段被杀也不用重跑云端。
            if mode_key == PdfSplitMode.CONTENT_ANALYSIS:
                from apps.pdf_splitting.services.split.two_stage import TASK_EXTRACT

                task_id = build_task_submission_service().submit(
                    TASK_EXTRACT,
                    args=[str(job.id)],
                    task_name=f"pdf_split_extract_{job.id}",
                )
            else:
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

    def find_reusable_job(
        self,
        *,
        source_name: str,
        total_pages: int | None = None,
        user: Any = None,
    ) -> PdfSplitJob | None:
        """找一份**已经算好、可直接复用**的拆分任务。

        ## 为什么需要它

        否则会出现很难接受的浪费：律师已经跑完一次 164 页识别（云端 OCR +
        LLM 分段，5-10 分钟、几十元），但只要 `draft_state` 没被回写（没点过
        「自动识别」按钮、或换了浏览器），阅读器就拿不到结果 —— 再点一次
        就从零重跑，前面的钱和时间全白花。

        ## 匹配口径（三重，宁可找不到也不误用）

        1. `source_original_name` 完全相同（文件名是律师自己的命名习惯，区分度高）；
        2. `total_pages` 相同（防同名不同件）；
        3. `status` 属于**已产出结果**的状态（待复核 / 已完成）。

        刻意**不用**文件 hash：拆分任务的 source 是任务目录下的副本，拿它算
        hash 与材料包附件对不上，还得先下载整份（68MB）才能比——代价比收益大。
        三重条件已足够保守：同名 + 同页数 + 已出结果。

        Args:
            source_name: 原始文件名（`attachments_meta[].original_filename`）。
            total_pages: 页数；传 None 则不校验页数（仅在调用方拿不到页数时）。
            user: 传入时只看自己创建的任务（与 get_job 口径一致）。
        """
        if not source_name:
            return None

        queryset = PdfSplitJob.objects.filter(
            source_original_name=source_name,
            status__in=(PdfSplitJobStatus.REVIEW_REQUIRED, PdfSplitJobStatus.COMPLETED),
        )
        if total_pages is not None:
            queryset = queryset.filter(total_pages=total_pages)

        # ⚠️ 这里**刻意不按 created_by 过滤**。
        #
        # 复用的是「这份文件识别出的结果」，不是「某人的私人物品」：
        # 同一份材料包常由助理先跑一次、主办律师再来用；也有可能任务是用脚本/
        # 管理后台跑的（created_by 为空）。按属主过滤会让这些场景全部 miss，
        # 又退回「从零重跑 164 页」。
        #
        # 安全性由调用方保证：只有能打开该材料包的人（即持有对应 message_id
        # 读取权限的人）才会拿这个结果去用；本方法只返回 segments，不泄文件内容。
        # 保留 user 参数供未来需要隔离的租户场景使用。

        # 取最新的一份：同一文件可能被故意重跑过几次，律师要看的是最终结论
        return queryset.order_by("-created_at").first()

    def get_job(self, job_id: uuid.UUID, user: Any = None) -> PdfSplitJob:
        """获取拆解任务。

        传入 user 时按属主过滤（管理员全量），非本人任务按不存在处理
        （安全审计第4轮，口径同 doc_converter B-10）。
        """
        qs = PdfSplitJob.objects.prefetch_related("segments")
        if user is not None:
            from apps.core.security.admin_access import is_admin_user

            if not is_admin_user(user):
                qs = qs.filter(created_by=user)
        try:
            return qs.get(id=job_id)
        except PdfSplitJob.DoesNotExist:
            raise NotFoundError(message="拆解任务不存在", code="PDF_SPLIT_JOB_NOT_FOUND", errors={}) from None

    def build_job_payload(self, job: PdfSplitJob) -> dict[str, Any]:
        md_path = PdfSplitStorage(job.id).segments_md_path
        md_by_order = load_segments_md(md_path)
        pos_by_order = load_segments_positioned(md_path)
        flags_by_order = load_segments_quality_flags(md_path)
        segments = [
            self._serialize_segment(
                item,
                markdown=md_by_order.get(item.order, ""),
                positioned=pos_by_order.get(item.order, []),
                quality_flags=flags_by_order.get(item.order, []),
            )
            for item in job.segments.order_by("order", "id")
        ]
        download_url = ""
        if job.status == PdfSplitJobStatus.COMPLETED and job.export_zip_relpath:
            download_url = f"/api/v1/pdf-splitting/jobs/{job.id}/download"
        pdf_url = f"/api/v1/pdf-splitting/jobs/{job.id}/pdf"

        return {
            "job_id": str(job.id),
            "status": job.status,
            "split_mode": job.split_mode,
            "ocr_profile": job.ocr_profile,
            "layout_mode": getattr(job, "layout_mode", PdfSplitLayoutMode.FAST_TEXT),
            "cloud_backend": getattr(job, "cloud_backend", PdfSplitCloudBackend.AUTO),
            "progress": int(job.progress or 0),
            "total_pages": int(job.total_pages or 0),
            "processed_pages": int(job.processed_pages or 0),
            "current_page": int(job.current_page or 0),
            "summary": dict(job.summary_payload or {}),
            "segments": segments,
            "download_url": download_url,
            "pdf_url": pdf_url,
            "error_message": job.error_message or "",
            # ↓↓ 存活信息：前端据此判断「在跑」还是「卡死了」，不必等满 14 分钟超时。
            #
            # stale_seconds 为 null 表示非 processing 态（终态或待人工），不参与判活。
            # 前端拿到 stale_seconds 为正的整数时，应该把「长时间无变化」提示成
            # 「可能已中断」并给出重试入口，而不是继续转圈。
            "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "stale_seconds": _stale_seconds_for(job),
        }

    @transaction.atomic
    def confirm_segments(
        self, *, job_id: uuid.UUID, items: list[dict[str, Any]], user: Any = None
    ) -> PdfSplitJob:  # pragma: no cover
        job = self.get_job(job_id, user=user)
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

    def request_cancel(self, *, job_id: uuid.UUID, user: Any = None) -> PdfSplitJob:  # pragma: no cover
        job = self.get_job(job_id, user=user)
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
            not job.task_id or bool(cancel_result.get("queue_deleted")) or not bool(cancel_result.get("running"))
        )
        if can_mark_cancelled:
            updates.update(status=PdfSplitJobStatus.CANCELLED, finished_at=timezone.now())
        PdfSplitJob.objects.filter(id=job.id).update(**updates)
        job.refresh_from_db()
        return job

    def mark_completed(self, *, job_id: uuid.UUID, export_zip_relpath: str) -> None:  # pragma: no cover
        PdfSplitJob.objects.filter(id=job_id).update(
            status=PdfSplitJobStatus.COMPLETED,
            progress=100,
            export_zip_relpath=export_zip_relpath,
            finished_at=timezone.now(),
            error_message="",
        )

    def mark_failed(self, *, job_id: uuid.UUID, error_message: str) -> None:  # pragma: no cover
        PdfSplitJob.objects.filter(id=job_id).update(
            status=PdfSplitJobStatus.FAILED,
            error_message=error_message[:4000],
            finished_at=timezone.now(),
        )

    def _serialize_segment(
        self,
        segment: PdfSplitSegment,
        *,
        markdown: str = "",
        positioned: list[dict[str, Any]] | None = None,
        quality_flags: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": segment.id,
            "order": segment.order,
            "page_start": segment.page_start,
            "page_end": segment.page_end,
            "segment_type": segment.segment_type,
            "segment_label": _segment_display_label(segment),
            "filename": segment.filename,
            "confidence": round(float(segment.confidence or 0.0), 3),
            "review_flag": segment.review_flag,
            "review_flag_label": segment.get_review_flag_display(),
            "source_method": segment.source_method,
            "content_md": markdown,
            # 该段正文块 + 归一化矩形（识别定位用）；无坐标的后端/旧任务为空表
            "positioned": positioned or [],
            # 该段的识别质量提示（如「疑似错字：受办人（全本 178 次写作「经办人」…）」）；
            # 旧任务没有该字段，回空表。只是提示，不影响段本身的可用性。
            "quality_flags": quality_flags or [],
        }

    def _normalize_confirmed_segments(self, *, items: list[dict[str, Any]], total_pages: int) -> list[dict[str, Any]]:
        if not items:
            raise ValidationException(message="请至少保留一个片段", errors={"segments": "片段列表不能为空"})

        normalized_items: list[dict[str, Any]] = []
        for raw in items:
            try:
                page_start = int(raw.get("page_start"))  # type: ignore[arg-type]
                page_end = int(raw.get("page_end"))  # type: ignore[arg-type]
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

    def _save_uploaded_pdf(self, file: UploadedFile, target_path: Path) -> str:  # pragma: no cover
        from django.conf import settings
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

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
        media_root = Path(settings.MEDIA_ROOT)
        rel_path = target_path.relative_to(media_root).as_posix()
        content = file.read()
        default_storage.save(rel_path, ContentFile(content))
        return sanitize_upload_filename(file_name)

    def _validate_local_pdf_path(self, source_path: str) -> Path:
        raw = (source_path or "").strip()
        if not raw:
            raise ValidationException(message="source_path 不能为空", errors={"source_path": "请输入本地PDF绝对路径"})
        if raw.lower().startswith("smb://"):
            raise ValidationException(
                message="不支持 smb:// 路径", errors={"source_path": "请提供本机可读取的绝对路径"}
            )
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

        # 安全审计 B-11：本地路径仅允许在配置的浏览根（FOLDER_BROWSE_ROOTS）或
        # MEDIA_ROOT 内——否则任意登录用户可拆解并回读服务器上任意 PDF。
        from django.conf import settings as _settings

        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        allowed = list(getattr(_settings, "FOLDER_BROWSE_ROOTS", []) or [])
        media_root = Path(str(_settings.MEDIA_ROOT)).resolve()
        candidate_roots = [Path(r).expanduser().resolve() for r in allowed if r] + [media_root]
        if not any(resolved == r or r in resolved.parents for r in candidate_roots):
            raise ValidationException(
                message="路径越界：仅允许浏览根目录内的文件",
                errors={"source_path": raw},
            )
        return resolved

    def _validate_pdf_file(self, source_pdf_path: Path) -> int:  # pragma: no cover
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
        except (TypeError, ValueError):
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

    def _normalize_cloud_backend(self, value: str | None) -> str:
        """平台偏好归一化：非法值一律落回 auto（可容灾、行为最稳）。"""
        mode = str(value or "").strip().lower()
        valid = {choice for choice, _label in PdfSplitCloudBackend.choices}
        return mode if mode in valid else PdfSplitCloudBackend.AUTO

    def _normalize_layout_mode(self, value: str | None) -> str:
        """版面策略归一化：非法值一律落回 fast_text（不调云端）。

        默认必须是保守的那个——传错了顶多拿不到坐标，不会悄悄烧云端费用。
        """
        mode = str(value or "").strip().lower()
        valid_modes = {choice for choice, _label in PdfSplitLayoutMode.choices}
        if mode in valid_modes:
            return mode
        return PdfSplitLayoutMode.FAST_TEXT

    def _normalize_split_mode(self, value: str | None) -> str:
        mode = str(value or "").strip().lower()
        valid_modes = {choice for choice, _label in PdfSplitMode.choices}
        if mode in valid_modes:
            return mode
        return PdfSplitMode.CONTENT_ANALYSIS


# ↓↓ 由 PdfSplitJobService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _segment_display_label(segment: PdfSplitSegment) -> str:
    """片段展示名：LLM 的开放命名（借条 / 转账凭证等，超出模板枚举）记在
    filename 里、类型仍为 unrecognized——这里把文件名（去 .pdf）透出为
    segment_label，前端把它当类型胶囊展示；规则引擎的未识别段不受影响。"""
    if segment.segment_type == PdfSplitSegmentType.UNRECOGNIZED and str(segment.source_method or "").startswith("llm"):
        stem = re.sub(r"\.pdf$", "", segment.filename or "", flags=re.IGNORECASE).strip()
        if stem and not stem.startswith("未识别材料"):
            return stem
    return get_segment_label(segment.segment_type)


def load_segments_md(path: Path) -> dict[int, str]:
    """读分段 Markdown 产物（order → 正文）；文件缺失 / 损坏一律回空表——
    旧任务没有 md 产物，content_md 退化为空串，不阻断任务详情接口。"""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("pdf_split_segments_md_read_failed", extra={"path": str(path)})
        return {}
    if not isinstance(payload, list):
        return {}
    result: dict[int, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        result[order] = str(item.get("markdown") or "")
    return result


def load_segments_quality_flags(path: Path) -> dict[int, list[str]]:
    """读分段的质量标记（order → quality_flags）。

    与 ``load_segments_md`` / ``load_segments_positioned`` 同源同文件
    （``segments_md.json`` 每段条目的 ``quality_flags``）：段级提示与正文出自同一次
    一致性校对，分文件存迟早会对不上。旧任务没有该字段，或产物损坏时回空表——
    前端按「这一段没有质量提示」降级，不阻断任务详情接口。
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    result: dict[int, list[str]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        flags = item.get("quality_flags")
        if isinstance(flags, list):
            result[order] = [str(flag) for flag in flags if isinstance(flag, str) and flag]
    return result


def load_segments_positioned(path: Path) -> dict[int, list[dict[str, Any]]]:
    """读分段「可定位块」（order → positioned 列表）。

    与 ``load_segments_md`` 同源同文件（``segments_md.json`` 的 ``positioned``
    字段）：布局与正文来自同一次解析，分两个文件存迟早会对不上。
    旧任务没有该字段、或产物损坏时一律回空表——前端按「没有坐标」降级处理，
    不阻断任务详情接口。
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    result: dict[int, list[dict[str, Any]]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        positioned = item.get("positioned")
        if isinstance(positioned, list):
            result[order] = [b for b in positioned if isinstance(b, dict)]
    return result
