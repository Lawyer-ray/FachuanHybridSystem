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
import re
from collections import Counter
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf as fitz
from django.db import DatabaseError

from apps.document_parsing.services.backends._page_artifacts import clean_page_artifacts
from apps.pdf_splitting.services.heartbeat import heartbeat_block
from apps.pdf_splitting.services.template_registry import get_template_definition

from .consistency_summary import attach_quality_flags_to_markdown, detect_inconsistencies, pick_top_inconsistencies
from .llm_segment_detector import LLMSegmentationError, LLMSegmentDetector
from .markdown_builder import build_segments_markdown
from .ocr_handler import OCRHandler, OCRStageBudget, cloud_backend_of_method
from .page_degeneracy import degeneracy_reason
from .page_fingerprint import find_duplicate_pages, page_signature
from .page_quality import mark_rescued_image_blocks, rescue_image_region, strip_stamp_boilerplate_lines
from .page_quality_summary import attach_page_quality_flags, build_page_quality_summary, qualities_by_page
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

#: 心跳回调：只做一件事——给当前 job 写一拍心跳。
#:
#: 为什么传回调而不是 job_id：本模块刻意与 ``PdfSplitJob`` 解耦（分文件头：“不建任务、
#: 不落库”），它不知道也不应该知道主键长什么样；而逐页 OCR 的线程池里又确实需要
#: 「阻塞期间也有一拍心跳」（2026-11-20 事故：这里冻结了 839s）。传一个动作下去，
#: 两边的依赖方向就都对了：上层知道给谁刷，下层只管在正确的时机呼一下。
HeartbeatCallback = Callable[[], None]

# 取消 / 进度节流：每解析 5 页查一次取消（与旧 analyze_job 的节奏一致）
_CANCEL_CHECK_EVERY = 5

#: 一次取字里最多为几页做图片块补救 OCR。
#:
#: 每页一次云端调用（VL 单页实测 ~29s），8 页约 4 分钟——取字阶段有 20 分钟预算，
#: 留得出余量；同时这个上限挡住「整本都是图形页」的极端卷宗把预算吃光。
#: 579 实测命中 6 页（p23/p24/p41/p98/p100/p101），远在上限内。
_RESCUE_MAX_PAGES = 8

#: 走「无块类型」路径的取字来源：PDF 文本层与本地/VL 兜底（含它们的缓存命中）。
#: 云端块路径的页眉页脚由块类型在重建层滤掉，不在这里重复处理。
_UNSTRUCTURED_SOURCES = frozenset({"text", "ocr", "ocr_failed", "ocr_cache", "ocr_failed_cache"})

#: 长纯数字行（≥6 位）。579 兜底页实测有 16/18/22 位的纯数字行——那是卡号与账号，
#: 不是页码。``clean_page_artifacts`` 会无条件删掉**所有**纯数字行，所以含这种行的页
#: 必须跳过它那一道，否则等于把诉讼核心事实（金额/日期/账号）删掉。
_LONG_DIGIT_LINE_RE = re.compile(r"(?m)^\s*\d{6,}\s*$")

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
    #: 表格几何产物（由调用方落盘到 ``analysis/table_geometry.json``）。
    #:
    #: 为什么由 outcome 带出而不是在 pipeline 里自己写：本模块与 DB/job 目录完全解耦
    #: （模块头注释的约定），落盘是 ``PdfSplitService._persist_analysis`` 的事。
    #: 也不能只传给 ``build_segments_markdown`` 而不存：用户确认分段后重建时（confirm）
    #: 拿不到内存里的这份数据，那次重建就会退回整表框。
    table_geometry: dict[str, Any] = field(default_factory=dict)


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
    heartbeat: HeartbeatCallback | None = None,
    budget: OCRStageBudget | None = None,
) -> tuple[list[PageDescriptor], dict[str, Any]]:
    """流水线第一阶段：只做取字，不分段。

    单独抽出来的理由：164 页真实卷宗上，取字（云端 OCR + 分批）与分段（LLM）
    各自就能吃掉大半分钟，合在一起必然撞 Django-Q 的 600s worker 超时。
    拆成两个独立任务后各自有完整预算，且取字产物落 pages.json，分段被杀
    也不用重跑 OCR。

    Args:
        heartbeat: 心跳回调（长阻塞路径也会刷）；None = 不刷（无任务上下文的纯函数调用）。
        budget: 本段墙钟预算；None = 不降级（行为与改动前完全一致）。
    """
    extractor = PageTextExtractor(
        ocr_handler=ocr_handler,
        on_progress=on_progress,
        is_cancelled=is_cancelled,
        heartbeat=heartbeat,
        budget=budget,
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
    page_quality = build_page_quality_summary(pages)
    summary["page_quality"] = page_quality
    # 取字失败的页必须留一条 WARNING，且带页号。
    #
    # 为什么不能只靠 summary 里的计数：`ocr_failed` 页的正文是空的，它既不会出现在
    # Markdown 里，也不会让任务失败——**律师侧唯一的痕迹就是少了一页内容**。
    # 2026-11-25 一份 37 页扫描卷宗的某一页（整案核心事实与金额全在那一页）就是这样
    # 整页丢的，日志里一条都没有。
    failed_pages = page_quality.get("ocr_failed_pages") or []
    if failed_pages:
        logger.warning(
            "pdf_split_pages_without_text",
            extra={
                "page_numbers": failed_pages[:50],
                "failed_count": len(failed_pages),
                "total_pages": len(pages),
                "ocr_provider": summary.get("ocr_provider"),
                "ocr_fallback_reason": summary.get("ocr_fallback_reason"),
            },
        )
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
    heartbeat: HeartbeatCallback | None = None,
    budget: OCRStageBudget | None = None,
    segment_strategy: str | None = None,
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
        heartbeat / budget: 心跳回调与墙钟预算，原样下传给取字阶段（见 `extract_pages`）。
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
        heartbeat=heartbeat,
        budget=budget,
    )
    drafts, segment_summary = detect_segments_with_fallback(
        pages,
        template_key=template_key,
        llm_segment_detector=llm_segment_detector,
        # None = 取 SystemConfig 的 PDF_SPLIT_SEGMENT_STRATEGY（默认 batch）
        strategy=segment_strategy,
    )
    # 分段完成后再做跨页一致性校对：判据要的是「全本哪些短词被写成两种样子」，
    # 与分段结果无关，放在这里是为了让两条产物（summary 清单 / 段级 flag）出自同一次计算。
    inconsistencies = detect_inconsistencies(pages)
    # 坐标换算依赖后端坐标系（MinerU 千分比 / Textin 绝对坐标），必须在构建
    # 时就告诉 markdown_builder：事后再猜会算出错位的绿框。
    bbox_backend = str(extraction_summary.get("ocr_provider") or "")
    artifact, geometry, geometry_summary = _measure_table_geometry(
        pdf_path=pdf_path, pages=pages, bbox_backend=bbox_backend
    )
    segments_md = attach_page_quality_flags(
        attach_quality_flags_to_markdown(
            build_segments_markdown(
                drafts,
                pages,
                bbox_backend=bbox_backend,
                table_geometry=geometry,
                legacy_uniform=_table_geometry_switches().uniform_fallback_enabled(),
            ),
            inconsistencies,
        ),
        qualities_by_page(pages),
    )
    return PdfAnalysisOutcome(
        pages=pages,
        drafts=drafts,
        segments_md=segments_md,
        table_geometry=artifact,
        # summary 只增不改：取字 + 分段原有字段全保留，新字段追加在后面
        summary={
            **extraction_summary,
            **segment_summary,
            **_inconsistency_summary(inconsistencies),
            # 几何的观测块（整表框的 reason 都在这里计数）
            "table_geometry": geometry_summary,
        },
    )


