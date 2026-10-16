"""Tests for split.pipeline：取字编排 / 取消 / 分段降级 / md 产出的无任务耦合流水线。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split.pipeline import (
    PageTextExtractor,
    PipelineCancelled,
    analyze_pdf,
    detect_segments_with_fallback,
)
from apps.pdf_splitting.services.split.split_models import OCRPageResult, OCRRuntimeProfile

TEMPLATE_KEY = "filing_materials_v1"
PROFILE = OCRRuntimeProfile(key="balanced", use_v5=True, dpi=200, workers=2)


def _make_pdf(path: Path, pages: list[str | None]) -> None:
    """生成测试 PDF：每页一段插入文本；None = 空白页（模拟扫描件，无文本层）。"""
    with fitz.open() as doc:
        for content in pages:
            page = doc.new_page()
            if content:
                page.insert_text((72, 96), content, fontname="china-s")
        doc.save(path.as_posix())


class _StubOCRHandler:
    """取字桩：缓存恒未命中；云端 / 本地 OCR 返回预置结果并记录调用。"""

    def __init__(
        self,
        *,
        cloud: dict[int, OCRPageResult] | None = None,
        cloud_error: Exception | None = None,
        local: dict[int, OCRPageResult] | None = None,
        backend: str | None = "mineru",
    ) -> None:
        self.cloud = cloud or {}
        self.local = local or {}
        self.cloud_error = cloud_error
        self.backend = backend
        self.cloud_calls: list[str] = []
        self.local_calls: list[list[int]] = []
        self.written: list[tuple[str, int]] = []

    def resolve_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
        return PROFILE

    def resolve_cloud_backend(self) -> str | None:
        return self.backend

    def sha256_file(self, pdf_path: Path) -> str:
        return "hash-x"

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> OCRPageResult | None:
        return None

    def write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: OCRPageResult) -> None:
        self.written.append((profile_key, result.page_no))

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
        self.cloud_calls.append(backend)
        if self.cloud_error:
            raise self.cloud_error
        return self.cloud

    def parallel_ocr(
        self, *, pdf_path: Path, page_numbers: list[int], runtime_profile: OCRRuntimeProfile
    ) -> dict[int, OCRPageResult]:
        self.local_calls.append(page_numbers)
        return self.local


class _StubLLM:
    def __init__(self, segments: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.segments = segments
        self.error = error

    def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
        if self.error:
            raise self.error
        from apps.pdf_splitting.services.split.llm_segment_detector import parse_llm_segments

        return parse_llm_segments(json.dumps(self.segments), total_pages=len(pages), template_key=template_key)


class TestPageTextExtractor:
    def test_文本层直取_不走云端与本地(self, tmp_path: Path) -> None:
        pdf = tmp_path / "t.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三被告李四诉讼请求事实与理由"])
        handler = _StubOCRHandler()
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY)

        assert [p.source_method for p in pages] == ["text"]
        assert handler.cloud_calls == []
        assert handler.local_calls == []
        assert summary["ocr_provider"] == "mineru"  # 桩声明了云端后端（未使用）
        assert summary["ocr_miss_count"] == 0

    def test_扫描页走云端_带版面进描述符(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, [None])
        layout = {"blocks": [{"type": "title", "text": "证据清单", "bbox": [0, 10, 100, 30]}]}
        handler = _StubOCRHandler(
            cloud={1: OCRPageResult(page_no=1, text="证据清单证明内容", source_method="mineru_ocr", ocr_failed=False, layout=layout)}
        )
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY)

        assert handler.cloud_calls == ["mineru"]
        assert pages[0].layout_title == "证据清单"
        assert summary["ocr_provider"] == "mineru"
        assert summary["ocr_miss_count"] == 1
        assert ("balanced_mineru_v1", 1) in handler.written  # 云端结果写缓存

    def test_云端失败本地兜底_失败页记ocr_failed(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan2.pdf"
        _make_pdf(pdf, [None, None])
        handler = _StubOCRHandler(
            cloud_error=RuntimeError("mineru down"),
            local={1: OCRPageResult(page_no=1, text="银行流水交易明细", source_method="ocr", ocr_failed=False)},
        )
        pages, summary = PageTextExtractor(ocr_handler=handler).extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY)

        assert handler.local_calls == [[1, 2]]
        assert [p.source_method for p in pages] == ["ocr", "ocr_failed"]
        assert pages[1].ocr_failed is True
        assert "RuntimeError" in summary["ocr_fallback_reason"]

    def test_取消回调抛PipelineCancelled(self, tmp_path: Path) -> None:
        pdf = tmp_path / "cancel.pdf"
        _make_pdf(pdf, [None] * 8)
        extractor = PageTextExtractor(ocr_handler=_StubOCRHandler(), is_cancelled=lambda: True)
        with pytest.raises(PipelineCancelled):
            extractor.extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY)


class TestAnalyzePdf:
    def test_端到端_取字分段md一体产出(self, tmp_path: Path) -> None:
        pdf = tmp_path / "e2e.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三诉讼请求", "此致人民法院具状人张三"])
        handler = _StubOCRHandler(backend=None)
        llm = _StubLLM(
            segments=[
                {"page_start": 1, "page_end": 2, "type": "complaint", "label": "起诉状", "confidence": 0.9},
            ]
        )
        progress: list[tuple[int, int]] = []
        outcome = analyze_pdf(
            pdf,
            template_key=TEMPLATE_KEY,
            on_progress=lambda done, total: progress.append((done, total)),
            ocr_handler=handler,
            llm_segment_detector=llm,
        )

        assert outcome.summary["segment_backend"] == "llm"
        assert [d.filename for d in outcome.drafts] == ["起诉状.pdf"]
        assert outcome.segments_md[0]["markdown"].startswith("# 起诉状\n")
        assert progress and progress[-1] == (2, 2)

    def test_llm失败降级规则引擎_summary记原因(self, tmp_path: Path) -> None:
        pdf = tmp_path / "fallback.pdf"
        _make_pdf(pdf, ["民事起诉状原告张三诉讼请求事实与理由人民法院"])
        outcome = analyze_pdf(
            pdf,
            template_key=TEMPLATE_KEY,
            ocr_handler=_StubOCRHandler(backend=None),
            llm_segment_detector=_StubLLM(error=RuntimeError("gateway down")),
        )
        assert outcome.summary["segment_backend"] == "rule"
        assert "gateway down" in outcome.summary["segment_llm_fallback_reason"]
        assert outcome.drafts  # 规则引擎兜底产出完整覆盖分段

    def test_detect_segments_with_fallback独立可调(self) -> None:
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        pages = [
            PageDescriptor(
                page_no=1, text="民事起诉状", normalized_text="民事起诉状", head_text="民事起诉状",
                source_method="text", ocr_failed=False,
                top_candidates=[{"segment_type": "complaint", "label": "起诉状", "score": 0.8,
                                 "matched_strong": ["起诉状"], "matched_weak": []}],
            )
        ]
        drafts, summary = detect_segments_with_fallback(
            pages, template_key=TEMPLATE_KEY, llm_segment_detector=_StubLLM(error=RuntimeError("x"))
        )
        assert summary["segment_backend"] == "rule"
        assert drafts[0].page_start == 1 and drafts[0].page_end == 1
