"""PdfSplitService facade — 保持原有公共 API 不变。"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pymupdf as fitz
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.core.services.storage_service import sanitize_upload_filename
from apps.pdf_splitting.models import (
    PdfSplitJob,
    PdfSplitJobStatus,
    PdfSplitMode,
    PdfSplitOcrProfile,
    PdfSplitReviewFlag,
    PdfSplitSegment,
    PdfSplitSegmentType,
    PdfSplitStage,
)
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.pdf_splitting.services.template_registry import get_default_filename

from .export_utils import ExportUtils, deduplicate_filename, export_segment_pdf
from .markdown_builder import build_segments_markdown
from .ocr_handler import OCRHandler
from .pipeline import (
    PdfAnalysisOutcome,
    PipelineCancelled,
    analyze_pdf,
    build_page_descriptor,
    detect_segments_with_fallback,
    extract_pages,
)
from .segment_detector import SegmentDetector
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")


class PdfSplitService:
    MAX_PAGES = 300
    PREVIEW_DPI = 200
    PROGRESS_UPDATE_EVERY = 5
    CANCEL_CHECK_EVERY = 5

    def __init__(self, *, ocr_service: Any = None, llm_segment_detector: Any = None) -> None:
        self._ocr_service = ocr_service
        self._ocr_handler = OCRHandler()
        self._segment_detector = SegmentDetector()
        self._llm_segment_detector = llm_segment_detector
        self._export_utils = ExportUtils()

    # ==================================================================
    # 公共 API
    # ==================================================================

    def analyze_job(self, job: PdfSplitJob) -> None:  # pragma: no cover
        """内容分析任务的执行入口：编排交给 split.pipeline.analyze_pdf，这里只做任务态与持久化。"""
        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()

        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.PROCESSING,
            progress=0,
            processed_pages=0,
            current_page=0,
            error_message="",
        )

        job.refresh_from_db(fields=["cancel_requested", "split_mode", "ocr_profile", "template_key"])
        if job.cancel_requested:
            PdfSplitJob.objects.filter(id=job.id).update(
                status=PdfSplitJobStatus.CANCELLED,
                finished_at=timezone.now(),
            )
            return

        if job.split_mode == PdfSplitMode.PAGE_SPLIT:
            with fitz.open(storage.source_pdf_path) as doc:
                total_pages = int(doc.page_count)
            drafts = self._build_page_split_drafts(total_pages=total_pages, source_name=job.source_original_name)
            self._persist_page_split(
                job=job,
                drafts=drafts,
                total_pages=total_pages,
                storage=storage,
            )
            return

        def on_progress(resolved_pages: int, total_pages: int) -> None:
            # 每页都刷心跳（便宜，单列 update），进度写库才节流。
            # 这样「一页识别两分钟」的慢任务不会在两次进度回写之间被看门狗误判为死。
            self.touch_heartbeat(job_id=job.id)
            self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)

        def is_cancelled() -> bool:
            job.refresh_from_db(fields=["cancel_requested"])
            return bool(job.cancel_requested)

        try:
            outcome = analyze_pdf(
                storage.source_pdf_path,
                template_key=job.template_key,
                ocr_profile=job.ocr_profile,
                # 任务上存的版面策略（默认 fast_text）：补版面时电子页也会上云端，
                # 这样"原文坐标索引对照"对电子版 PDF 同样成立。
                layout_mode=getattr(job, "layout_mode", "fast_text"),
                # 平台偏好：auto=容灾；mineru/textin=锁定不降级
                cloud_backend=getattr(job, "cloud_backend", "auto"),
                on_progress=on_progress,
                is_cancelled=is_cancelled,
                ocr_handler=self._ocr_handler,
                llm_segment_detector=self._llm_segment_detector,
            )
        except PipelineCancelled:
            PdfSplitJob.objects.filter(id=job.id).update(
                status=PdfSplitJobStatus.CANCELLED,
                finished_at=timezone.now(),
            )
            return
        self._persist_analysis(job=job, storage=storage, outcome=outcome)

    def extract_stage(self, job: PdfSplitJob) -> tuple[list[Any], dict[str, Any]]:
        """两阶段任务链 ①：只做取字。

        把任务标成 processing + stage=extract，跑完后返回 pages 供调用方
        落盘。不在这里写 pages.json：落盘与推进阶段是编排层（tasks.py）的事，
        本方法保持“纯粹的二作”。
        """
        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        self._begin_stage(job, PdfSplitStage.EXTRACT)

        def on_progress(resolved_pages: int, total_pages: int) -> None:
            self.touch_heartbeat(job_id=job.id)
            self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)

        def is_cancelled() -> bool:
            job.refresh_from_db(fields=["cancel_requested"])
            return bool(job.cancel_requested)

        return extract_pages(
            storage.source_pdf_path,
            template_key=job.template_key,
            ocr_profile=job.ocr_profile,
            layout_mode=getattr(job, "layout_mode", "fast_text"),
            cloud_backend=getattr(job, "cloud_backend", "auto"),
            on_progress=on_progress,
            is_cancelled=is_cancelled,
            ocr_handler=self._ocr_handler,
        )

    def segment_stage(self, job: PdfSplitJob) -> None:
        """两阶段任务链 ②：从 pages.json 读回取字结果，只做分段与落库。"""
        from . import two_stage
        from .pipeline import PageDescriptor

        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        self._begin_stage(job, PdfSplitStage.SEGMENT)

        raw_pages = two_stage.load_pages(storage)
        if not raw_pages:
            raise ValueError("取字结果缺失（pages.json 不存在或为空），需重跑取字阶段")

        pages = [PageDescriptor(**item) for item in raw_pages]
        drafts, segment_summary = detect_segments_with_fallback(pages, template_key=job.template_key)

        bbox_backend = str(getattr(job, "cloud_backend", "") or "")
        outcome = PdfAnalysisOutcome(
            pages=pages,
            drafts=drafts,
            segments_md=build_segments_markdown(drafts, pages, bbox_backend=bbox_backend),
            summary=segment_summary,
        )
        self._persist_analysis(job=job, storage=storage, outcome=outcome)
        PdfSplitJob.objects.filter(id=job.id).update(stage=PdfSplitStage.DONE)

    def _begin_stage(self, job: PdfSplitJob, stage: str) -> None:
        """阶段开始：置 processing + 写阶段 + 刷心跳。"""
        now = timezone.now()
        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.PROCESSING,
            stage=stage,
            error_message="",
            heartbeat_at=now,
            updated_at=now,
        )

    def export_job(self, job: PdfSplitJob) -> None:  # pragma: no cover
        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        segments = list(job.segments.order_by("order", "id"))
        if not segments:
            raise ValueError("没有可导出的片段")

        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.EXPORTING,
            progress=0,
            error_message="",
        )

        pdf_files: list[tuple[bytes, str]] = []
        with fitz.open(storage.source_pdf_path) as source_doc:
            total = len(segments)
            seen_names: set[str] = set()
            for index, segment in enumerate(segments, start=1):
                job.refresh_from_db(fields=["cancel_requested"])
                if job.cancel_requested:
                    PdfSplitJob.objects.filter(id=job.id).update(
                        status=PdfSplitJobStatus.CANCELLED,
                        finished_at=timezone.now(),
                    )
                    return

                display_name = sanitize_upload_filename(segment.filename or get_default_filename(segment.segment_type))
                if not display_name.lower().endswith(".pdf"):
                    display_name = f"{display_name}.pdf"
                display_name = deduplicate_filename(display_name, seen_names)

                pdf_bytes = export_segment_pdf(source_doc, segment.page_start, segment.page_end)
                pdf_files.append((pdf_bytes, display_name))

                progress = int(index * 100 / total)
                PdfSplitJob.objects.filter(id=job.id).update(progress=progress)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_bytes, filename in pdf_files:
                zf.writestr(filename, file_bytes)
        storage.save_overwrite(storage.export_zip_path, ContentFile(zip_buffer.getvalue()))

    def render_preview(self, job: PdfSplitJob, page_no: int) -> Path:  # pragma: no cover
        storage = PdfSplitStorage(job.id)
        preview_path = storage.preview_path(page_no)
        if preview_path.exists():
            return preview_path

        with fitz.open(storage.source_pdf_path) as doc:
            if page_no < 1 or page_no > doc.page_count:
                raise ValueError("页码超出范围")
            page = doc.load_page(page_no - 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(self.PREVIEW_DPI / 72, self.PREVIEW_DPI / 72))
            storage.save_overwrite(preview_path, ContentFile(pix.tobytes("png")))
        return preview_path

    # ==================================================================
    # 内部方法
    # ==================================================================

    def _detect_segments_with_fallback(
        self, descriptors: list[PageDescriptor], *, template_key: str
    ) -> tuple[list[SegmentDraft], dict[str, Any]]:
        """分段检测（委托 split.pipeline；保留方法形态供既有调用方与测试）。"""
        return detect_segments_with_fallback(
            descriptors,
            template_key=template_key,
            llm_segment_detector=self._llm_segment_detector,
        )

    def _build_descriptor(
        self,
        *,
        page_no: int,
        text: str,
        source_method: str,
        ocr_failed: bool,
        template_key: str,
        layout: dict[str, Any] | None = None,
    ) -> PageDescriptor:
        """（旧签名委托 split.pipeline.build_page_descriptor；保留供既有调用方与测试）。"""
        return build_page_descriptor(
            page_no=page_no,
            text=text,
            source_method=source_method,
            ocr_failed=ocr_failed,
            template_key=template_key,
            layout=layout,
            segment_detector=self._segment_detector,
        )

    def _build_page_split_drafts(self, *, total_pages: int, source_name: str) -> list[SegmentDraft]:
        base_name = sanitize_upload_filename(Path(source_name or "document").stem) or "document"
        drafts: list[SegmentDraft] = []
        for page_no in range(1, total_pages + 1):
            drafts.append(
                SegmentDraft(
                    order=page_no,
                    page_start=page_no,
                    page_end=page_no,
                    segment_type=PdfSplitSegmentType.UNRECOGNIZED,
                    filename=f"{base_name}_第{page_no:03d}页.pdf",
                    confidence=1.0,
                    source_method="page_split",
                    review_flag=PdfSplitReviewFlag.NORMAL,
                )
            )
        return drafts

    def _persist_analysis(
        self,
        *,
        job: PdfSplitJob,
        storage: PdfSplitStorage,
        outcome: Any,
    ) -> None:  # pragma: no cover
        """把 pipeline 产物落库落盘：pages / segments / segments_md + 任务摘要（含取字与分段的观测字段）。"""
        storage.write_json(storage.pages_json_path, [asdict(item) for item in outcome.pages])
        storage.write_json(storage.segments_json_path, [asdict(item) for item in outcome.drafts])
        storage.write_json(storage.segments_md_path, outcome.segments_md)

        PdfSplitSegment.objects.filter(job=job).delete()
        PdfSplitSegment.objects.bulk_create(
            [
                PdfSplitSegment(
                    job=job,
                    order=item.order,
                    page_start=item.page_start,
                    page_end=item.page_end,
                    segment_type=item.segment_type,
                    filename=item.filename,
                    confidence=item.confidence,
                    source_method=item.source_method,
                    review_flag=item.review_flag,
                )
                for item in outcome.drafts
            ]
        )

        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.REVIEW_REQUIRED,
            progress=100,
            total_pages=len(outcome.pages),
            processed_pages=len(outcome.pages),
            current_page=len(outcome.pages),
            summary_payload={
                "split_mode": PdfSplitMode.CONTENT_ANALYSIS,
                "template_key": job.template_key,
                "template_version": job.template_version,
                **outcome.summary,
                "segment_count": len(outcome.drafts),
                "recognized_count": len(
                    [item for item in outcome.drafts if item.segment_type != PdfSplitSegmentType.UNRECOGNIZED]
                ),
                "unrecognized_count": len(
                    [item for item in outcome.drafts if item.segment_type == PdfSplitSegmentType.UNRECOGNIZED]
                ),
            },
        )

    def _persist_page_split(
        self,
        *,
        job: PdfSplitJob,
        drafts: list[SegmentDraft],
        total_pages: int,
        storage: PdfSplitStorage,
    ) -> None:  # pragma: no cover
        storage.write_json(storage.pages_json_path, [])
        storage.write_json(storage.segments_json_path, [asdict(item) for item in drafts])

        PdfSplitSegment.objects.filter(job=job).delete()
        PdfSplitSegment.objects.bulk_create(
            [
                PdfSplitSegment(
                    job=job,
                    order=item.order,
                    page_start=item.page_start,
                    page_end=item.page_end,
                    segment_type=item.segment_type,
                    filename=item.filename,
                    confidence=item.confidence,
                    source_method=item.source_method,
                    review_flag=item.review_flag,
                )
                for item in drafts
            ]
        )

        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.REVIEW_REQUIRED,
            progress=100,
            total_pages=total_pages,
            processed_pages=total_pages,
            current_page=total_pages,
            summary_payload={
                "split_mode": PdfSplitMode.PAGE_SPLIT,
                "template_key": job.template_key,
                "template_version": job.template_version,
                "segment_count": len(drafts),
                "recognized_count": 0,
                "unrecognized_count": len(drafts),
                "page_split": True,
            },
        )

    def _update_progress(self, *, job_id: Any, resolved_pages: int, total_pages: int) -> None:  # pragma: no cover
        progress = int(resolved_pages * 100 / total_pages) if total_pages else 0
        if resolved_pages % self.PROGRESS_UPDATE_EVERY == 0 or resolved_pages == total_pages:
            now = timezone.now()
            # 必须显式写 updated_at / heartbeat_at：`QuerySet.update()` 绕过 `auto_now`，
            # 不写的话这两个字段永远停在创建时刻，看门狗与前端都无法区分
            # 「任务在跑」与「worker 已死」。
            PdfSplitJob.objects.filter(id=job_id).update(
                total_pages=total_pages,
                processed_pages=resolved_pages,
                current_page=resolved_pages,
                progress=progress,
                updated_at=now,
                heartbeat_at=now,
            )

    def _should_check_cancel(self, marker: int) -> bool:
        return marker % self.CANCEL_CHECK_EVERY == 0

    def touch_heartbeat(self, *, job_id: Any) -> None:  # pragma: no cover
        """刷新心跳，不改变进度。

        为什么在进度回写之外还需要它：`_update_progress` 每 5 页才写一次库，
        而单页云端识别在 164 页扫描件上可能长达一两分钟。如果一页识别特别慢
        （或卡在云端排队），两次进度回写之间会超过看门狗的 `STALE_SECONDS`，
        把一个**仍在正常工作**的任务误判为死任务。心跳必须比进度更频繁。

        调用方（pipeline 的每页回调）负责调它；这里只负责写库。
        """
        now = timezone.now()
        PdfSplitJob.objects.filter(id=job_id).update(heartbeat_at=now, updated_at=now)


# 版面标题提取已下沉 split_models（pipeline / service 共用）；此处保留旧名再导出，
# 既有测试与潜在调用方仍从本模块引用
from .split_models import extract_layout_title as _extract_layout_title
