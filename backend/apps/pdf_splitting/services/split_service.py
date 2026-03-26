from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import fitz
from django.conf import settings
from django.utils import timezone

from apps.automation.services.ocr.ocr_service import OCRService
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

from .storage import PdfSplitStorage
from .template_registry import SegmentTemplateRule, get_default_filename, get_segment_label, get_template_definition

logger = logging.getLogger("apps.pdf_splitting")

_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_NON_WORD_RE = re.compile(r"\s+")
_TEXT_MIN_LENGTH = 12


@dataclass
class PageDescriptor:
    page_no: int
    text: str
    normalized_text: str
    head_text: str
    source_method: str
    ocr_failed: bool
    top_candidates: list[dict[str, Any]]


@dataclass
class SegmentDraft:
    order: int
    page_start: int
    page_end: int
    segment_type: str
    filename: str
    confidence: float
    source_method: str
    review_flag: str


@dataclass(frozen=True)
class OCRRuntimeProfile:
    key: str
    use_v5: bool
    dpi: int
    workers: int


@dataclass(frozen=True)
class OCRPageResult:
    page_no: int
    text: str
    source_method: str
    ocr_failed: bool


def _ocr_pages_worker(
    *,
    pdf_path: str,
    page_numbers: list[int],
    use_v5: bool,
    dpi: int,
) -> list[OCRPageResult]:
    results: list[OCRPageResult] = []
    ocr_service = OCRService(use_v5=use_v5)
    try:
        with fitz.open(pdf_path) as doc:
            matrix = fitz.Matrix(dpi / 72, dpi / 72)
            for page_no in page_numbers:
                try:
                    page = doc.load_page(page_no - 1)
                    pix = page.get_pixmap(matrix=matrix)
                    image_bytes = pix.tobytes("png")
                    text = ocr_service.recognize_bytes(image_bytes)
                    ocr_failed = not bool(text)
                except Exception:
                    logger.exception("pdf_split_page_ocr_worker_failed", extra={"page_no": page_no})
                    text = ""
                    ocr_failed = True
                results.append(
                    OCRPageResult(
                        page_no=page_no,
                        text=text,
                        source_method="ocr" if text else "ocr_failed",
                        ocr_failed=ocr_failed,
                    )
                )
    except Exception:
        logger.exception("pdf_split_ocr_worker_failed", extra={"pdf_path": pdf_path})
        for page_no in page_numbers:
            results.append(
                OCRPageResult(
                    page_no=page_no,
                    text="",
                    source_method="ocr_failed",
                    ocr_failed=True,
                )
            )
    return results