def _table_geometry_pass() -> Any:
    """延迟拿到 ``table_geometry_pass`` 模块（import 面已经很大，模块级再加一条不划算）。"""
    from . import table_geometry_pass

    return table_geometry_pass


def _table_geometry_switches() -> Any:
    """延迟拿到 ``table_geometry_switches`` 模块（同上：模块级 import 不划算）。"""
    from . import table_geometry_switches

    return table_geometry_switches


def _measure_table_geometry(
    *, pdf_path: Path, pages: list[PageDescriptor], bbox_backend: str
) -> tuple[dict[str, Any], dict[int, dict[int, Any]], dict[str, Any]]:
    """单任务入口的几何 pass：开关关就完全不调引擎、不产产物。

    与 ``PdfSplitService._ensure_table_geometry`` 同口径（同一个 ``switches()``、
    同一个 ``summary_block()``）；差别只在“不读盘也不落盘”——单任务路径刚跑完取字，
    手里就有 ``pdf_path`` 与 ``pages``，量一次即可，落盘由调用方用 outcome 完成
    （否则用户确认分段后重建时就拿不到几何，会退回整表框）。
    """
    module = _table_geometry_pass()
    enabled, _legacy_uniform = _table_geometry_switches().switches()
    if not enabled:
        logger.info("pdf_split_table_geometry_disabled", extra={"entry": "analyze_pdf"})
        return {}, {}, module.summary_block({}, enabled=False)
    artifact = module.build_geometry_artifact(
        pages,
        pdf_path=pdf_path,
        engine=module.PaddleTableGeometryEngine(),
        bbox_backend=bbox_backend,
        # 与 _ensure_table_geometry 同口径：L2 开关只在这里读，pass 层收布尔值
        local_lines_enabled=_table_geometry_switches().local_lines_enabled(),
    )
    return artifact, module.geometries_by_page_block(artifact), module.summary_block(artifact, enabled=True)


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


#: 分段策略。``batch`` = 逐批摘要（现状，稳）；``wholebook`` = 整本一次（看得全）；
#: ``wholebook_cross`` = 两条都跑，边界不一致的段标成「待裁定」。
SEGMENT_STRATEGY_BATCH = "batch"
SEGMENT_STRATEGY_WHOLEBOOK = "wholebook"
SEGMENT_STRATEGY_WHOLEBOOK_CROSS = "wholebook_cross"
SEGMENT_STRATEGIES: tuple[str, ...] = (
    SEGMENT_STRATEGY_BATCH,
    SEGMENT_STRATEGY_WHOLEBOOK,
    SEGMENT_STRATEGY_WHOLEBOOK_CROSS,
)


def resolve_segment_strategy(explicit: str | None = None) -> str:
    """分段策略的取值来源：显式参数 > SystemConfig > batch。

    为什么默认仍是 batch：整本一次要一口气看完一本书，大卷宗会撞 LLM 超时；
    分批是踩过「164 页整本一次跑到 499s 被 worker 杀掉」之后才改成默认的。
    想用整本路径就显式开——不存在「悄悄换成另一种切法」。
    """
    want = str(explicit or "").strip().lower()
    if not want:
        try:
            from apps.core.services.system_config_service import SystemConfigService

            want = str(SystemConfigService().get_value("PDF_SPLIT_SEGMENT_STRATEGY", "") or "").strip().lower()
        except (ImportError, RuntimeError, DatabaseError):  # pragma: no cover - 读不到配置就用默认
            logger.warning("读取 PDF_SPLIT_SEGMENT_STRATEGY 失败，按 batch 处理", exc_info=True)
            want = ""
    if want in SEGMENT_STRATEGIES:
        return want
    if want:
        logger.warning("未知的分段策略 %r，按 batch 处理", want)
    return SEGMENT_STRATEGY_BATCH


def detect_segments_with_fallback(
    pages: list[PageDescriptor],
    *,
    template_key: str,
    llm_segment_detector: Any = None,
    checkpoint_path: Path | None = None,
    strategy: str | None = None,
) -> tuple[list[SegmentDraft], dict[str, Any]]:
    """分段检测：律所 LLM（语义分类）优先，任何失败降级关键词规则引擎。

    返回 (drafts, summary 附加字段)。两条路径输出的 SegmentDraft 结构同构，
    后续校验（完整覆盖、无重叠）对两条路径一视同仁。

    ``checkpoint_path``：批级成果落盘位置（由调用方给到 job 的 analysis 目录）。
    worker 被杀后重跑据此续跑，不再为已完成的批重付 LLM 费用。

    ``strategy``：见 ``SEGMENT_STRATEGIES``。整本路径失败（超时/输出非法/覆盖不全）
    会**降级回分批**并把原因写进 ``segment_llm_fallback_reason``——不会退回规则引擎，
    因为分批 LLM 也失败了那才是规则引擎的事。
    """
    chosen = resolve_segment_strategy(strategy)
    if chosen == SEGMENT_STRATEGY_BATCH:
        return _detect_segments_batched(
            pages, template_key=template_key, detector=llm_segment_detector, checkpoint_path=checkpoint_path
        )
    return _detect_segments_wholebook(
        pages,
        template_key=template_key,
        batch_detector=llm_segment_detector,
        checkpoint_path=checkpoint_path,
        cross_check=chosen == SEGMENT_STRATEGY_WHOLEBOOK_CROSS,
    )


