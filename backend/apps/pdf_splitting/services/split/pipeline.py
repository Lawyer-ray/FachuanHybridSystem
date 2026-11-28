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
    PageTextExtractor（取字编排，实现在 page_text_extractor.py）
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

取字那半边（``PageTextExtractor`` / ``build_page_descriptor`` / 版面策略常量 /
取字异常）已拆到 ``page_text_extractor.py``；本模块按**原路径** re-export，
``from apps.pdf_splitting.services.split.pipeline import PageTextExtractor`` 照旧可用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.db import DatabaseError

from .consistency_summary import attach_quality_flags_to_markdown, detect_inconsistencies, pick_top_inconsistencies
from .llm_segment_detector import LLMSegmentationError, LLMSegmentDetector
from .markdown_builder import build_segments_markdown
from .ocr_handler import OCRStageBudget
from .page_quality_summary import attach_page_quality_flags, build_page_quality_summary, qualities_by_page

# 取字组件的实体在 ``page_text_extractor``：这里 re-export，既有调用方（service.py /
# rotated_backfill.py / 单测）继续按 pipeline 路径 import，不必改一行。
from .page_text_extractor import (
    _RESCUE_MAX_PAGES,
    LAYOUT_MODE_FAST_TEXT,
    LAYOUT_MODE_LAYOUT,
    CancelCallback,
    HeartbeatCallback,
    LockedCloudBackendUnavailable,
    PageTextExtractor,
    PipelineCancelled,
    ProgressCallback,
    _assert_page_integrity,
    build_page_descriptor,
    clean_unstructured_page_text,
    locked_cloud_backend_message,
)
from .segment_detector import SegmentDetector
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")


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
            （容灾）；``mineru`` / ``textin`` / ``deepseek`` 锁定单一平台、失败即失败
            （不降级）。**锁定平台当前不可用**（一个候选都解析不出来，典型原因：平台未
            启用 / ``DEEPSEEK_OCR_API_KEY`` 未配）时，只要真的走到云端取字就会抛
            :class:`LockedCloudBackendUnavailable`——不静默回落本地 OCR，也不采信页缓存
            （那份档案里只可能是本地兜底的结果）。锁定不可用时**不会**被当成 auto：
            ``None`` / ``auto`` / 脏值才走 auto。
        layout_mode: 版面策略。``fast_text``（默认）电子页只抽文本层、不调云端；
            ``layout`` 让电子页也上云端拿版面块与坐标（"原文坐标索引对照"需要），
            代价是这些页也要计费且更慢。容量不足/调用失败时回落文本层并在
            summary.layout_unavailable_reason 说明。
            注意：``layout`` **故意不**把「整本文本层都可用」当成完事（那会连坐标都没
            有可用），所以「锁定平台不可用 + 纯电子件 + layout」会失败而不是回落文本层。
            这是刻意取舍：锁定了就不许换路，否则用户以为拿到的是他选的平台的坐标。
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
#:
#: 取值必须与落库枚举 ``models.PdfSplitSegmentStrategy`` 逐字一致（那边是用户选的
#: 枚举，这里是执行侧常量）。
SEGMENT_STRATEGY_BATCH = "batch"
SEGMENT_STRATEGY_WHOLEBOOK = "wholebook"
SEGMENT_STRATEGY_WHOLEBOOK_CROSS = "wholebook_cross"
SEGMENT_STRATEGIES: tuple[str, ...] = (
    SEGMENT_STRATEGY_BATCH,
    SEGMENT_STRATEGY_WHOLEBOOK,
    SEGMENT_STRATEGY_WHOLEBOOK_CROSS,
)


def resolve_segment_strategy(explicit: str | None = None) -> str:
    """分段策略的取值来源：**任务级选择 > SystemConfig 默认 > batch**。

    ``explicit`` 是**用户在这个任务上选的**（``PdfSplitJob.segment_strategy``）：
    有值就永远以它为准，部署级配置不得覆盖单次任务的选择。

    ``explicit`` 为空时才读 SystemConfig 的 ``PDF_SPLIT_SEGMENT_STRATEGY``——它现在
    只是「部署级默认值」，不再是唯一入口（历史任务与未传该字段的调用方走这条）。

    为什么最后一道默认仍是 batch：整本一次要一口气看完一本书，大卷宗会撞 LLM 超时；
    分批是踩过「164 页整本一次跑到 499s 被 worker 杀掉」之后才改成默认的。
    想用整本路径就显式选——不存在「悄悄换成另一种切法」。
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
