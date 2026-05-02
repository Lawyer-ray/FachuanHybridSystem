"""OCR 子系统：并行识别 / 缓存 / 配置解析。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import fitz
from django.conf import settings

from apps.automation.services.ocr.ocr_service import OCRService
from apps.pdf_splitting.models import PdfSplitOcrProfile

from .split_models import OCRRuntimeProfile, OCRPageResult

logger = logging.getLogger("apps.pdf_splitting")


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


class OCRHandler:
    """OCR 子系统的入口，封装并行识别、缓存、配置解析。"""

    def resolve_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
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
                use_v5=True,
                dpi=200,
                workers=min(3, cpu),
            ),
            PdfSplitOcrProfile.ACCURATE: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.ACCURATE,
                use_v5=True,
                dpi=220,
                workers=min(2, cpu),
            ),
        }
        return profiles.get(normalized, profiles[PdfSplitOcrProfile.BALANCED])

    def parallel_ocr(
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

    def sha256_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> OCRPageResult | None:
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

    def write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: OCRPageResult) -> None:
        cache_file = self._ocr_cache_file(pdf_hash=pdf_hash, profile_key=profile_key, page_no=result.page_no)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": result.text,
            "ocr_failed": result.ocr_failed,
            "source_method": result.source_method,
        }
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _ocr_cache_file(*, pdf_hash: str, profile_key: str, page_no: int) -> Path:
        return (
            Path(settings.MEDIA_ROOT)
            / "pdf_splitting"
            / "ocr_cache"
            / pdf_hash
            / profile_key
            / f"page_{page_no:04d}.json"
        )

    @staticmethod
    def _chunk_pages(*, page_numbers: list[int], chunk_count: int) -> list[list[int]]:
        if not page_numbers:
            return []
        chunk_count = max(1, min(chunk_count, len(page_numbers)))
        buckets: list[list[int]] = [[] for _ in range(chunk_count)]
        for index, page_no in enumerate(page_numbers):
            buckets[index % chunk_count].append(page_no)
        return [bucket for bucket in buckets if bucket]