def _detect_segments_batched(
    pages: list[PageDescriptor],
    *,
    template_key: str,
    detector: Any = None,
    checkpoint_path: Path | None = None,
) -> tuple[list[SegmentDraft], dict[str, Any]]:
    """逐批摘要分段（原路径，逐字未改）。"""
    detector = detector if detector is not None else LLMSegmentDetector()
    # 单批降级必须能被 summary 说出来：前端 segmentBackendOf 读到 "llm" 就不提示
    # 规则降级，而「有几批其实是规则切的」只有分批执行器知道。
    batch_stats: dict[str, Any] = {}
    try:
        # 分批分段：164 页整本一次会让总时长撞上 Django-Q 的 600s worker 超时
        # 被杀（实测某次 164 页任务跑到 499s 被杀）。分批后单次 LLM 调用缩短到
        # 1-3 分钟，且死一批也能整轮降级而不会出现半成品。
        from .segment_batch import detect_in_batches

        drafts = detect_in_batches(
            pages=pages,
            template_key=template_key,
            detector=detector,
            stats=batch_stats,
            checkpoint_path=checkpoint_path,
        )
        # 续页合并：LLM 会把跨页的同一份材料从中间切开（实测 164 页卷宗里
        # 一份《个人房产抵押贷款合同》被切成 p116-125 / p126-140 两段）。
        # 判据是条款序号推进 + 后段首页无标题，详见 segment_merge.py。
        from .segment_merge import merge_continuation_segments

        drafts = merge_continuation_segments(drafts, {page.page_no: page.text for page in pages})
        return drafts, {
            "segment_backend": _segment_backend_of(batch_stats),
            "segment_llm_fallback_reason": "",
            "segment_total_batches": int(batch_stats.get("total_batches") or 0),
            "segment_rule_batches": int(batch_stats.get("rule_batches") or 0),
        }
    except Exception as exc:
        reason = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning("pdf_split_llm_segment_fallback", extra={"action": "llm_segment_fallback", "reason": reason})
        drafts = SegmentDetector().detect_segments(pages, template_key=template_key)
        return drafts, {"segment_backend": "rule", "segment_llm_fallback_reason": reason}


def _detect_segments_wholebook(
    pages: list[PageDescriptor],
    *,
    template_key: str,
    batch_detector: Any = None,
    checkpoint_path: Path | None = None,
    cross_check: bool = False,
) -> tuple[list[SegmentDraft], dict[str, Any]]:
    """整本一次分段；可要求同时跑分批路径并标出**边界分歧**。

    整本路径失败一律降级回分批（而不是直接掉到规则引擎）：分批 LLM 才是这个仓库
    原本的唯一 LLM 路径，整本只是「看得更全」的增强。降级原因写进 summary，
    否则「这次怎么切得不如上次」无从解释。
    """
    from .segment_merge import merge_continuation_segments
    from .wholebook_segment_detector import WholeBookSegmentDetector

    detector = WholeBookSegmentDetector()
    whole: list[SegmentDraft] | None = None
    fallback_reason = ""
    try:
        whole = detector.detect(pages, template_key=template_key)
        whole = merge_continuation_segments(whole, {page.page_no: page.text for page in pages})
    except (LLMSegmentationError, ValueError, RuntimeError, TimeoutError) as exc:
        # 只接「LLM 这条路失败」的可预期类型：供给不可用 / 输出非法 / 覆盖不全 / 超时。
        # 不接 Exception——编程错误应当炸出来，而不是被降级掩盖成「这次切得糙一点」。
        fallback_reason = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning(
            "pdf_split_wholebook_fallback", extra={"action": "wholebook_fallback", "reason": fallback_reason}
        )
        whole = None

    if whole is None:
        fallback_drafts, fallback_summary = _detect_segments_batched(
            pages, template_key=template_key, detector=batch_detector, checkpoint_path=checkpoint_path
        )
        fallback_summary["segment_llm_fallback_reason"] = fallback_reason or fallback_summary.get(
            "segment_llm_fallback_reason", ""
        )
        fallback_summary["segment_strategy"] = SEGMENT_STRATEGY_WHOLEBOOK
        return fallback_drafts, fallback_summary

    summary: dict[str, Any] = {
        "segment_backend": "llm_wholebook",
        "segment_llm_fallback_reason": "",
        "segment_total_batches": 1,
        "segment_rule_batches": 0,
        "segment_strategy": SEGMENT_STRATEGY_WHOLEBOOK_CROSS if cross_check else SEGMENT_STRATEGY_WHOLEBOOK,
        "segment_wholebook_budget": dict(getattr(detector, "last_budget", {}) or {}),
    }
    if not cross_check:
        return whole, summary

    # 交叉：分批路径的边界与整本不一致的地方，交给人裁定。
    #
    # 为什么不自动采信任一边：两条路径的分歧恰恰是「这段到底是一份还是两份」这种
    # 判断题——整本看得全但有幻觉风险，分批看得窄但对局部更专心。实测两者在
    # 「主体资格材料是否拆开」上稳定不同，这属于产品口径，不是谁能算出来的。
    batch_drafts, batch_summary = _detect_segments_batched(
        pages, template_key=template_key, detector=batch_detector, checkpoint_path=checkpoint_path
    )
    summary["segment_batch_backend"] = batch_summary.get("segment_backend", "")
    boundaries_whole = _boundary_set(whole)
    boundaries_batch = _boundary_set(batch_drafts)
    disagreed = sorted(boundaries_whole ^ boundaries_batch)
    summary["segment_boundary_disagreement_pages"] = disagreed
    summary["segment_boundary_disagreement_total"] = len(disagreed)
    if disagreed:
        _mark_boundary_disagreement(whole, disagreed)
        logger.info(
            "pdf_split_segment_boundary_disagreement",
            extra={"pages": disagreed, "wholebook": sorted(boundaries_whole), "batch": sorted(boundaries_batch)},
        )
    summary["segment_backend"] = "llm_wholebook_cross"
    return whole, summary


def _boundary_set(drafts: list[SegmentDraft]) -> set[int]:
    """一段的**起点页**集合就是它的切点集合（1 恒在，不算分歧）。"""
    return {int(d.page_start) for d in drafts if int(d.page_start) > 1}


def _mark_boundary_disagreement(drafts: list[SegmentDraft], disagreed: list[int]) -> None:
    """把落在分歧点附近的整本段标成「待裁定」。

    「附近」= 段首或段尾正好是某个分歧页；两侧各放一页，是因为分歧常常表现为
    「整本说 p22 起新段、分批说 p26 才起」，这时 p22 段的尾部与 p26 段的首部
    都值得看。
    """
    from apps.pdf_splitting.models import PdfSplitReviewFlag

    points = set(disagreed)
    for draft in drafts:
        start, end = int(draft.page_start), int(draft.page_end)
        if not (points & {start, start + 1, end, end + 1}):
            continue
        draft.review_flag = str(PdfSplitReviewFlag.BOUNDARY_DISAGREEMENT)