class PdfSplitService:
    MAX_PAGES = 300
    PREVIEW_DPI = 200
    COMPLAINT_MAX_SPAN = 20
    PROGRESS_UPDATE_EVERY = 5
    CANCEL_CHECK_EVERY = 5
    COMPLAINT_TERMINAL_KEYWORDS = ("此致", "具状人", "起诉人", "起诉状具状人", "日期")
    COMPLAINT_ATTACHMENT_KEYWORDS = (
        "证据",
        "借条",
        "转账",
        "聊天记录",
        "微信",
        "支付宝",
        "发票",
        "授权委托书",
        "居民身份证",
        "送达地址确认书",
    )

    def __init__(self, *, ocr_service: OCRService | None = None) -> None:
        self._ocr_service = ocr_service

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

        runtime_profile = self._resolve_ocr_runtime_profile(job.ocr_profile)
        pdf_hash = self._sha256_file(storage.source_pdf_path)
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
                if self._is_effective_text(direct_text):
                    descriptors[page_index] = self._build_descriptor_from_text(
                        page_no=page_no,
                        text=direct_text,
                        source_method="text",
                        ocr_failed=False,
                        template_key=template.key,
                    )
                    resolved_pages += 1
                    self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)
                    continue

                cached = self._read_ocr_cache(pdf_hash=pdf_hash, profile_key=runtime_profile.key, page_no=page_no)
                if cached is not None:
                    descriptors[page_index] = self._build_descriptor_from_text(
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
                ocr_results = self._parallel_ocr_missing_pages(
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
                        result = OCRPageResult(
                            page_no=page_no,
                            text="",
                            source_method="ocr_failed",
                            ocr_failed=True,
                        )
                    self._write_ocr_cache(
                        pdf_hash=pdf_hash,
                        profile_key=runtime_profile.key,
                        result=result,
                    )
                    descriptors[page_no - 1] = self._build_descriptor_from_text(
                        page_no=page_no,
                        text=result.text,
                        source_method=result.source_method,
                        ocr_failed=result.ocr_failed,
                        template_key=template.key,
                    )
                    resolved_pages += 1
                    self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)

            final_descriptors = [item for item in descriptors if item is not None]
            drafts = self._detect_segments(final_descriptors, template_key=template.key)
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

                display_name = sanitize_upload_filename(segment.filename or get_default_filename(segment.segment_type))
                if not display_name.lower().endswith(".pdf"):
                    display_name = f"{display_name}.pdf"
                display_name = self._deduplicate_filename(display_name, seen_names)

                output_path = storage.export_pdf_path(display_name)
                self._export_segment_pdf(source_doc, segment.page_start, segment.page_end, output_path)
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
            pix = page.get_pixmap(matrix=fitz.Matrix(self.PREVIEW_DPI / 72, self.PREVIEW_DPI / 72))
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(preview_path.as_posix())
        return preview_path

    def _persist_analysis(
        self,
        *,
        job: PdfSplitJob,
        descriptors: list[PageDescriptor],
        drafts: list[SegmentDraft],
        storage: PdfSplitStorage,
        runtime_profile: OCRRuntimeProfile,
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
                "recognized_count": len([item for item in drafts if item.segment_type != PdfSplitSegmentType.UNRECOGNIZED]),
                "unrecognized_count": len([item for item in drafts if item.segment_type == PdfSplitSegmentType.UNRECOGNIZED]),
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

    def _build_page_descriptor(self, *, doc: fitz.Document, page_index: int, template_key: str) -> PageDescriptor:
        runtime_profile = self._resolve_ocr_runtime_profile(PdfSplitOcrProfile.BALANCED)
        page = doc.load_page(page_index)
        raw_text = page.get_text("text") or ""
        source_method = "text"
        ocr_failed = False
        if not self._is_effective_text(raw_text):
            image_bytes = self._render_page_bytes(page, dpi=runtime_profile.dpi)
            try:
                ocr_service = self._ocr_service or OCRService(use_v5=runtime_profile.use_v5)
                raw_text = ocr_service.recognize_bytes(image_bytes)
                source_method = "ocr" if raw_text else "ocr_failed"
                ocr_failed = not bool(raw_text)
            except Exception:
                logger.exception("pdf_split_page_ocr_failed", extra={"page_no": page_index + 1})
                raw_text = ""
                source_method = "ocr_failed"
                ocr_failed = True

        return self._build_descriptor_from_text(
            page_no=page_index + 1,
            text=raw_text,
            source_method=source_method,
            ocr_failed=ocr_failed,
            template_key=template_key,
        )

    def _score_page(self, *, head_text: str, normalized_text: str, template_key: str) -> list[dict[str, Any]]:
        template = get_template_definition(template_key)
        candidates: list[dict[str, Any]] = []
        for rule in template.rules:
            score = 0.0
            matched_strong = [kw for kw in rule.strong_keywords if self._contains_keyword(head_text, kw)]
            matched_weak = [kw for kw in rule.weak_keywords if self._contains_keyword(normalized_text, kw)]
            matched_negative = [kw for kw in rule.negative_keywords if self._contains_keyword(normalized_text, kw)]
            if matched_strong:
                score += min(0.75, 0.4 + 0.18 * len(matched_strong))
            if matched_weak:
                score += min(0.2, 0.08 * len(matched_weak))
            if matched_negative:
                score -= min(0.4, 0.12 * len(matched_negative))
            if matched_strong and score >= 0.42:
                candidates.append(
                    {
                        "segment_type": rule.segment_type,
                        "label": rule.label,
                        "score": round(max(score, 0.0), 3),
                        "matched_strong": matched_strong,
                        "matched_weak": matched_weak,
                    }
                )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:3]

    def _detect_segments(self, pages: list[PageDescriptor], *, template_key: str) -> list[SegmentDraft]:
        template = get_template_definition(template_key)
        start_candidates: list[dict[str, Any]] = []
        for page in pages:
            if not page.top_candidates:
                continue
            top = page.top_candidates[0]
            start_candidates.append(
                {
                    "page_no": page.page_no,
                    "segment_type": top["segment_type"],
                    "score": float(top["score"]),
                }
            )

        segments: list[SegmentDraft] = []
        for index, start in enumerate(start_candidates):
            next_start_page = start_candidates[index + 1]["page_no"] if index + 1 < len(start_candidates) else len(pages) + 1
            end_page = next_start_page - 1
            if start["segment_type"] == PdfSplitSegmentType.COMPLAINT:
                end_page = self._find_complaint_end(pages, start["page_no"], next_start_page - 1, template.rules[0])
                if (
                    segments
                    and segments[-1].segment_type == PdfSplitSegmentType.COMPLAINT
                    and start["page_no"] == segments[-1].page_end + 1
                ):
                    continue
            review_flag = PdfSplitReviewFlag.NORMAL
            source_method = "rule"
            confidence = start["score"]
            if index > 0 and start_candidates[index - 1]["page_no"] == start["page_no"] - 1:
                if start_candidates[index - 1]["segment_type"] == start["segment_type"]:
                    review_flag = PdfSplitReviewFlag.LOW_CONFIDENCE
                    source_method = "rule_adjacent_start"
                    confidence = min(confidence, 0.55)
            segments.append(
                SegmentDraft(
                    order=len(segments) + 1,
                    page_start=start["page_no"],
                    page_end=max(start["page_no"], end_page),
                    segment_type=start["segment_type"],
                    filename=f"{get_default_filename(start['segment_type'])}.pdf",
                    confidence=round(confidence, 3),
                    source_method=source_method,
                    review_flag=review_flag,
                )
            )

        merged_segments = self._merge_adjacent_pack_segments(segments)
        return self._fill_unrecognized_gaps(segments=merged_segments, total_pages=len(pages))

    def _find_complaint_end(
        self,
        pages: list[PageDescriptor],
        start_page: int,
        max_end_page: int,
        rule: SegmentTemplateRule,
    ) -> int:
        upper_bound = min(max_end_page, start_page + self.COMPLAINT_MAX_SPAN - 1)
        end_page = start_page
        terminal_seen = False
        for page_no in range(start_page, upper_bound + 1):
            page = pages[page_no - 1]
            if page_no == start_page:
                end_page = page_no
                continue

            has_continuation = any(self._contains_keyword(page.normalized_text, kw) for kw in rule.continuation_keywords)
            has_attachment_signal = any(self._contains_keyword(page.normalized_text, kw) for kw in self.COMPLAINT_ATTACHMENT_KEYWORDS)
            if not has_continuation and has_attachment_signal:
                break

            end_page = page_no
            if any(self._contains_keyword(page.normalized_text, kw) for kw in self.COMPLAINT_TERMINAL_KEYWORDS):
                terminal_seen = True
                next_page = pages[page_no] if page_no < len(pages) else None
                if next_page and not any(
                    self._contains_keyword(next_page.normalized_text, kw) for kw in rule.continuation_keywords
                ):
                    break

        if terminal_seen:
            return end_page
        return min(end_page, upper_bound)

    def _fill_unrecognized_gaps(self, *, segments: list[SegmentDraft], total_pages: int) -> list[SegmentDraft]:
        filled: list[SegmentDraft] = []
        cursor = 1
        ordered_segments = sorted(segments, key=lambda item: (item.page_start, item.page_end))
        for item in ordered_segments:
            if item.page_start > cursor:
                filled.append(
                    SegmentDraft(
                        order=len(filled) + 1,
                        page_start=cursor,
                        page_end=item.page_start - 1,
                        segment_type=PdfSplitSegmentType.UNRECOGNIZED,
                        filename=f"未识别材料_{cursor}-{item.page_start - 1}.pdf",
                        confidence=0.0,
                        source_method="gap_fill",
                        review_flag=PdfSplitReviewFlag.UNRECOGNIZED,
                    )
                )
            item.order = len(filled) + 1
            filled.append(item)
            cursor = item.page_end + 1

        if cursor <= total_pages:
            filled.append(
                SegmentDraft(
                    order=len(filled) + 1,
                    page_start=cursor,
                    page_end=total_pages,
                    segment_type=PdfSplitSegmentType.UNRECOGNIZED,
                    filename=f"未识别材料_{cursor}-{total_pages}.pdf",
                    confidence=0.0,
                    source_method="gap_fill",
                    review_flag=PdfSplitReviewFlag.UNRECOGNIZED,
                )
            )
        return filled

    def _merge_adjacent_pack_segments(self, segments: list[SegmentDraft]) -> list[SegmentDraft]:
        if not segments:
            return []

        merged: list[SegmentDraft] = []
        mergeable_types = {PdfSplitSegmentType.PARTY_IDENTITY}
        for item in sorted(segments, key=lambda value: (value.page_start, value.page_end)):
            if (
                merged
                and item.segment_type in mergeable_types
                and merged[-1].segment_type == item.segment_type
                and item.page_start == merged[-1].page_end + 1
            ):
                previous = merged[-1]
                merged[-1] = SegmentDraft(
                    order=previous.order,
                    page_start=previous.page_start,
                    page_end=item.page_end,
                    segment_type=previous.segment_type,
                    filename=previous.filename,
                    confidence=max(previous.confidence, item.confidence),
                    source_method="rule_merged_adjacent",
                    review_flag=(
                        PdfSplitReviewFlag.LOW_CONFIDENCE
                        if PdfSplitReviewFlag.LOW_CONFIDENCE in {previous.review_flag, item.review_flag}
                        else previous.review_flag
                    ),
                )
                continue

            item.order = len(merged) + 1
            merged.append(item)
        return merged

    def _render_page_bytes(self, page: fitz.Page, *, dpi: int) -> bytes:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        return pix.tobytes("png")

    def _export_segment_pdf(self, source_doc: fitz.Document, page_start: int, page_end: int, output_path: Path) -> None:
        segment_doc = fitz.open()
        try:
            segment_doc.insert_pdf(source_doc, from_page=page_start - 1, to_page=page_end - 1)
            segment_doc.save(output_path.as_posix())
        finally:
            segment_doc.close()

    def _deduplicate_filename(self, display_name: str, seen_names: set[str]) -> str:
        path = Path(display_name)
        stem = path.stem or "片段"
        suffix = path.suffix or ".pdf"
        candidate = f"{stem}{suffix}"
        counter = 2
        while candidate in seen_names:
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        seen_names.add(candidate)
        return candidate

    def _normalize_text(self, value: str) -> str:
        return _NON_WORD_RE.sub("", value or "")

    def _contains_keyword(self, haystack: str, keyword: str) -> bool:
        return self._normalize_text(keyword) in haystack

    def _is_effective_text(self, value: str) -> bool:
        normalized = self._normalize_text(value)
        return len(normalized) >= _TEXT_MIN_LENGTH

    def _build_descriptor_from_text(
        self,
        *,
        page_no: int,
        text: str,
        source_method: str,
        ocr_failed: bool,
        template_key: str,
    ) -> PageDescriptor:
        normalized_text = self._normalize_text(text)
        head_text = normalized_text[:240]
        top_candidates = self._score_page(head_text=head_text, normalized_text=normalized_text, template_key=template_key)
        return PageDescriptor(
            page_no=page_no,
            text=text,
            normalized_text=normalized_text,
            head_text=head_text,
            source_method=source_method,
            ocr_failed=ocr_failed,
            top_candidates=top_candidates,
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

    def _resolve_ocr_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
        normalized = str(profile_key or "").strip().lower()
        cpu = max(1, os.cpu_count() or 1)
        profiles: dict[str, OCRRuntimeProfile] = {
            PdfSplitOcrProfile.FAST: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.FAST,
                use_v5=False,
                dpi=140,
                workers=min(6, cpu),
            ),
            PdfSplitOcrProfile.BALANCED: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.BALANCED,
                use_v5=False,
                dpi=168,
                workers=min(4, cpu),
            ),
            PdfSplitOcrProfile.ACCURATE: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.ACCURATE,
                use_v5=True,
                dpi=220,
                workers=min(2, cpu),
            ),
        }
        return profiles.get(normalized, profiles[PdfSplitOcrProfile.BALANCED])

    def _parallel_ocr_missing_pages(
        self,
        *,
        pdf_path: Path,
        page_numbers: list[int],
        runtime_profile: OCRRuntimeProfile,
    ) -> dict[int, OCRPageResult]:
        if not page_numbers:
            return {}

        if runtime_profile.workers <= 1 or len(page_numbers) <= 1:
            result_list = _ocr_pages_worker(
                pdf_path=pdf_path.as_posix(),
                page_numbers=page_numbers,
                use_v5=runtime_profile.use_v5,
                dpi=runtime_profile.dpi,
            )
            return {item.page_no: item for item in result_list}

        results: dict[int, OCRPageResult] = {}
        chunks = self._chunk_pages(page_numbers=page_numbers, chunk_count=runtime_profile.workers)
        with ThreadPoolExecutor(max_workers=runtime_profile.workers) as executor:
            future_map = {
                executor.submit(
                    _ocr_pages_worker,
                    pdf_path=pdf_path.as_posix(),
                    page_numbers=chunk,
                    use_v5=runtime_profile.use_v5,
                    dpi=runtime_profile.dpi,
                ): chunk
                for chunk in chunks
                if chunk
            }
            for future in as_completed(future_map):
                chunk = future_map[future]
                try:
                    for item in future.result():
                        results[item.page_no] = item
                except Exception:
                    logger.exception("pdf_split_parallel_ocr_failed_chunk", extra={"chunk_size": len(chunk)})
                    for item in _ocr_pages_worker(
                        pdf_path=pdf_path.as_posix(),
                        page_numbers=chunk,
                        use_v5=runtime_profile.use_v5,
                        dpi=runtime_profile.dpi,
                    ):
                        results[item.page_no] = item

        if len(results) < len(page_numbers):
            missing_pages = [page_no for page_no in page_numbers if page_no not in results]
            logger.warning(
                "pdf_split_parallel_ocr_missing_results",
                extra={"missing_pages": len(missing_pages), "total_pages": len(page_numbers)},
            )
            for item in _ocr_pages_worker(
                pdf_path=pdf_path.as_posix(),
                page_numbers=missing_pages,
                use_v5=runtime_profile.use_v5,
                dpi=runtime_profile.dpi,
            ):
                results[item.page_no] = item
        return results

    def _chunk_pages(self, *, page_numbers: list[int], chunk_count: int) -> list[list[int]]:
        if not page_numbers:
            return []
        chunk_count = max(1, min(chunk_count, len(page_numbers)))
        buckets: list[list[int]] = [[] for _ in range(chunk_count)]
        for index, page_no in enumerate(page_numbers):
            buckets[index % chunk_count].append(page_no)
        return [bucket for bucket in buckets if bucket]

    def _sha256_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _ocr_cache_file(self, *, pdf_hash: str, profile_key: str, page_no: int) -> Path:
        return (
            Path(settings.MEDIA_ROOT)
            / "pdf_splitting"
            / "ocr_cache"
            / pdf_hash
            / profile_key
            / f"page_{page_no:04d}.json"
        )

    def _read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> OCRPageResult | None:
        cache_file = self._ocr_cache_file(pdf_hash=pdf_hash, profile_key=profile_key, page_no=page_no)
        if not cache_file.exists():
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            text = str(payload.get("text") or "")
            ocr_failed = bool(payload.get("ocr_failed"))
            return OCRPageResult(
                page_no=page_no,
                text=text,
                source_method="ocr_cache" if text else "ocr_failed_cache",
                ocr_failed=ocr_failed,
            )
        except Exception:
            logger.exception("pdf_split_ocr_cache_read_failed", extra={"cache_file": cache_file.as_posix()})
            return None

    def _write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: OCRPageResult) -> None:
        cache_file = self._ocr_cache_file(pdf_hash=pdf_hash, profile_key=profile_key, page_no=result.page_no)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": result.text,
            "ocr_failed": result.ocr_failed,
            "source_method": result.source_method,
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
