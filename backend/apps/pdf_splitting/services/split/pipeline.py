"""内容分析流水线：PDF → 逐页取字 → 分段 → 每段 Markdown。

与 PdfSplitJob / DB 完全解耦（进度与取消经回调透出）：给一个 PDF 路径就能拿到
pages / segments / segments_md / summary，不建任务、不落库。pdf_splitting 的任务
执行（PdfSplitService.analyze_job）只是它的一个带持久化的适配层；其他域要复用
「MinerU/TextIn 取字 + 律所 AI 分段 + Markdown 重建」这整段能力时直接调
``analyze_pdf()``，或按需组合下面的独立组件。

内部协作关系（谁负责什么、失败怎么走）：

    PDF 路径
      │
      ▼
    PageTextExtractor（取字编排）
      │  每页按优先级：PDF 文本层（快、无版面）→ OCR 页级缓存（SHA-256）
      │  → 云端整本解析（MinerU/TextIn，带版面块与表格）→ 本地并行 OCR 兜底
      ▼
    PageDescriptor[]（text / normalized / layout / layout_title / 规则候选分）
      │
      ├─▶ detect_segments_with_fallback（分段 + 命名）
      │      律所 LLM 语义分段（llm_segment_detector）优先；
      │      失败（无供给/超时/输出非法）降级关键词规则引擎（segment_detector）。
      │      两条路径输出同构 SegmentDraft（完整覆盖、无重叠）。
      ▼
    markdown_builder（每段按页区间重建 Markdown：版面块→标题/段落/GFM 表格，
      无版面退回原文）

组件均为无状态模块，可单独复用；本模块只做编排。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pymupdf as fitz

from apps.pdf_splitting.services.template_registry import get_template_definition

from .llm_segment_detector import LLMSegmentDetector
from .markdown_builder import build_segments_markdown
from .ocr_handler import OCRHandler
from .segment_detector import SegmentDetector
from .split_models import OCRPageResult, PageDescriptor, SegmentDraft, extract_layout_title

logger = logging.getLogger("apps.pdf_splitting")

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]

# 取消 / 进度节流：每解析 5 页查一次取消（与旧 analyze_job 的节奏一致）
_CANCEL_CHECK_EVERY = 5


class PipelineCancelled(RuntimeError):
    """调用方经 is_cancelled 回调请求取消。"""


@dataclass
class PdfAnalysisOutcome:
    """一次内容分析的完整产物。summary 携带取字与分段的可观测字段，可直接并入任务摘要。"""

    pages: list[PageDescriptor]
    drafts: list[SegmentDraft]
    segments_md: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)


def analyze_pdf(
    pdf_path: Path,
    *,
    template_key: str = "filing_materials_v1",
    ocr_profile: str = "balanced",
    on_progress: ProgressCallback | None = None,
    is_cancelled: CancelCallback | None = None,
    ocr_handler: Any = None,
    llm_segment_detector: Any = None,
) -> PdfAnalysisOutcome:
    """整条流水线的无状态门面：取字 → 分段 → Markdown。

    Args:
        pdf_path: PDF 文件路径。
        template_key: 分段模板（建议标签集；默认立案材料 15 类）。
        ocr_profile: OCR 档位 fast / balanced / accurate。
        on_progress: 进度回调 (已解析页数, 总页数)，每解析一页触发一次（节流由调用方决定）。
        is_cancelled: 取消查询回调；返回 True 时抛 PipelineCancelled。
        ocr_handler / llm_segment_detector: 依赖注入口（测试桩）；缺省用真实实现。
    """
    extractor = PageTextExtractor(
        ocr_handler=ocr_handler,
        on_progress=on_progress,
        is_cancelled=is_cancelled,
    )
    pages, extraction_summary = extractor.extract(pdf_path, ocr_profile=ocr_profile, template_key=template_key)
    drafts, segment_summary = detect_segments_with_fallback(
        pages,
        template_key=template_key,
        llm_segment_detector=llm_segment_detector,
    )
    return PdfAnalysisOutcome(
        pages=pages,
        drafts=drafts,
        segments_md=build_segments_markdown(drafts, pages),
        summary={**extraction_summary, **segment_summary},
    )


def detect_segments_with_fallback(
    pages: list[PageDescriptor],
    *,
    template_key: str,
    llm_segment_detector: Any = None,
) -> tuple[list[SegmentDraft], dict[str, Any]]:
    """分段检测：律所 LLM（语义分类）优先，任何失败降级关键词规则引擎。

    返回 (drafts, summary 附加字段)。两条路径输出的 SegmentDraft 结构同构，
    后续校验（完整覆盖、无重叠）对两条路径一视同仁。
    """
    detector = llm_segment_detector if llm_segment_detector is not None else LLMSegmentDetector()
    try:
        drafts = detector.detect(pages, template_key=template_key)
        return drafts, {"segment_backend": "llm", "segment_llm_fallback_reason": ""}
    except Exception as exc:
        reason = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("pdf_split_llm_segment_fallback", extra={"action": "llm_segment_fallback", "reason": reason})
        drafts = SegmentDetector().detect_segments(pages, template_key=template_key)
        return drafts, {"segment_backend": "rule", "segment_llm_fallback_reason": reason}


def build_page_descriptor(
    *,
    page_no: int,
    text: str,
    source_method: str,
    ocr_failed: bool,
    template_key: str,
    layout: dict[str, Any] | None = None,
    segment_detector: SegmentDetector | None = None,
) -> PageDescriptor:
    """把一页取字结果加工成 PageDescriptor（归一化文本、版面标题、规则候选分）。

    top_candidates 只被规则引擎消费；LLM 分段走 normalized_text / layout_title，
    但统一产出，保持 pages.json 数据形状稳定。
    """
    detector = segment_detector if segment_detector is not None else SegmentDetector()
    normalized_text = detector.normalize_text(text)
    return PageDescriptor(
        page_no=page_no,
        text=text,
        normalized_text=normalized_text,
        head_text=detector.normalize_text(text[:240]),
        source_method=source_method,
        ocr_failed=ocr_failed,
        top_candidates=detector.score_page(
            head_text=detector.normalize_text(text[:240]), normalized_text=normalized_text, template_key=template_key
        ),
        layout=layout,
        layout_title=extract_layout_title(layout),
    )


class PageTextExtractor:
    """逐页取字编排：文本层 → OCR 缓存 → 云端解析 → 本地 OCR 兜底。

    云端（MinerU/TextIn）一次解析整本并按页恢复结果，带版面块（供 Markdown
    重建结构）；云端失败或漏页由本地并行 OCR 兜底。所有取字结果按
    (PDF SHA-256 × 档位 × 页码) 落缓存，重复分析零成本。
    """

    def __init__(
        self,
        *,
        ocr_handler: Any = None,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> None:
        self._ocr_handler = ocr_handler if ocr_handler is not None else OCRHandler()
        self._rule_detector = SegmentDetector()
        self._on_progress = on_progress
        self._is_cancelled = is_cancelled

    def extract(
        self, pdf_path: Path, *, ocr_profile: str, template_key: str
    ) -> tuple[list[PageDescriptor], dict[str, Any]]:
        runtime_profile = self._ocr_handler.resolve_runtime_profile(ocr_profile)
        cloud_backend = self._ocr_handler.resolve_cloud_backend()
        cloud_cache_profile = f"{runtime_profile.key}_{cloud_backend}_v1" if cloud_backend else runtime_profile.key
        pdf_hash = self._ocr_handler.sha256_file(pdf_path)

        stats = {
            "runtime_profile": runtime_profile,
            "cloud_backend": cloud_backend,
            "cloud_cache_profile": cloud_cache_profile,
            "cache_hit_count": 0,
            "cloud_cache_hit_count": 0,
            "pending_ocr_count": 0,
            "cloud_error": "",
        }
        with fitz.open(pdf_path) as doc:
            total_pages = int(doc.page_count)
            descriptors = self._extract_from_text_layer_or_cache(
                doc,
                pdf_hash=pdf_hash,
                cloud_cache_profile=cloud_cache_profile,
                runtime_profile_key=runtime_profile.key,
                template_key=template_key,
                stats=stats,
            )
            self._resolve_pending_pages(
                pdf_path, descriptors=descriptors, pdf_hash=pdf_hash, template_key=template_key, stats=stats
            )

        final_pages = [item for item in descriptors if item is not None]
        return final_pages, self._build_summary(stats)

    # ------------------------------------------------------------------
    # 取字步骤
    # ------------------------------------------------------------------

    def _extract_from_text_layer_or_cache(
        self,
        doc: fitz.Document,
        *,
        pdf_hash: str,
        cloud_cache_profile: str,
        runtime_profile_key: str,
        template_key: str,
        stats: dict[str, Any],
    ) -> list[PageDescriptor | None]:
        """第一遍扫描：PDF 自带文本层直接用；否则查 OCR 页缓存。剩余页号留给云端/本地兜底。"""
        total_pages = int(doc.page_count)
        descriptors: list[PageDescriptor | None] = [None] * total_pages
        resolved_pages = 0
        cloud_backend = stats["cloud_backend"]
        for page_index in range(total_pages):
            self._raise_if_cancelled(page_index)
            page_no = page_index + 1
            page = doc.load_page(page_index)
            direct_text = page.get_text("text") or ""
            if self._rule_detector.is_effective_text(direct_text):
                descriptors[page_index] = build_page_descriptor(
                    page_no=page_no,
                    text=direct_text,
                    source_method="text",
                    ocr_failed=False,
                    template_key=template_key,
                    segment_detector=self._rule_detector,
                )
                resolved_pages += 1
                self._report_progress(resolved_pages, total_pages)
                continue

            cached = self._ocr_handler.read_ocr_cache(
                pdf_hash=pdf_hash, profile_key=cloud_cache_profile, page_no=page_no
            )
            cached_from_cloud = cached is not None and cloud_backend is not None
            if cached is None and cloud_backend is None:
                cached = self._ocr_handler.read_ocr_cache(
                    pdf_hash=pdf_hash, profile_key=runtime_profile_key, page_no=page_no
                )
            if cached is not None:
                descriptors[page_index] = build_page_descriptor(
                    page_no=page_no,
                    text=cached.text,
                    source_method="ocr_cache" if cached.text else "ocr_failed_cache",
                    ocr_failed=cached.ocr_failed,
                    template_key=template_key,
                    layout=cached.layout,
                    segment_detector=self._rule_detector,
                )
                resolved_pages += 1
                stats["cache_hit_count"] += 1
                stats["cloud_cache_hit_count"] += int(cached_from_cloud)
                self._report_progress(resolved_pages, total_pages)

        stats["pending_page_numbers"] = [no for no in range(1, total_pages + 1) if descriptors[no - 1] is None]
        return descriptors

    def _resolve_pending_pages(
        self,
        pdf_path: Path,
        *,
        descriptors: list[PageDescriptor | None],
        pdf_hash: str,
        template_key: str,
        stats: dict[str, Any],
    ) -> None:
        """第二遍：对文本层/缓存都没覆盖的页，云端整本解析优先、本地并行 OCR 兜底。"""
        pending: list[int] = stats["pending_page_numbers"]
        if not pending:
            return
        stats["pending_ocr_count"] = len(pending)
        total_pages = len(descriptors)
        cloud_results = self._parse_cloud(pdf_path, stats)

        for page_no in [no for no in pending if cloud_results.get(no)]:
            self._raise_if_cancelled(page_no)
            result = cloud_results[page_no]
            if not result.text:
                continue
            self._ocr_handler.write_ocr_cache(
                pdf_hash=pdf_hash, profile_key=stats["cloud_cache_profile"], result=result
            )
            descriptors[page_no - 1] = build_page_descriptor(
                page_no=page_no,
                text=result.text,
                source_method=result.source_method,
                ocr_failed=False,
                template_key=template_key,
                layout=result.layout,
                segment_detector=self._rule_detector,
            )
            self._report_progress(self._resolved_count(descriptors), total_pages)

        local_fallback_pages = [no for no in pending if descriptors[no - 1] is None]
        if not local_fallback_pages:
            return
        ocr_results = self._ocr_handler.parallel_ocr(
            pdf_path=pdf_path, page_numbers=local_fallback_pages, runtime_profile=stats["runtime_profile"]
        )
        for page_no in local_fallback_pages:
            self._raise_if_cancelled(page_no)
            result = ocr_results.get(page_no) or OCRPageResult(
                page_no=page_no, text="", source_method="ocr_failed", ocr_failed=True
            )
            self._ocr_handler.write_ocr_cache(
                pdf_hash=pdf_hash, profile_key=stats["runtime_profile"].key, result=result
            )
            descriptors[page_no - 1] = build_page_descriptor(
                page_no=page_no,
                text=result.text,
                source_method=result.source_method,
                ocr_failed=result.ocr_failed,
                template_key=template_key,
                layout=result.layout,
                segment_detector=self._rule_detector,
            )
            self._report_progress(self._resolved_count(descriptors), total_pages)

    def _parse_cloud(self, pdf_path: Path, stats: dict[str, Any]) -> dict[int, Any]:
        backend = stats["cloud_backend"]
        if not backend:
            return {}
        try:
            return self._ocr_handler.parse_cloud_pages(pdf_path=pdf_path, backend=backend)
        except Exception as exc:
            logger.exception("pdf_split_cloud_ocr_failed", extra={"provider": backend})
            stats["cloud_error"] = (
                f"{type(exc).__name__}: {str(exc).replace(pdf_path.as_posix(), '[source PDF]')[:400]}"
            )
            return {}

    # ------------------------------------------------------------------
    # 回调与摘要
    # ------------------------------------------------------------------

    def _raise_if_cancelled(self, marker: int) -> None:
        if marker % _CANCEL_CHECK_EVERY != 0 or self._is_cancelled is None:
            return
        if self._is_cancelled():
            raise PipelineCancelled()

    def _report_progress(self, resolved_pages: int, total_pages: int) -> None:
        if self._on_progress is not None:
            self._on_progress(resolved_pages, total_pages)

    def _resolved_count(self, descriptors: list[PageDescriptor | None]) -> int:
        return len([item for item in descriptors if item is not None])

    def _build_summary(self, stats: dict[str, Any]) -> dict[str, Any]:
        runtime_profile = stats["runtime_profile"]
        cloud_backend = stats["cloud_backend"]
        pending = stats["pending_ocr_count"]
        return {
            "ocr_profile": runtime_profile.key,
            "ocr_dpi": runtime_profile.dpi,
            "ocr_model": "v5_server" if runtime_profile.use_v5 else "v4_default",
            "ocr_workers": runtime_profile.workers,
            "ocr_cache_hit_count": int(max(stats["cache_hit_count"], 0)),
            "ocr_miss_count": int(max(pending, 0)),
            "ocr_provider": cloud_backend or "local",
            "ocr_cloud_cache_profile": stats["cloud_cache_profile"] if cloud_backend else "",
            "ocr_cloud_cache_hit_count": int(max(stats["cloud_cache_hit_count"], 0)),
            "ocr_fallback_reason": stats["cloud_error"] if pending and cloud_backend else "",
        }