def _segment_backend_of(batch_stats: dict[str, Any]) -> str:
    """按各批实际走的路径给出 summary 口径：全 LLM / 混用 / 全规则。

    拿不到分批统计时按 "llm" 报——那是本轮没抛异常的唯一成功路径，
    与改动前一致；有统计就一律照实说，混用不再冒充纯 LLM。
    """
    total = int(batch_stats.get("total_batches") or 0)
    rule = int(batch_stats.get("rule_batches") or 0)
    if total <= 0:
        return "llm"
    if rule <= 0:
        return "llm"
    return "rule" if rule >= total else "mixed"


def clean_unstructured_page_text(text: str) -> str:
    """文本层 / 兜底页的噪声清洗：复用云端后端那套页眉页码判据 + 印章套话判据。

    云端块路径靠块类型（header / footer / page_number）滤噪声，这两条路径**没有块类型**，
    于是判决书页眉、页码、印章核验语每页重复混进正文（579 实测 83/164 页含印章套话）。
    判据一律复用现成的：``clean_page_artifacts``（云端两个后端共用）与
    ``page_quality`` 的印章套话正则，这里不另造一套。

    ⚠️ 含长纯数字行的页跳过 ``clean_page_artifacts``：它无条件删纯数字行，而卷宗里
    16/18/22 位的纯数字行是卡号/账号。印章套话不碰数字，仍然照清。
    """
    stripped = strip_stamp_boilerplate_lines(text)
    if _LONG_DIGIT_LINE_RE.search(stripped):
        return stripped
    return clean_page_artifacts(stripped)


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

    噪声清洗放在这里而不是各取字分支：文本层、兜底、缓存命中共四条分支都要清，
    逐处调用迟早漏一条（漏掉的那条就是「云端页干净、兜底页满屏印章」的劈叉）。
    """
    detector = segment_detector if segment_detector is not None else SegmentDetector()
    if source_method in _UNSTRUCTURED_SOURCES:
        text = clean_unstructured_page_text(text)
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


def _assert_page_integrity(pages: list[Any], *, expected: int) -> list[Any]:
    """取字产物必须**恰好覆盖 1..N 每页一次**，否则立刻失败而不是继续往下走。

    ## 为什么这条断言是必须的（2026-11-20 事故）

    原先这里是 `[item for item in descriptors if item is not None]`：页号缺失被
    静默「压紧」，于是第 k 个元素的页号可能不是 k。下游两处都按位置取值——
    `descriptors[page_no - 1]` 与段检测拿到的顺序——一旦错位，`pages.json` 的
    「页号 ↔ 文本」绑定就整体歪掉，而**整条链路没有一个地方会报错**：段检测照样
    输出 44 段、置信度照样 0.9，只是每段的正文和页号不是同一页。用户看到的是
    「全部识别错误、错页乱页」。

    这条断言把「静默出错」变成「当场失败」：宁可这次取字报错重跑，也不要交出一份
    页码错乱的分段结果——后者律师会拿去归档。
    """
    numbers = [int(getattr(page, "page_no", 0) or 0) for page in pages]
    duplicated = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicated:
        raise ValueError(f"取字产物页号重复：{duplicated[:10]}（共 {len(duplicated)} 个重复页号）")
    out_of_order = [n for i, n in enumerate(numbers) if i > 0 and n <= numbers[i - 1]]
    if out_of_order:
        raise ValueError(f"取字产物页号未严格递增：首个异常 {out_of_order[0]}（页序已乱，拒绝继续分段）")
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"取字产物页号必须从 1 连续：实际 {numbers[:5]}…{numbers[-3:]}")
    if numbers and len(numbers) != expected:
        raise ValueError(f"取字产物只覆盖 {len(numbers)} 页，应为 {expected} 页（缺页会让分段边界整体错位）")
    return pages


class PageTextExtractor:
    """逐页取字编排：文本层 → OCR 缓存 → 云端解析 → 本地 OCR 兜底 → 图片块补救。

    云端（MinerU/TextIn）一次解析整本并按页恢复结果，带版面块（供 Markdown
    重建结构）；云端失败或漏页由本地并行 OCR 兜底。所有取字结果按
    (PDF SHA-256 × 档位 × 页码) 落缓存，重复分析零成本。

    最后一步只对质量画像标出的图形页/证件页做定向补救（见 ``_rescue_image_pages``），
    不是逐页都跑。
    """

    def __init__(
        self,
        *,
        ocr_handler: Any = None,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
        heartbeat: HeartbeatCallback | None = None,
        budget: OCRStageBudget | None = None,
    ) -> None:
        self._ocr_handler = ocr_handler if ocr_handler is not None else OCRHandler()
        self._rule_detector = SegmentDetector()
        self._on_progress = on_progress
        self._is_cancelled = is_cancelled
        self._heartbeat = heartbeat
        # 预算只在**取字阶段被算出来**时才存在（见 split/service.extract_stage）：
        # 无任务上下文的直接调用（其他域复用、单测）不降级，行为与改动前一致。
        self._budget = budget

    # ------------------------------------------------------------------
    # 心跳 / 预算：长阻塞段与逐页降级共用
    # ------------------------------------------------------------------

    def _heartbeat_ctx(self) -> Any:
        """包住一段可能长时间无回调的阻塞调用（云端整本解析 / 图片补救单页识别）。

        没传心跳回调时返回 `nullcontext()`：纯函数调用（例如别的域直接调
        `analyze_pdf`）不应该因为多了一个上下文管理器就产生任何行为。
        """
        if self._heartbeat is None:
            return nullcontext()
        return heartbeat_block(self._heartbeat)

    def _ocr_kwargs(self) -> dict[str, Any]:
        """`parallel_ocr` 的可选关键字：**只有在真有值时才传**。

        为什么不做成恒定传 `budget=None, heartbeat=None`：`ocr_handler` 是依赖注入点，
        既有测试桩 / 旧实现的 `parallel_ocr` 签名不带这两个参数，恒传会直接 TypeError。
        只在有值时下传，存量桩零改动，而生产路径（两个值都有）拿到完整能力。
        """
        extra: dict[str, Any] = {}
        if self._budget is not None:
            extra["budget"] = self._budget
        if self._heartbeat is not None:
            extra["heartbeat"] = self._heartbeat
        return extra

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

        stats: dict[str, Any] = {
            "runtime_profile": runtime_profile,
            "pdf_hash": pdf_hash,
            "cloud_backend": cloud_backend,
            "cloud_candidates": cloud_candidates,
            "cloud_cache_profile": cloud_cache_profile,
            "cache_hit_count": 0,
            "cloud_cache_hit_count": 0,
            # 缓存条目里恢复出来的真实平台计数：本轮没调云端时，它是唯一的来源证据
            "cache_providers": Counter(),
            "cloud_succeeded": False,
            "pending_ocr_count": 0,
            "cloud_error": "",
            "layout_mode": layout_mode,
            # 补版面但云端不可用：必须让调用方知道「你以为开了、其实没生效」
            "layout_unavailable_reason": "",
            "image_rescue_pages": [],
            "image_rescue_chars": 0,
            "image_rescue_reused": 0,
            # 因预算不足被跳过的页（逐页 OCR 阶段）：只计不拦，但必须能让 summary 说出来。
            "budget_skipped_pages": [],
            # 因预算不足整批放弃的图片补救页数（补救是附加内容，不是正文必要的路）
            "image_rescue_skipped_budget": 0,
            # 云端/缓存给出的正文被判为「废的」（复读循环、空返回）的页。
            # 它们不算取字成功——清掉后进 pending，走既有兜底链重新取字。
            "degenerate_pages": [],
            "cache_degenerate_pages": [],
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
            # 立案材料一式三份是常态：先把与前面某页**版式完全相同**的页挑出来，
            # 只 OCR 代表作，其余页在 OCR 结束后继承文字。真实 40 页扫描件里 25 页
            # 是副本，本机 OCR 取字从 97s 降到 ~40s（见 page_fingerprint 模块头）。
            duplicate_pages = self._dedupe_pending_pages(doc, stats)
            self._resolve_pending_pages(
                pdf_path, descriptors=descriptors, pdf_hash=pdf_hash, template_key=template_key, stats=stats
            )
            self._fill_duplicate_pages(descriptors, duplicates=duplicate_pages, template_key=template_key, stats=stats)

        # 补救放在取字全部定稿之后：判据要的是「这一页最终读出来多少内容」，
        # 半路补救会对同一页重复判定，也可能把云端还没填的页当成图形页。
        self._rescue_image_pages(pdf_path, descriptors=descriptors, template_key=template_key, stats=stats)
        final_pages = [item for item in descriptors if item is not None]
        _assert_page_integrity(final_pages, expected=stats.get("total_pages") or len(descriptors))
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
            if cached is not None and (cached_reason := degeneracy_reason(cached.text)):
                # 缓存里躺着的是复读/空的垃圾：**不能采信**，否则这一页永久是垃圾
                # （缓存命中会一遍遍把同一份垃圾搬回来）。把它重新扔回 pending，
                # 这一轮重新取字；取到干净结果时会覆盖缓存条目。
                stats["cache_degenerate_pages"].append(page_no)
                logger.warning(
                    "pdf_split_cache_page_degenerate",
                    extra={"page_no": page_no, "reason": cached_reason, "source": cached.source_method[:32]},
                )
                cached = None
            if cached is not None:
                descriptors[page_index] = build_page_descriptor(
                    page_no=page_no,
                    text=cached.text,
                    # 用缓存条目自己的来源：档案名记的是首选平台，容灾写进来的可能是
                    # 另一个平台的结果。照抄 "ocr_cache" 会把真实坐标系来源抹掉。
                    source_method=cached.source_method,
                    ocr_failed=cached.ocr_failed,
                    template_key=template_key,
                    layout=cached.layout,
                    segment_detector=self._rule_detector,
                )
                resolved_pages += 1
                stats["cache_hit_count"] += 1
                stats["cloud_cache_hit_count"] += int(cached_from_cloud)
                cached_backend = cloud_backend_of_method(cached.source_method)
                if cached_backend:
                    stats["cache_providers"][cached_backend] += 1
                self._report_progress(resolved_pages, total_pages)

        stats["pending_page_numbers"] = [no for no in range(1, total_pages + 1) if descriptors[no - 1] is None]
        return descriptors

    def _dedupe_pending_pages(self, doc: fitz.Document, stats: dict[str, Any]) -> dict[int, int]:
        """把「与前面某页版式完全相同」的待取字页挑出来，只留代表作进 OCR。

        **只在本机 OCR 路径生效**：云端（MinerU/TextIn）是一次整本解析，少送几页
        省不掉那一次往返，反而让页序对齐更复杂。

        宁漏不错：阈值见 page_fingerprint（真实样本上真副本 ≤0.024、不同文书 ≥0.044）。
        漏判只是多 OCR 一页；误判会把两页不同内容的文字合成一份，只能靠人工复核发现。
        """
        stats["dedupe_skipped_pages"] = 0
        pending: list[int] = list(stats.get("pending_page_numbers") or [])
        if stats.get("cloud_backend") is not None or len(pending) < 2:
            return {}
        signatures: dict[int, list[float]] = {}
        for page_no in pending:
            self._raise_if_cancelled(page_no - 1)
            signatures[page_no] = page_signature(doc.load_page(page_no - 1))
        duplicates = find_duplicate_pages(signatures)
        if not duplicates:
            return {}
        stats["dedupe_skipped_pages"] = len(duplicates)
        stats["pending_page_numbers"] = [page_no for page_no in pending if page_no not in duplicates]
        return duplicates

    def _fill_duplicate_pages(
        self,
        descriptors: list[PageDescriptor | None],
        *,
        duplicates: dict[int, int],
        template_key: str,
        stats: dict[str, Any],
    ) -> None:
        """把代表作的取字结果抄给重复页（页号仍是自己的，版式块同页可直接沿用）。"""
        filled = 0
        for page_no, rep_no in duplicates.items():
            representative = descriptors[rep_no - 1]
            if representative is None:  # 代表作也没取到字：保持缺页，由完整性断言兜底
                continue
            descriptors[page_no - 1] = build_page_descriptor(
                page_no=page_no,
                text=representative.text,
                source_method="dedupe_copy",
                ocr_failed=representative.ocr_failed,
                template_key=template_key,
                layout=representative.layout,
                segment_detector=self._rule_detector,
            )
            filled += 1
        stats["dedupe_filled_pages"] = filled

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

        # 这里只处理**可用**页：空 / 退化 / 候选没覆盖的页已经在 `_parse_cloud` 里摘成
        # 「残余页」并接力给下一个候选；所有候选都试完仍没救回来的页，落在下面的
        # `local_fallback_pages` 里走本地 OCR。
        for page_no in sorted(cloud_results):
            self._raise_if_cancelled(page_no)
            result = cloud_results[page_no]
            self._ocr_handler.write_ocr_cache(
                pdf_hash=pdf_hash,
                profile_key=stats["cloud_cache_profile"],
                result=result,
                page_no=page_no,
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
        # 预算与心跳一起下传：逐页 OCR 可能一页阻塞 300s，**这一段既无进度回调也无 DB 写入**
        # （2026-11-20 事故里就冻结在这里 839s），必须靠心跳回调 + 逐页预算门禁控住。
        ocr_results = self._ocr_handler.parallel_ocr(
            pdf_path=pdf_path,
            page_numbers=local_fallback_pages,
            runtime_profile=stats["runtime_profile"],
            **self._ocr_kwargs(),
        )
        # 因预算不足被跳过的页：**不写页缓存**。预算是这一次运行的临时状态，写进缓存就变成
        # 「这页永久没字」——下一轮即使预算充足也会命中缓存直接跳过，降级变成永久损失。
        budget_skipped = set(self._budget.skipped_pages) if self._budget is not None else set()
        for page_no in local_fallback_pages:
            self._raise_if_cancelled(page_no)
            result = ocr_results.get(page_no) or OCRPageResult(
                page_no=page_no, text="", source_method="ocr_failed", ocr_failed=True
            )
            if page_no not in budget_skipped:
                self._ocr_handler.write_ocr_cache(
                    pdf_hash=pdf_hash, profile_key=stats["runtime_profile"].key, result=result
                )
            else:
                stats["budget_skipped_pages"].append(page_no)
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
        if stats["budget_skipped_pages"]:
            # 必须留痕：`llm_segment_detector` 会把 ocr_failed 页当「未取到文字」跳过，
            # 少页文本会影响分段边界。这个代价必须可见，而不是只体现在“这次快了点”。
            logger.warning(
                "pdf_split_ocr_budget_degraded",
                extra={
                    "skipped_pages": len(stats["budget_skipped_pages"]),
                    "total_pending_pages": len(local_fallback_pages),
                    "page_numbers": stats["budget_skipped_pages"][:50],
                    "remaining_seconds": round(self._budget.remaining_seconds(), 1) if self._budget else None,
                },
            )

    def _rescue_image_pages(
        self,
        pdf_path: Path,
        *,
        descriptors: list[PageDescriptor | None],
        template_key: str,
        stats: dict[str, Any],
    ) -> None:
        """图形页 / 证件缺字段页的图片块定向补救 OCR。

        为什么需要：MinerU 把照片、手写页整块当图片返回，块里一个字都没有，重建层
        按类型把 image 块丢掉——579 实测 54 个 image 块全丢，身份证页只剩 45 字印章语、
        面谈笔录 2 页只剩 209 字。质量画像**已经标出**这些页（graphic / doc_missing），
        但从来没人拿它触发补救。这里把那条信号兑现成一次定向识别。

        为什么不无谓重复计费：兜底页（source_method=ocr*）的版面本来就来自 VL 那次
        响应，图片区域的内容已经在里面，再调一次是同一页付两次钱——直接记成复用。
        """
        pages = [item for item in descriptors if item is not None]
        qualities = qualities_by_page(pages)
        targets = [
            (page, region)
            for page in pages
            if (region := rescue_image_region(page, qualities[page.page_no])) is not None
        ]
        if not targets:
            return
        if len(targets) > _RESCUE_MAX_PAGES:
            logger.warning(
                "pdf_split_image_rescue_capped",
                extra={"targets": len(targets), "cap": _RESCUE_MAX_PAGES},
            )
        capped = targets[:_RESCUE_MAX_PAGES]
        # 预算门禁（现有兜底路径的第二段，不是新发明的一条路）：补救是**附加**内容，
        # 每页还是一次最坏 300s 的云端调用。取字本身已经把预算吃光时，宁可直接不作补救，
        # 也不要发出“注定把任务拖过 django-q 硬阀值”的调用（2026-11-20：整轮白跑）。
        # 正文已经拿到（补救只补图形块/证件字段），丢掉它只是少几页细节，不是丢整份结果。
        if self._budget is not None and not self._budget.allows_single_page_ocr():
            stats["image_rescue_skipped_budget"] = len(capped)
            logger.warning(
                "pdf_split_image_rescue_skipped_budget",
                extra={
                    "targets": len(capped),
                    "page_numbers": [page.page_no for page, _region in capped],
                    "remaining_seconds": round(self._budget.remaining_seconds(), 1),
                    "required_seconds": round(self._budget.required_seconds(), 1),
                },
            )
            return
        for index, (page, region) in enumerate(capped):
            # 逐页再判一次：补救过程中预算还在减（一页 29s，几页就能把余量吃浅）。
            if self._budget is not None and not self._budget.allows_single_page_ocr():
                stats["image_rescue_skipped_budget"] = len(capped) - index
                logger.warning(
                    "pdf_split_image_rescue_skipped_budget",
                    extra={
                        "page_no": page.page_no,
                        "remaining_targets": len(capped) - index,
                        "remaining_seconds": round(self._budget.remaining_seconds(), 1),
                        "required_seconds": round(self._budget.required_seconds(), 1),
                    },
                )
                break
            self._rescue_one_page(
                pdf_path, page, region=region, descriptors=descriptors, template_key=template_key, stats=stats
            )

    def _rescue_one_page(
        self,
        pdf_path: Path,
        page: PageDescriptor,
        *,
        region: list[float],
        descriptors: list[PageDescriptor | None],
        template_key: str,
        stats: dict[str, Any],
    ) -> None:
        """补救单页：识别图片区域 → 并进该页正文与版面 → 回写缓存（重跑不再付费）。"""
        if page.source_method in _UNSTRUCTURED_SOURCES:
            # 兜底页的版面就是 VL 那次响应给的，内容已在其中，不再重复计费
            stats["image_rescue_reused"] += 1
            return
        try:
            # 单页补救也是一次云端调用（实测 ~29s，最坏 300s）：同样需要心跳块兜住。
            with self._heartbeat_ctx():
                rescued = self._ocr_handler.ocr_page_region(
                    pdf_path=pdf_path, page_no=page.page_no, region=region, runtime_profile=stats["runtime_profile"]
                )
        except Exception:
            # 补救是附加内容：它失败不能让已经取好的整本卷宗判失败
            logger.exception("pdf_split_image_rescue_failed", extra={"page_no": page.page_no})
            return
        if not rescued:
            logger.warning("pdf_split_image_rescue_empty", extra={"page_no": page.page_no})
            return

        text = f"{page.text}\n\n{rescued['text']}".strip()
        layout = dict(page.layout or {})
        layout["blocks"] = [
            *mark_rescued_image_blocks(layout.get("blocks") or [], region=region),
            *rescued["blocks"],
        ]
        layout["text"] = text
        descriptors[page.page_no - 1] = build_page_descriptor(
            page_no=page.page_no,
            text=text,
            source_method=page.source_method,
            ocr_failed=False,
            template_key=template_key,
            layout=layout,
            segment_detector=self._rule_detector,
        )
        stats["image_rescue_pages"].append(page.page_no)
        stats["image_rescue_chars"] += len(str(rescued["text"]))
        logger.info(
            "pdf_split_image_rescued",
            extra={"page_no": page.page_no, "chars": len(str(rescued["text"])), "region": region},
        )
        self._cache_rescued_page(page, text=text, layout=layout, stats=stats)

    def _cache_rescued_page(
        self, page: PageDescriptor, *, text: str, layout: dict[str, Any], stats: dict[str, Any]
    ) -> None:
        """把补救后的整页结果回写页缓存：同一份 PDF 重跑时不再为这几页付第二次钱。"""
        if not stats.get("cloud_cache_profile"):
            return
        try:
            self._ocr_handler.write_ocr_cache(
                pdf_hash=stats["pdf_hash"],
                profile_key=stats["cloud_cache_profile"],
                result=OCRPageResult(
                    page_no=page.page_no, text=text, source_method=page.source_method, ocr_failed=False, layout=layout
                ),
            )
        except Exception:
            logger.exception("pdf_split_image_rescue_cache_failed", extra={"page_no": page.page_no})

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
            # 退化页**不写缓存**：缓存是「这页已经取好了」的账本，把复读/空的垃圾写进去
            # 等于把这页永久钉死成垃圾——下一轮命中缓存直接采信，永远救不回来。
            # （写缓存发生在批次回调里，比逐页判退化更早，所以这里必须再挡一道。）
            if degeneracy_reason(getattr(result, "text", "")):
                continue
            try:
                # page_no 传**权威键**（绝对页号），不要依赖 result 自带的页号：
                # 分批解析曾只平移字典键、不改值，导致多批写到同一批缓存文件名上互相覆盖
                self._ocr_handler.write_ocr_cache(
                    pdf_hash=pdf_hash, profile_key=profile_key, result=result, page_no=page_no
                )
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
        """云端解析，**分批 + 断点续传**，按候选平台逐个尝试（容灾 + 残余页接力）。

        为什么不整本一次发：164 页的真实卷宗整本解析时长过久，进程中途一死
        （开发环境的 watchfiles 重启、生产环境的 OOM/部署）就把全部成果归零——
        实测同一份材料连续两次死在 135/164 且每次都从零开始。分批后每批
        完成即落盘，断在哪补哪。详见 `cloud_batch.py`。

        ## 残余页必须接力下一个候选（2026-11-25）

        原实现是「任一候选返回非空字典就锁定并返回」，而「空页 / 退化页 / 候选没覆盖
        的页」是**返回之后**才判的（`_resolve_pending_pages`）。于是候选 1（如 DeepSeek）
        吐了复读/空返回的那些页永远接不到候选 2（如 MinerU 小批），直接掉进本地逐页
        `parallel_ocr`：一份 37 页材料里 26 页逐页兜底，吃掉了 20.7 分钟里的大部分。

        现在按**候选轮次**推进：每轮只解析「上一轮没拿到可用结果」的页；
        `tried[页号]` 记着这页已经试过哪些候选，所以**同一候选不会对同一页调两次**。
        全部候选都试完仍没有可用结果的页，才交给调用方走本地兜底。

        Args:
            on_batch_done: 每批落盘回调。**每一轮都要传下去**——断点续传的落盘点在这里，
                接力轮次同样要落盘，否则候选 2 补回来的页在进程死掉后又要重新付费。
            on_progress: `(resolved, total)`；多轮时已完成的页计入偏移，进度不回退。
        """
        candidates: list[str] = stats.get("cloud_candidates") or []
        if not candidates:
            return {}

        page_numbers: list[int] = sorted(stats.get("pending_page_numbers") or [])
        if not page_numbers:
            return {}

        accepted: dict[int, Any] = {}
        residual = list(page_numbers)
        # 「这页已试过哪几个候选」的唯一状态：每轮挑候选前先看它，试完立刻记下
        tried: dict[int, set[str]] = {page_no: set() for page_no in page_numbers}
        errors: list[str] = []
        total = len(page_numbers)
        resolved_before = 0
        #: 第一个真正返回结果的候选（= 主平台）。stats 里 `cloud_backend` 是单一值，
        #: 多轮接力时只由它写一次，后补的候选不会覆盖（避免同一字段被重复计数）。
        primary: str | None = None

        def round_progress(resolved: int, _batch_total: int) -> None:
            if on_progress is not None:
                on_progress(resolved_before + resolved, total)

        for index, backend in enumerate(candidates):
            if not residual:
                break
            # 只把「这页还没试过这个候选」的页送出去：同一候选不得对同一页调两次
            round_pages = [page_no for page_no in residual if backend not in tried[page_no]]
            if not round_pages:
                continue
            for page_no in round_pages:
                tried[page_no].add(backend)
            try:
                round_results = self._parse_cloud_round(
                    pdf_path,
                    backend=backend,
                    page_numbers=round_pages,
                    on_batch_done=on_batch_done,
                    on_progress=round_progress,
                )
            except Exception as exc:
                logger.exception("pdf_split_cloud_ocr_failed", extra={"provider": backend})
                errors.append(f"{backend}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
            if not round_results:
                # 解析成功但一页都没出来：同样视为这次尝试失败，继续下一个
                logger.warning("pdf_split_cloud_empty", extra={"provider": backend, "pages": len(round_pages)})
                errors.append(f"{backend}: 返回空结果")
                continue
            # 命中：把实际生效的平台记进 stats，summary / 缓存档案都以它为准。
            # 只在第一个返回结果的候选上写一次——后面的候选只是补残余页。
            if primary is None:
                primary = backend
                stats["cloud_backend"] = backend
                stats["cloud_succeeded"] = True
                stats["cloud_failover_from"] = candidates[:index]
                if index > 0:
                    logger.info("云端容灾生效：%s 失败后改用 %s", " -> ".join(candidates[:index]), backend)
            # `round_pages` 就是本轮之前的**全部**残余页（一个候选对每一页只试一次），
            # 所以这里返回的残余集合是完整的：本轮没用上的页一页都不会被漏掉。
            usable, residual = self._classify_cloud_round(round_results, round_pages, stats)
            if usable and not accepted and primary != backend:
                # 主平台「回了结果但一页可用都没有」（全空/全退化，实测 DeepSeek 整本
                # 空返回会出现）：产物其实全部来自这个候选，平台归属必须改记它。
                # 不改的话坐标系与摘要会把整本算到没出字的那个引擎头上（见
                # `_actual_provider`：平台报错 → 绿框整体错位）。
                logger.warning(
                    "pdf_split_cloud_primary_no_usable_page",
                    extra={"provider": primary, "fallback": backend, "pages": len(usable)},
                )
                stats["cloud_backend"] = backend
                stats["cloud_failover_from"] = candidates[:index]
                primary = backend
            if usable and primary != backend:
                logger.info(
                    "云端残余页接力生效：%s 补回 %d 页（主平台 %s）",
                    backend,
                    len(usable),
                    primary,
                )
            if not usable:
                # 候选回了结果，但这一轮没有一页可用（全空/全退化/页码对不上）：
                # 仍然要换下一个候选，并把原因留在 cloud_error 里（律师看得到）。
                logger.warning("pdf_split_cloud_no_usable_page", extra={"provider": backend, "pages": len(round_pages)})
                errors.append(f"{backend}: {len(round_pages)} 页均无可用的取字结果")
            accepted.update(usable)
            resolved_before += len(usable)

        # 所有候选都没给出**任何**可用页：把各平台错误汇总成回落原因
        if not accepted:
            stats["cloud_error"] = (
                " | ".join(errors).replace(pdf_path.as_posix(), "[source PDF]")[:800] or "云端解析失败"
            )
        return accepted

    def _parse_cloud_round(
        self,
        pdf_path: Path,
        *,
        backend: str,
        page_numbers: list[int],
        on_batch_done: Any,
        on_progress: Any,
    ) -> dict[int, Any]:
        """用**一个**候选解析 `page_numbers`（可稀疏），返回整卷绝对页号的结果。

        长阻塞段仍在这里包心跳：整本云端解析实测 MinerU 单路曾静默阻塞 4347s，
        批级进度回调之间有很长的沉默期，不包心跳看门狗会把在跑的任务判死。
        """
        from .cloud_batch import parse_in_batches

        with self._heartbeat_ctx():
            return parse_in_batches(
                source_path=pdf_path,
                page_numbers=page_numbers,
                parse_one=lambda mini_path: self._ocr_handler.parse_cloud_pages(pdf_path=mini_path, backend=backend),
                on_batch_done=on_batch_done,
                on_progress=on_progress,
            )

    def _classify_cloud_round(
        self,
        results: dict[int, Any],
        page_numbers: list[int],
        stats: dict[str, Any],
    ) -> tuple[dict[int, Any], list[int]]:
        """把一轮结果分成「可用页」与「残余页（空 / 退化 / 候选没覆盖）」。

        退化页**不写页缓存**（批次回调 `_persist_cloud_batch` 已按批挡了一道，这里只
        负责记账）：缓存是「这页已经取好了」的账本，写进去就变成永久垃圾。

        `degenerate_pages` 只在**第一次**记一次：同一页可能被多个候选先后判成退化，
        每轮都 append 会让 summary 里的退化页数虚高。
        """
        usable: dict[int, Any] = {}
        residual: list[int] = []
        for page_no in page_numbers:
            self._raise_if_cancelled(page_no)
            result = results.get(page_no)
            text = str(getattr(result, "text", "") or "")
            if not text:
                # 空返回 / 候选压根没覆盖这一页：都算残余，交给下一个候选
                residual.append(page_no)
                continue
            if reason := degeneracy_reason(text):
                residual.append(page_no)
                if page_no not in stats["degenerate_pages"]:
                    stats["degenerate_pages"].append(page_no)
                logger.warning(
                    "pdf_split_cloud_page_degenerate",
                    extra={
                        "page_no": page_no,
                        "reason": reason,
                        "source": str(getattr(result, "source_method", ""))[:32],
                    },
                )
                continue
            usable[page_no] = result
        return usable, residual

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

    def _actual_provider(self, stats: dict[str, Any]) -> str:
        """本轮产物**真正**出自哪个平台（坐标系换算就按它）。

        首选平台不等于实际平台：容灾会换平台，而全部命中缓存那一轮根本不调云端，
        ``cloud_backend`` 仍是首选值。此时若缓存里躺着上一次容灾写进来的 TextIn 结果，
        照首选报 MinerU 就会拿千分比去除绝对坐标——绿框整体错位。
        """
        preferred = str(stats["cloud_backend"] or "")
        cached = stats.get("cache_providers") or {}
        if not cached:
            return preferred or "local"
        dominant = str(max(cached.items(), key=lambda item: item[1])[0])
        if len(cached) > 1:
            logger.warning(
                "pdf_split_mixed_cached_providers",
                extra={"providers": dict(cached), "chosen": dominant},
            )
        if stats.get("cloud_succeeded"):
            return preferred or dominant
        return dominant

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
        summary = {
            "ocr_profile": runtime_profile.key,
            "ocr_dpi": runtime_profile.dpi,
            "ocr_model": "v5_server" if runtime_profile.use_v5 else "v4_default",
            "ocr_workers": runtime_profile.workers,
            "ocr_cache_hit_count": int(max(stats["cache_hit_count"], 0)),
            "ocr_miss_count": int(max(pending, 0)),
            # 云端/缓存给出「废正文」的页：这些页已被重新扔回 pending 走兜底。
            # 必须单独报——它们**曾经**被当成取字成功（有字、任务成功、日志无痕）。
            "degenerate_pages": sorted(
                {int(no) for no in (stats.get("degenerate_pages") or [])}
                | {int(no) for no in (stats.get("cache_degenerate_pages") or [])}
            ),
            "ocr_provider": self._actual_provider(stats),
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
            # 图片块补救的兑现情况：救了几页、救回多少字、几页是复用已有 VL 结果。
            # 「质量画像标了图形页」与「真的去补救了」是两件事，后者必须可观测。
            "image_rescue_pages": list(stats.get("image_rescue_pages") or []),
            "image_rescue_chars": int(stats.get("image_rescue_chars") or 0),
            "image_rescue_reused": int(stats.get("image_rescue_reused") or 0),
            # 重复页去重（一式三份）：省掉多少页 OCR、补回多少页文字。
            # 这两个数就是「为什么这次取字比上次快一半」的直接证据。
            "dedupe_skipped_pages": int(stats.get("dedupe_skipped_pages") or 0),
            "dedupe_filled_pages": int(stats.get("dedupe_filled_pages") or 0),
        }
        if self._budget is not None:
            # 预算降级的观测面：**只有真算了预算才追加这几个键**，不在无预算的
            # 纯函数调用（别的域复用 / 单测）上凭空多出字段。
            summary.update(
                {
                    "stage_budget_seconds": round(self._budget.total_seconds, 1),
                    "stage_budget_remaining_seconds": round(self._budget.remaining_seconds(), 1),
                    # 因预算不足而没发云端调用的页数（下游会把它们当“未取到文字”）
                    "ocr_budget_skipped_count": len(stats["budget_skipped_pages"]),
                    "ocr_budget_skipped_pages": list(stats["budget_skipped_pages"]),
                    "image_rescue_skipped_budget": int(stats.get("image_rescue_skipped_budget") or 0),
                }
            )
        return summary
