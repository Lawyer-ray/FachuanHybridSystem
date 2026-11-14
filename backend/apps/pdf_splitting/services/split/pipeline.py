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

from .consistency_summary import attach_quality_flags_to_markdown, detect_inconsistencies, pick_top_inconsistencies
from .llm_segment_detector import LLMSegmentDetector
from .markdown_builder import build_segments_markdown
from .ocr_handler import OCRHandler
from .page_quality_summary import build_page_quality_summary
from .segment_detector import SegmentDetector
from .split_models import (
    MATERIAL_KIND_SCANNED_PDF,
    OCRPageResult,
    PageDescriptor,
    SegmentDraft,
    classify_pdf_material,
    extract_layout_title,
)

logger = logging.getLogger("apps.pdf_splitting")

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]

# 取消 / 进度节流：每解析 5 页查一次取消（与旧 analyze_job 的节奏一致）
_CANCEL_CHECK_EVERY = 5

#: 版面策略取值。与 models.PdfSplitLayoutMode 同值，但这里不 import models：
#: pipeline 是「无任务耦合」的门面（不建任务、不落库），让它可以被任何域直接调用，
#: 不该因为一个字符串常量把 ORM 依赖引进来。
LAYOUT_MODE_FAST_TEXT = "fast_text"
LAYOUT_MODE_LAYOUT = "layout"


class PipelineCancelled(RuntimeError):
    """调用方经 is_cancelled 回调请求取消。"""


@dataclass
class PdfAnalysisOutcome:
    """一次内容分析的完整产物。summary 携带取字与分段的可观测字段，可直接并入任务摘要。"""

    pages: list[PageDescriptor]
    drafts: list[SegmentDraft]
    segments_md: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)


def extract_pages(
    pdf_path: Path,
    *,
    template_key: str = "filing_materials_v1",
    ocr_profile: str = "balanced",
    layout_mode: str = LAYOUT_MODE_FAST_TEXT,
    cloud_backend: str | None = None,
    on_progress: ProgressCallback | None = None,
    is_cancelled: CancelCallback | None = None,
    ocr_handler: Any = None,
) -> tuple[list[PageDescriptor], dict[str, Any]]:
    """流水线第一阶段：只做取字，不分段。

    单独抽出来的理由：164 页真实卷宗上，取字（云端 OCR + 分批）与分段（LLM）
    各自就能吃掉大半分钟，合在一起必然撞 Django-Q 的 600s worker 超时。
    拆成两个独立任务后各自有完整预算，且取字产物落 pages.json，分段被杀
    也不用重跑 OCR。
    """
    extractor = PageTextExtractor(
        ocr_handler=ocr_handler,
        on_progress=on_progress,
        is_cancelled=is_cancelled,
    )
    pages, summary = extractor.extract(
        pdf_path,
        ocr_profile=ocr_profile,
        template_key=template_key,
        layout_mode=layout_mode,
        cloud_backend=cloud_backend,
    )
    # 页面质量画像随取字一起算完并写进 summary：它只被取字结果决定（字数 / 版面块），
    # 与分段无关。**只写 summary，不拦流程**——判据是启发式，`graphic` / `sparse`
    # 都只是「这页 Markdown 可能看不全内容，请核对原图」的提示，拦下来会让律师
    # 遇到「164 页都读出来了任务却说失败」。误报的代价（律师照常读）远小于误拦
    # （整份卷宗用不成）。
    summary["page_quality"] = build_page_quality_summary(pages)
    return pages, summary


