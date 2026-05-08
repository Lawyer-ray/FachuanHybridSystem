"""PdfSplitService facade — 保持原有公共 API 不变。"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import fitz
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
)
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.pdf_splitting.services.template_registry import get_default_filename, get_template_definition

from .export_utils import ExportUtils
from .ocr_handler import OCRHandler
from .segment_detector import SegmentDetector
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")


class PdfSplitService:
    MAX_PAGES = 300
    PREVIEW_DPI = 200
    PROGRESS_UPDATE_EVERY = 5
    CANCEL_CHECK_EVERY = 5

    def __init__(self, *, ocr_service: Any = None) -> None:
        self._ocr_service = ocr_service
        self._ocr_handler = OCRHandler()
        self._segment_detector = SegmentDetector()
        self._export_utils = ExportUtils()

    # ==================================================================
    # 公共 API
    # ==================================================================

    def analyze_job(self, job: PdfSplitJob) -> None:
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

        runtime_profile = self._ocr_handler.resolve_runtime_profile(job.ocr_profile)
        pdf_hash = self._ocr_handler.sha256_file(storage.source_pdf_path)
        resolved_pages = 0
        cache_hit_count = 0

        with fitz.open(storage.source_pdf_path) as doc:
            total_pages = int(doc.page_count)
            template = get_template_definition(job.template_key)
            descriptors: list[PageDescriptor | None] = [None] * total_pages
            pending_page_numbers: list[int] = []
            for page_index in range(total_pages):
                if self._should_check_cancel(page_index):
                    job.refresh_from_db(fields=["cancel_requested"])
                if job.cancel_requested:
                    PdfSplitJob.objects.filter(id=job.id).update(
                        status=PdfSplitJobStatus.CANCELLED,
                        finished_at=timezone.now(),
                    )
                    return

                page_no = page_index + 1
                page = doc.load_page(page_index)
                direct_text = page.get_text("text") or ""
                if self._segment_detector.is_effective_text(direct_text):
                    descriptors[page_index] = self._build_descriptor(
                        page_no=page_no,
                        text=direct_text,
                        source_method="text",
                        ocr_failed=False,
                        template_key=template.key,
                    )
                    resolved_pages += 1
                    self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)
                    continue

                cached = self._ocr_handler.read_ocr_cache(
                    pdf_hash=pdf_hash, profile_key=runtime_profile.key, page_no=page_no
                )
                if cached is not None:
                    descriptors[page_index] = self._build_descriptor(
                        page_no=page_no,
                        text=cached.text,
                        source_method="ocr_cache" if cached.text else "ocr_failed_cache",
                        ocr_failed=cached.ocr_failed,
                        template_key=template.key,
                    )
                    resolved_pages += 1
                    cache_hit_count += 1
                    self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)
                    continue

                pending_page_numbers.append(page_no)

            if pending_page_numbers:
                ocr_results = self._ocr_handler.parallel_ocr(
                    pdf_path=storage.source_pdf_path,
                    page_numbers=pending_page_numbers,
                    runtime_profile=runtime_profile,
                )
                for page_no in pending_page_numbers:
                    if self._should_check_cancel(page_no):
                        job.refresh_from_db(fields=["cancel_requested"])
                    if job.cancel_requested:
                        PdfSplitJob.objects.filter(id=job.id).update(
                            status=PdfSplitJobStatus.CANCELLED,
                            finished_at=timezone.now(),
                        )
                        return

                    result = ocr_results.get(page_no)
                    if result is None:
                        from .split_models import OCRPageResult

                        result = OCRPageResult(
                            page_no=page_no,
                            text="",
                            source_method="ocr_failed",
                            ocr_failed=True,
                        )
                    self._ocr_handler.write_ocr_cache(
                        pdf_hash=pdf_hash,
                        profile_key=runtime_profile.key,
                        result=result,
                    )
                    descriptors[page_no - 1] = self._build_descriptor(
                        page_no=page_no,
                        text=result.text,
                        source_method=result.source_method,
                        ocr_failed=result.ocr_failed,
                        template_key=template.key,
                    )
                    resolved_pages += 1
                    self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)

            final_descriptors = [item for item in descriptors if item is not None]
            drafts = self._segment_detector.detect_segments(final_descriptors, template_key=template.key)
            self._persist_analysis(
                job=job,
                descriptors=final_descriptors,
                drafts=drafts,
                storage=storage,
                runtime_profile=runtime_profile,
                cache_hit_count=cache_hit_count,
                pending_ocr_count=len(pending_page_numbers),
            )

    def export_job(self, job: PdfSplitJob) -> None:
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

        pdf_files: list[tuple[Path, str]] = []
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

                display_name = sanitize_upload_filename(
                    segment.filename or get_default_filename(segment.segment_type)
                )
                if not display_name.lower().endswith(".pdf"):
                    display_name = f"{display_name}.pdf"
                display_name = self._export_utils.deduplicate_filename(display_name, seen_names)

                output_path = storage.export_pdf_path(display_name)
                self._export_utils.export_segment_pdf(source_doc, segment.page_start, segment.page_end, output_path)
                pdf_files.append((output_path, display_name))

                progress = int(index * 100 / total)
                PdfSplitJob.objects.filter(id=job.id).update(progress=progress)

        with zipfile.ZipFile(storage.export_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path, filename in pdf_files:
                zf.write(file_path, arcname=filename)

    def render_preview(self, job: PdfSplitJob, page_no: int) -> Path:
        storage = PdfSplitStorage(job.id)
        preview_path = storage.preview_path(page_no)
        if preview_path.exists():
            return preview_path

        with fitz.open(storage.source_pdf_path) as doc:
            if page_no < 1 or page_no > doc.page_count:
                raise ValueError("页码超出范围")
            page = doc.load_page(page_no - 1)
            pix = page.get_pixmap(
                matrix=fitz.Matrix(self.PREVIEW_DPI / 72, self.PREVIEW_DPI / 72)
            )
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(preview_path.as_posix())
        return preview_path

    # ==================================================================
    # 内部方法
    # ==================================================================

    def _build_descriptor(
        self,
        *,
        page_no: int,
        text: str,
        source_method: str,
        ocr_failed: bool,
        template_key: str,
    ) -> PageDescriptor:
        normalized_text = self._segment_detector.normalize_text(text)
        head_text = normalized_text[:240]
        top_candidates = self._segment_detector.score_page(
            head_text=head_text, normalized_text=normalized_text, template_key=template_key
        )
        return PageDescriptor(
            page_no=page_no,
            text=text,
            normalized_text=normalized_text,
            head_text=head_text,
            source_method=source_method,
            ocr_failed=ocr_failed,
            top_candidates=top_candidates,
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
        descriptors: list[PageDescriptor],
        drafts: list[SegmentDraft],
        storage: PdfSplitStorage,
        runtime_profile: Any,
        cache_hit_count: int,
        pending_ocr_count: int,
    ) -> None:
        storage.write_json(storage.pages_json_path, [asdict(item) for item in descriptors])
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
            total_pages=len(descriptors),
            processed_pages=len(descriptors),
            current_page=len(descriptors),
            summary_payload={
                "split_mode": PdfSplitMode.CONTENT_ANALYSIS,
                "template_key": job.template_key,
                "template_version": job.template_version,
                "ocr_profile": runtime_profile.key,
                "ocr_dpi": runtime_profile.dpi,
                "ocr_model": "v5_server" if runtime_profile.use_v5 else "v4_default",
                "ocr_workers": runtime_profile.workers,
                "ocr_cache_hit_count": int(max(cache_hit_count, 0)),
                "ocr_miss_count": int(max(pending_ocr_count, 0)),
                "segment_count": len(drafts),
                "recognized_count": len(
                    [item for item in drafts if item.segment_type != PdfSplitSegmentType.UNRECOGNIZED]
                ),
                "unrecognized_count": len(
                    [item for item in drafts if item.segment_type == PdfSplitSegmentType.UNRECOGNIZED]
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
    ) -> None:
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

    def _update_progress(self, *, job_id: Any, resolved_pages: int, total_pages: int) -> None:
        progress = int(resolved_pages * 100 / total_pages) if total_pages else 0
        if resolved_pages % self.PROGRESS_UPDATE_EVERY == 0 or resolved_pages == total_pages:
            PdfSplitJob.objects.filter(id=job_id).update(
                total_pages=total_pages,
                processed_pages=resolved_pages,
                current_page=resolved_pages,
                progress=progress,
            )

    def _should_check_cancel(self, marker: int) -> bool:
        return marker % self.CANCEL_CHECK_EVERY == 0