def analyze_pdf(
    pdf_path: Path,
    *,
    template_key: str = "filing_materials_v1",
    ocr_profile: str = "balanced",
    layout_mode: str = LAYOUT_MODE_FAST_TEXT,
    cloud_backend: str | None = None,
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
        cloud_backend: 云端平台偏好。``auto``（默认）按优先级并在失败时切下一个
            （容灾）；``mineru`` / ``textin`` 锁定单一平台、失败即失败（不降级）。
        layout_mode: 版面策略。``fast_text``（默认）电子页只抽文本层、不调云端；
            ``layout`` 让电子页也上云端拿版面块与坐标（"原文坐标索引对照"需要），
            代价是这些页也要计费且更慢。云端不可用时自动回落文本层并在
            summary.layout_unavailable_reason 说明。
        on_progress: 进度回调 (已解析页数, 总页数)，每解析一页触发一次（节流由调用方决定）。
        is_cancelled: 取消查询回调；返回 True 时抛 PipelineCancelled。
        ocr_handler / llm_segment_detector: 依赖注入口（测试桩）；缺省用真实实现。
    """
    pages, extraction_summary = extract_pages(
        pdf_path,
        template_key=template_key,
        ocr_profile=ocr_profile,
        layout_mode=layout_mode,
        cloud_backend=cloud_backend,
        on_progress=on_progress,
        is_cancelled=is_cancelled,
        ocr_handler=ocr_handler,
    )
    drafts, segment_summary = detect_segments_with_fallback(
        pages,
        template_key=template_key,
        llm_segment_detector=llm_segment_detector,
    )
    # 分段完成后再做跨页一致性校对：判据要的是「全本哪些短词被写成两种样子」，
    # 与分段结果无关，放在这里是为了让两条产物（summary 清单 / 段级 flag）出自同一次计算。
    inconsistencies = detect_inconsistencies(pages)
    # 坐标换算依赖后端坐标系（MinerU 千分比 / Textin 绝对坐标），必须在构建
    # 时就告诉 markdown_builder：事后再猜会算出错位的绿框。
    bbox_backend = str(extraction_summary.get("ocr_provider") or "")
    segments_md = attach_quality_flags_to_markdown(
        build_segments_markdown(drafts, pages, bbox_backend=bbox_backend), inconsistencies
    )
    return PdfAnalysisOutcome(
        pages=pages,
        drafts=drafts,
        segments_md=segments_md,
        # summary 只增不改：取字 + 分段原有字段全保留，新字段追加在后面
        summary={
            **extraction_summary,
            **segment_summary,
            **_inconsistency_summary(inconsistencies),
        },
    )


def _inconsistency_summary(inconsistencies: list[Any]) -> dict[str, Any]:
    """跨页一致性的 summary 字段：只放最可疑的一批 + 真实总数。

    ``inconsistency_total`` 与列表长度分开报：前端要能说出「还有 N 条未显示」。
    裁条数是**输出体积**的边界（实测一份真实卷宗 1340 条，全量会把 job 详情
    撑到几 MB），不是对判据结果的业务过滤——过滤会让判据修好后问题仍然不可见。
    """
    return {
        "inconsistencies": pick_top_inconsistencies(inconsistencies),
        "inconsistency_total": len(inconsistencies),
    }


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
        # 分批分段：164 页整本一次会让总时长撞上 Django-Q 的 600s worker 超时
        # 被杀（实测某次 164 页任务跑到 499s 被杀）。分批后单次 LLM 调用缩短到
        # 1-3 分钟，且死一批也能整轮降级而不会出现半成品。
        from .segment_batch import detect_in_batches

        drafts = detect_in_batches(pages=pages, template_key=template_key, detector=detector)
        # 续页合并：LLM 会把跨页的同一份材料从中间切开（实测 164 页卷宗里
        # 一份《个人房产抵押贷款合同》被切成 p116-125 / p126-140 两段）。
        # 判据是条款序号推进 + 后段首页无标题，详见 segment_merge.py。
        from .segment_merge import merge_continuation_segments

        drafts = merge_continuation_segments(drafts, {page.page_no: page.text for page in pages})
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
        self,
        pdf_path: Path,
        *,
        ocr_profile: str,
        template_key: str,
        layout_mode: str = LAYOUT_MODE_FAST_TEXT,
        cloud_backend: str | None = None,
    ) -> tuple[list[PageDescriptor], dict[str, Any]]:
        runtime_profile = self._ocr_handler.resolve_runtime_profile(ocr_profile)
        # 候选顺序：auto → 全部平台（可容灾）；锁定 → 只有那一个（不允许降级）
        cloud_candidates = self._ocr_handler.resolve_cloud_backends(cloud_backend)
        cloud_backend = cloud_candidates[0] if cloud_candidates else None
        want_layout = layout_mode == LAYOUT_MODE_LAYOUT
        # 缓存档案名带上策略：同一份 PDF 在「仅文本层」下缓存的是纯文本、在
        # 「补版面」下缓存的是带版面块的结果，共用一份档案会互相污染——
        # 先开补版面再关掉，第二次拿到的还是带坐标的旧条目，开关形同虚设。
        cache_suffix = "layout" if want_layout else "text"
        cloud_cache_profile = (
            f"{runtime_profile.key}_{cloud_backend}_{cache_suffix}_v2" if cloud_backend else runtime_profile.key
        )
        pdf_hash = self._ocr_handler.sha256_file(pdf_path)

        stats = {
            "runtime_profile": runtime_profile,
            "cloud_backend": cloud_backend,
            "cloud_candidates": cloud_candidates,
            "cloud_cache_profile": cloud_cache_profile,
            "cache_hit_count": 0,
            "cloud_cache_hit_count": 0,
            "pending_ocr_count": 0,
            "cloud_error": "",
            "layout_mode": layout_mode,
            # 补版面但云端不可用：必须让调用方知道「你以为开了、其实没生效」
            "layout_unavailable_reason": "",
        }
        with fitz.open(pdf_path) as doc:
            total_pages = int(doc.page_count)
            # 抽样判定材料类别（只读首/中/尾几页）：写进 summary 让「这份为什么
            # 走了云端 / 为什么没坐标」可回溯，也供前端提示用。判定不改变下面
            # 的逐页决策——逐页才是真相，抽样只是为了给出一个可读标签。
            stats["material_kind"] = classify_pdf_material(doc, is_effective_text=self._rule_detector.is_effective_text)
            descriptors = self._extract_from_text_layer_or_cache(
                doc,
                pdf_hash=pdf_hash,
                cloud_cache_profile=cloud_cache_profile,
                runtime_profile_key=runtime_profile.key,
                template_key=template_key,
                stats=stats,
                want_layout=want_layout,
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
        want_layout: bool = False,
    ) -> list[PageDescriptor | None]:
        """第一遍扫描：PDF 自带文本层直接用；否则查 OCR 页缓存。剩余页号留给云端/本地兜底。

        ``want_layout`` 改写「文本层优先」这条规则：默认（False）下电子页读到文字
        就定稿，因为它又快又准——但代价是**拿不到版面块与坐标**（文本层没有
        bbox/表格结构）。开着补版面时，电子页**故意不定稿**，留给云端去拿版面，
        这样「原文坐标索引对照」才对电子版 PDF 也生效。成本是这些页也要上云。
        """
        total_pages = int(doc.page_count)
        descriptors: list[PageDescriptor | None] = [None] * total_pages
        resolved_pages = 0
        cloud_backend = stats["cloud_backend"]
        for page_index in range(total_pages):
            self._raise_if_cancelled(page_index)
            page_no = page_index + 1
            page = doc.load_page(page_index)
            direct_text = page.get_text("text") or ""
            # 补版面模式下不拿文本层定稿：否则这一页永远走不到云端，也就永远
            # 没有 bbox。注意这里**仍要先读 direct_text**——后面云端失败时
            # 用它兜底，比让这一页变成空白强。
            if self._rule_detector.is_effective_text(direct_text) and not want_layout:
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
        cloud_results = self._parse_cloud(
            pdf_path,
            stats,
            # 关键：每批完成立即逐页写缓存。这是断点续传的唯一落盘点——
            # 进程死在半路，已完成的批次仍在缓存里，重跑时先读缓存跳过。
            on_batch_done=lambda _batch, mapped: self._persist_cloud_batch(
                pdf_hash=pdf_hash, profile_key=stats["cloud_cache_profile"], batch=mapped
            ),
            on_progress=lambda resolved, total: self._report_progress(
                self._resolved_count(descriptors) + resolved, max(total_pages, total)
            ),
        )

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

        # 补版面模式的自救：这些页本来有文本层，是为了拿版面才故意没定稿的。
        # 云端没给出结果时，**先用文本层填回去**再考虑本地 OCR —— 文本层是
        # 机器真值、零成本、零错字；拿它去喂本地 OCR 等于把可靠的字重新猜一遍。
        if stats.get("layout_mode") == LAYOUT_MODE_LAYOUT:
            self._fill_from_text_layer(pdf_path, descriptors=descriptors, pending=pending, template_key=template_key)

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

    def _fill_from_text_layer(
        self,
        pdf_path: Path,
        *,
        descriptors: list[PageDescriptor | None],
        pending: list[int],
        template_key: str,
    ) -> None:
        """用 PDF 自带文本层补齐仍未定稿的页（补版面失败时的兜底）。

        只填「文本层有效」的页；扫描页文本层为空，自然留给后面的本地 OCR。
        产出的块**没有坐标**（文本层没有 bbox），所以 source_method 记成
        ``text``——与默认路径同源同义，summary 里也就能看出这一页没拿到版面。
        """
        targets = [no for no in pending if descriptors[no - 1] is None]
        if not targets:
            return
        with fitz.open(pdf_path) as doc:
            for page_no in targets:
                try:
                    direct_text = doc.load_page(page_no - 1).get_text("text") or ""
                except Exception:  # 单页读不出来不能拖垮整份
                    continue
                if not self._rule_detector.is_effective_text(direct_text):
                    continue
                descriptors[page_no - 1] = build_page_descriptor(
                    page_no=page_no,
                    text=direct_text,
                    source_method="text",
                    ocr_failed=False,
                    template_key=template_key,
                    segment_detector=self._rule_detector,
                )

    def _persist_cloud_batch(self, *, pdf_hash: str, profile_key: str, batch: dict[int, Any]) -> None:
        """一批云端结果立即逐页写缓存（断点续传的落盘点）。

        为什么在回调里写而不是等全部返回：进程可能在第三批死掉，那时前两批的
        成果必须已经落盘。写缓存是按页一个小文件，成本极低。
        """
        for page_no, result in batch.items():
            if not getattr(result, "text", ""):
                continue
            try:
                self._ocr_handler.write_ocr_cache(pdf_hash=pdf_hash, profile_key=profile_key, result=result)
            except Exception:
                # 写缓存失败不能让已解析的页丢掉（内存里的结果仍会进最终产物）
                logger.exception("pdf_split_cloud_cache_write_failed", extra={"page_no": page_no})

    def _parse_cloud(
        self,
        pdf_path: Path,
        stats: dict[str, Any],
        *,
        on_batch_done: Any = None,
        on_progress: Any = None,
    ) -> dict[int, Any]:
        """云端解析，**分批 + 断点续传**，按候选平台逐个尝试（容灾）。

        为什么不整本一次发：164 页的真实卷宗整本解析时长过久，进程中途一死
        （开发环境的 watchfiles 重启、生产环境的 OOM/部署）就把全部成果归零——
        实测同一份材料连续两次死在 135/164 且每次都从零开始。分批后每批
        完成即落盘，断在哪补哪。详见 `cloud_batch.py`。

        容灾语义不变：auto 逐一尝试候选平台，锁定则只试一个。
        """
        from .cloud_batch import parse_in_batches

        candidates: list[str] = stats.get("cloud_candidates") or []
        if not candidates:
            return {}

        page_numbers: list[int] = sorted(stats.get("pending_page_numbers") or [])
        if not page_numbers:
            return {}

        errors: list[str] = []
        for index, backend in enumerate(candidates):
            try:
                result = parse_in_batches(
                    source_path=pdf_path,
                    page_numbers=page_numbers,
                    parse_one=lambda mini_path, _backend=backend: self._ocr_handler.parse_cloud_pages(
                        pdf_path=mini_path, backend=_backend
                    ),
                    on_batch_done=on_batch_done,
                    on_progress=on_progress,
                )
            except Exception as exc:
                logger.exception("pdf_split_cloud_ocr_failed", extra={"provider": backend})
                errors.append(f"{backend}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
            if not result:
                # 解析成功但一页都没出来：同样视为这次尝试失败，继续下一个
                logger.warning("pdf_split_cloud_empty", extra={"provider": backend})
                errors.append(f"{backend}: 返回空结果")
                continue
            # 命中：把实际生效的平台记进 stats，summary / 缓存档案都以它为准
            if index > 0:
                logger.info(
                    "云端容灾生效：%s 失败后改用 %s",
                    " -> ".join(candidates[:index]),
                    backend,
                )
            stats["cloud_backend"] = backend
            stats["cloud_failover_from"] = candidates[:index]
            return result

        # 全部候选都失败
        stats["cloud_error"] = " | ".join(errors).replace(pdf_path.as_posix(), "[source PDF]")[:800] or "云端解析失败"
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
        layout_mode = stats.get("layout_mode", LAYOUT_MODE_FAST_TEXT)
        # 要了版面却没有云端可用：这是最容易被误当成「开关没生效」的情形。
        # 必须显式说出来，否则用户开了开关、看到的结果和没开一样，无从判断。
        layout_unavailable = ""
        if layout_mode == LAYOUT_MODE_LAYOUT and not cloud_backend:
            layout_unavailable = "未配置可用的云端解析平台，补版面已回落为仅文本层（无坐标）"
        elif layout_mode == LAYOUT_MODE_LAYOUT and stats.get("cloud_error"):
            layout_unavailable = f"云端解析失败，补版面已回落为仅文本层：{stats['cloud_error']}"
        return {
            "ocr_profile": runtime_profile.key,
            "ocr_dpi": runtime_profile.dpi,
            "ocr_model": "v5_server" if runtime_profile.use_v5 else "v4_default",
            "ocr_workers": runtime_profile.workers,
            "ocr_cache_hit_count": int(max(stats["cache_hit_count"], 0)),
            "ocr_miss_count": int(max(pending, 0)),
            "ocr_provider": cloud_backend or "local",
            # 实际生效平台与首选不同 = 发生过容灾；把首选链一并记下便于排障
            "cloud_failover_from": stats.get("cloud_failover_from", []),
            "cloud_candidates": stats.get("cloud_candidates", []),
            "ocr_cloud_cache_profile": stats["cloud_cache_profile"] if cloud_backend else "",
            "ocr_cloud_cache_hit_count": int(max(stats["cloud_cache_hit_count"], 0)),
            "ocr_fallback_reason": stats["cloud_error"] if pending and cloud_backend else "",
            # 电子版 / 扫描件 / 混合：同一本里混扫描页时逐页各自选路，
            # 这个标签只说明「整本更像哪类」，不要拿它替代逐页判定。
            "material_kind": stats.get("material_kind", MATERIAL_KIND_SCANNED_PDF),
            # 本次是否真的调了云端：false 且有扫描页 → 说明云端没配/不可用，
            # 走的是本地 OCR（排障时最容易误判成「云端很慢」的就是这个）。
            "cloud_used": bool(pending and cloud_backend),
            # 版面策略的落地情况（"开了但没生效"必须能从 summary 里看出来）
            "layout_mode": layout_mode,
            "layout_unavailable_reason": layout_unavailable,
        }
