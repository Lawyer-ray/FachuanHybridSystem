"""PdfSplitService facade — 保持原有公共 API 不变。"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pymupdf as fitz
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
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
    parse_dual_engines,
)
from apps.pdf_splitting.services.heartbeat import periodic_heartbeat
from apps.pdf_splitting.services.heartbeat import touch_heartbeat as _touch_heartbeat_row
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.pdf_splitting.services.template_registry import get_default_filename

from .consistency_summary import attach_quality_flags_to_markdown, detect_inconsistencies, pick_top_inconsistencies
from .dual_engine_runner import plan_dual_engine_factories, run_dual_engine
from .export_utils import ExportUtils, deduplicate_filename, export_segment_pdf
from .markdown_builder import build_segments_markdown, load_segment_markdown_map
from .ocr_handler import OCRHandler, cloud_backend_of_method
from .output_rotation import apply_page_rotations, parse_page_rotations
from .page_quality_summary import attach_page_quality_flags, qualities_by_page
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


def _dual_engine_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """把落盘的双引擎产物展开成 summary 键。

    形状固定（即使没跑双引擎也给空列表 + 三个 0）：前端抽屉直接 ``.map``，
    不用为「有没有双引擎」写分支；也避免旧任务里这两个键缺失导致的 undefined。
    """
    return {
        "engine_disagreements": list(payload.get("engine_disagreements") or []),
        "engine_disagree_summary": dict(payload.get("engine_disagree_summary") or {})
        or {"high": 0, "medium": 0, "low": 0},
        "dual_engine": dict(payload.get("dual_engine") or {}),
        # 转正页回填的记账（cross_check 阶段写好并落盘）：哪几页被 VL 换过、每页跳过原因。
        # 空 dict = 这次没开双引擎 / 没被转正页命中——不能省这个键，否则前端要写分支。
        "rotated_backfill": dict(payload.get("rotated_backfill") or {}),
        # 分歧裁定的总账。形状固定（没跑过也是这套零值）：前端要显示
        # 「332 条分歧里自动裁定 12 条」，缺键就得写 `?? 0`，而 `?? 0` 会把
        # 「功能关着」与「跑了但一条都没判成」显示成同一个样子。
        # 零值里必须带上 ``requested``：前端拿它与 ``enabled`` 对比才能说
        # 「你开了但没生效」，缺键就会被当成 false 而误报。
        "engine_disagreements_judge": dict(payload.get("engine_disagreements_judge") or {})
        or {"enabled": False, "requested": False, "annotated": 0, "accepted": 0, "human": 0, "reasons": {}},
    }


def _provider_from_pages(pages: list[PageDescriptor]) -> str:
    """从逐页取字来源推断整本的云端平台（取字 summary 缺失时的降级判据）。

    只认 ``mineru_ocr`` / ``textin_ocr`` 这类带平台名的来源；本地 OCR 与文本层
    没有平台可言，返回空串让上层如实说「坐标不可用」，而不是猜一个平台。
    多平台混用时取页数最多的那个，并交给上层记 warning。
    """
    counts: dict[str, int] = {}
    for page in pages:
        backend = cloud_backend_of_method(page.source_method)
        if backend:
            counts[backend] = counts.get(backend, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


#: 段文件名里的旧扩展名（.pdf / .md）—— 打包时名字统一由本模块重生，
#: 两种后缀都得先剥掉，否则同一个段会落成 ``01_起诉状.pdf.pdf``。
_SEGMENT_SUFFIX_RE = re.compile(r"\.(?:pdf|md)$", re.IGNORECASE)


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """条目列表 → zip 字节。

    集中一处是为了让「整包 / 多选 / 导出任务落盘」三条路径的压缩参数
    （deflate、平铺、不写目录项）只有一个口径：任何一条路径单独变化，
    律师拿到的包结构就会和界面上看到的段列表对不上。
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in entries:
            archive.writestr(filename, content)
    return buffer.getvalue()


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
                # 心跳回调同样要下传：这条旧全量路径里的逐页 OCR 也会长时间无回调。
                # 预算传 None：本路径没有按阶段覆盖 django-q timeout（走集群默认值），
                # 拿不到可信数字就不编一个——宁可不降级，也不拿错的尺子量剩余时间。
                heartbeat=lambda: self.touch_heartbeat(job_id=job.id),
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

        ## 为什么在这里算预算、并把心跳封成回调下传

        本方法是“最近一个知道 django-q 给本任务多少秒”的地方（`submit_extract_stage`
        提交的就是 `EXTRACT_STAGE_TIMEOUT_SECONDS`），而真正会阻塞的是下面的逐页 OCR
        （线程池里，单页最坏 300s）。2026-11-20 事故：93 页卷宗在这里遇上 8 次单页超时，
        心跳冻结 839s，最后被 1200s 硬杀，整轮（含两次 MinerU + 8 次 OCR 费用）白跑。

        所以：预算在**这一步**算好往下传（下面的 pipeline 不知道也不该知道任务阀值），
        心跳封成**无参回调**往下传（线程池不知道也不该知道 job 主键）。两者都是“参数/回调
        下传”而不是“把 job 存到共享线程里”——后者在同一 worker 跑多个任务时会互相污染。
        """
        from . import two_stage

        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        self._begin_stage(job, PdfSplitStage.EXTRACT)

        # 预算从阶段开始就计时（含建目录/写库这些小题大做的开销），不在 OCR 前才起表：
        # 否则“阶段开头就慢”的那几分钟会被当成可用预算。
        stage_budget = two_stage.extract_stage_budget()

        def on_progress(resolved_pages: int, total_pages: int) -> None:
            self.touch_heartbeat(job_id=job.id)
            self._update_progress(job_id=job.id, resolved_pages=resolved_pages, total_pages=total_pages)

        def on_heartbeat() -> None:
            # 只刷心跳，不动进度：逐页 OCR 与图片补救都是“没进度可报但可能在跑”的段落。
            self.touch_heartbeat(job_id=job.id)

        def is_cancelled() -> bool:
            job.refresh_from_db(fields=["cancel_requested"])
            return bool(job.cancel_requested)

        pages, summary = extract_pages(
            storage.source_pdf_path,
            template_key=job.template_key,
            ocr_profile=job.ocr_profile,
            layout_mode=getattr(job, "layout_mode", "fast_text"),
            # 取字用哪个平台：仍然**只看 cloud_backend**（单选 + 容灾语义）。
            # 交叉比对是另一件事，读的是 `dual_engines`，见下一行之后的
            # `_run_dual_engine_if_selected`——两条路径互不干扰。
            cloud_backend=getattr(job, "cloud_backend", "auto"),
            on_progress=on_progress,
            is_cancelled=is_cancelled,
            ocr_handler=self._ocr_handler,
            heartbeat=on_heartbeat,
            budget=stage_budget,
        )
        if stage_budget.skipped_count:
            # 阶段级别的最终账：单页日志早就在 `ocr_handler` 里打过，但“这次到底降级了几页”
            # 只有汇总后才看得出来（而这直接影响分段边界）。
            logger.warning(
                "pdf_split_extract_budget_degraded",
                extra={
                    "job_id": str(job.id),
                    "skipped_pages": stage_budget.skipped_count,
                    "budget_seconds": round(stage_budget.total_seconds, 1),
                    "remaining_seconds": round(stage_budget.remaining_seconds(), 1),
                },
            )
        # 双引擎**不在这里跑**：它要把整本再解析一遍（十几分钟），而本阶段已经
        # 用掉大半 600s 预算。留在同一次任务里会被 Q_CLUSTER timeout 硬杀进程，
        # 连 finally 都不执行（详见 two_stage.submit_cross_check_stage）。
        # 它在 cross_check_stage 里作为独立任务跑，那里有全新预算。
        return pages, summary

    def cross_check_stage(self, job: PdfSplitJob, pdf_path: Path | None = None) -> dict[str, Any]:
        """交叉比对阶段：两个引擎各解析一遍整本，产出引擎分歧。

        为什么只剩**一个调用点**：以前它是 `extract_stage` 里的一行内联调用，
        结果 164 页双引擎把整个任务拖超 600s，Django-Q 直接把 worker 杀了，
        DB 里只留一个 `stage=cross_check` 的僵尸（无任何 django_q_task 记录）。
        现在拆成独立任务，本阶段拥有自己的 600s。

        门禁只看 `job.dual_engines`：引擎不足 2 个时 tasks 层不会提交这个任务，
        但这里仍再判一次——任务可能被看门狗重排、或被人工重提。

        为什么分歧要**另跑一遍**而不是复用取字阶段的云端结果：主路径逐页解析
        并且只保留最终采纳的那一个平台的文本，堆不成「同一批页、两个引擎、各自
        全文」的对照矩阵，而分歧判定需要的就是这个矩阵（还要 block 坐标，主路径
        同样不保留）。代价是勾了双引擎就多付一次云端费用。

        为什么失败不抛异常：分歧是**附加信息**，取字早已成功且已落盘。让一个
        可选的交叉校验把整份卷宗判失败，是拿主路径给辅助功能陪葬。失败就把
        空分歧交给分段阶段，任务照常往下走。

        本阶段还顺带做**转正页回填**（`rotated_backfill`）：它是全仓唯一同时拿得到
        `pages`（extract 阶段落的 pages.json）与 `DualEngineOutcome` 的地方，所以
        VL 回填必须在这里下手，否则 VL 认对的那些页永远进不了正文。
        """
        engines = parse_dual_engines(getattr(job, "dual_engines", ""))
        if len(engines) < 2:
            return {}

        storage = PdfSplitStorage(job.id)
        # pdf_path 只在测试里显式传入；生产路径总是走任务目录下那份源文件副本
        # （任务目录自带 source/original.pdf，不依赖附件是否还在）。
        if pdf_path is None:
            pdf_path = storage.source_pdf_path
        self._enter_cross_check(job)
        try:
            factories, unavailable = plan_dual_engine_factories(engines)
            try:
                # 心跳线程覆盖整个阻塞段。它不能阻止 worker 超时（那要杀进程），
                # 但能让看门狗分清楚「还活着」与「真死了」，避免误重排。
                with periodic_heartbeat(job.id):
                    # 判定开不开是**任务级**选择（用户在前端勾/不勾）：传下去，
                    # 由 run_dual_engine 与部署级能力总闸合成有效值。
                    # 缺属性时 None = 未表态 → 跟随部署侧（与旧行为一致）。
                    outcome = run_dual_engine(
                        pdf_path,
                        engine_factories=factories,
                        judge_enabled=getattr(job, "ocr_judge_enabled", None),
                    )
            except Exception:
                logger.exception("pdf_split_dual_engine_failed", extra={"pdf_path": pdf_path.as_posix()})
                return {}
        finally:
            self._exit_cross_check(job)

        summary = dict(outcome.summary)
        dual = dict(summary.get("dual_engine") or {})
        dual["selected"] = engines
        dual["unavailable"] = unavailable
        summary["dual_engine"] = dual
        summary["rotated_backfill"] = self._apply_rotated_page_backfill(job=job, storage=storage, outcome=outcome)
        return summary

    def segment_stage(self, job: PdfSplitJob) -> None:
        """两阶段任务链 ②：从 pages.json 读回取字结果，只做分段与落库。

        本阶段额外跑一次**表格几何 pass**（DESIGN §5 方案 A）：段阶段是“唯一同时拥有
        ``pages``、``pdf_path`` 与上游产物目录的地方”，几何必须在这里落盘，三个
        ``build_segments_markdown`` 调用点才能共享同一份——否则会出现
        “确认分段后点格子又画错”。
        """
        from . import table_geometry_switches, two_stage
        from .pipeline import PageDescriptor, resolve_segment_strategy

        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        self._begin_stage(job, PdfSplitStage.SEGMENT)

        raw_pages = two_stage.load_pages(storage)
        if not raw_pages:
            raise ValueError("取字结果缺失（pages.json 不存在或为空），需重跑取字阶段")

        pages = [PageDescriptor(**item) for item in raw_pages]
        # LLM 分段在 164 页上是 4-8 分钟、全程无回调，必须靠后台心跳撑着，
        # 否则 `_begin_stage` 写的那一次心跳之后再无声息，看门狗会来杀。
        with periodic_heartbeat(job.id):
            drafts, segment_summary = detect_segments_with_fallback(
                pages,
                template_key=job.template_key,
                # 批级成果落在 job 目录里：worker 被杀后重跑接着已完成的批跑，
                # 不再为同一批 LLM 付第二次钱。
                checkpoint_path=storage.analysis_dir / "segment_checkpoint.json",
                # 策略以**任务级选择**为准（job.segment_strategy）；只有它为空时才回落到
                # SystemConfig 的 PDF_SPLIT_SEGMENT_STRATEGY，最后才是 batch。
                # 整本路径失败会自动降级回分批，所以这里不必先探测可用性。
                strategy=resolve_segment_strategy(getattr(job, "segment_strategy", "")),
            )

        # 跨页一致性校对与段级质量标记：与 analyze_pdf 走同一条路径（同一份判据、
        # 同一份文案），避免「单任务入口有、两阶段入口没有」的劈叉。
        bbox_backend = self._bbox_backend(job_id=job.id, storage=storage, pages=pages)
        table_geometry_payload, geometry, geometry_summary = self._ensure_table_geometry(
            job=job, storage=storage, pages=pages, bbox_backend=bbox_backend
        )
        inconsistencies = detect_inconsistencies(pages)
        segments_md = attach_page_quality_flags(
            attach_quality_flags_to_markdown(
                build_segments_markdown(
                    drafts,
                    pages,
                    bbox_backend=bbox_backend,
                    table_geometry=geometry,
                    # 回滚开关：几何缺失时是否退回旧均分（默认关 = 整表框）
                    legacy_uniform=table_geometry_switches.uniform_fallback_enabled(),
                ),
                inconsistencies,
            ),
            qualities_by_page(pages),
        )
        outcome = PdfAnalysisOutcome(
            pages=pages,
            drafts=drafts,
            segments_md=segments_md,
            # 产物随 outcome 交给 `_persist_analysis` 落盘：它写在 pages.json **之后**，
            # 顺序反过来的话产物会比 pages.json 旧，下次分段重跑就会判“过期”重付费。
            table_geometry=table_geometry_payload,
            summary={
                **segment_summary,
                # 取字阶段算好并落盘的页面质量画像。
                #
                # ⚠️ 必须嵌一层 `page_quality` 键，**不能 `**` 展开**：
                # load_page_quality 返回的是 {graphic_pages, sparse_pages, blank_pages,
                # details, doc_hints, doc_missing}，直接展开会把这些键平铺到 summary
                # 顶层，而前端读的是 `summary.page_quality.graphic_pages` —— 结果就是
                # 「后端算出来了、页面上什么也没有」。这个坑真踩过（v27.16.8 首跑）。
                "page_quality": two_stage.load_page_quality(storage),
                "inconsistencies": pick_top_inconsistencies(inconsistencies),
                "inconsistency_total": len(inconsistencies),
                # 双引擎分歧（取字阶段算好并落盘）。键名固定为 engine_disagreements /
                # engine_disagree_summary，前端 draft.ts 按这两个名字消费。
                # 没选多引擎时两个键是空列表/空计数——形状固定，前端不用判 None。
                **_dual_engine_summary(two_stage.load_engine_disagreements(storage)),
                # 表格几何的观测块：整表框的 reason 都在这里计数，静默降级不做
                "table_geometry": geometry_summary,
            },
        )
        # merge_summary=False：本阶段只产出分段相关字段，不能把取字阶段写下的
        # ocr_profile / layout_mode / material_kind 抹掉（summary 只增不删）。
        self._persist_analysis(job=job, storage=storage, outcome=outcome, merge_summary=False)
        PdfSplitJob.objects.filter(id=job.id).update(stage=PdfSplitStage.DONE)

    def _ensure_table_geometry(
        self, *, job: PdfSplitJob, storage: PdfSplitStorage, pages: list[PageDescriptor], bbox_backend: str
    ) -> tuple[dict[str, Any], dict[int, dict[int, Any]], dict[str, Any]]:
        """几何产物：**缺/过期才量** → 返回 (原始产物, 定位映射, summary 区块)。

        “缺/过期才量”是钱的问题：产物即缓存，分段重跑命中就不重复付费。
        开关关闭时不调用引擎也不产产物（回滚开关决定定位退到均分还是整表框）。

        本方法**不落盘**：产物由 ``_persist_analysis`` 在写完 ``pages.json`` 之后写，
        否则产物会永远比 pages.json 旧，过期判定每次都成立（等于没有缓存）。
        """
        from . import table_geometry_pass, table_geometry_switches, two_stage

        enabled, _legacy_uniform = table_geometry_switches.switches()
        if not enabled:
            logger.info("pdf_split_table_geometry_disabled", extra={"job_id": str(job.id)})
            return {}, {}, table_geometry_pass.summary_block({}, enabled=False)

        if two_stage.table_geometry_is_stale(storage):
            artifact = table_geometry_pass.build_geometry_artifact(
                pages,
                pdf_path=storage.source_pdf_path,
                engine=table_geometry_pass.PaddleTableGeometryEngine(),
                bbox_backend=bbox_backend,
                # L2 本地线条兜底（默认关）：开关只在这里读，pass 层收布尔值
                local_lines_enabled=table_geometry_switches.local_lines_enabled(),
            )
            logger.info(
                "pdf_split_table_geometry_measured",
                extra={"job_id": str(job.id), **table_geometry_pass.summary_block(artifact, enabled=True)},
            )
        else:
            artifact = two_stage.load_table_geometry_payload(storage)
        return (
            artifact,
            table_geometry_pass.geometries_by_page_block(artifact),
            table_geometry_pass.summary_block(artifact, enabled=True),
        )

    def _apply_rotated_page_backfill(
        self, *, job: PdfSplitJob, storage: PdfSplitStorage, outcome: Any
    ) -> dict[str, Any]:
        """转正页回填：**全仓唯一的调用点**（判据与规则全在 `rotated_backfill`）。

        双引擎跑在 cross_check 阶段，而 pages 在 extract 阶段就已落盘——本阶段是唯一
        同时拿得到两者（又不必重新付一次云端费）的位置。回填结果写回 pages.json，
        分段阶段与几何 pass 读到的就是修正后的正文。

        整个回填包在 try 里的理由：它是**附加修正**，一个回填 bug 不能把已经付费的
        双引擎分歧一起丢掉（那些分歧还没落盘）。失败只记 warning 并在 summary 里留
        ``error``，任务照常往下走，正文保持原样（乱码但不丢页）。

        异常类型只收具体的几个：读/写盘 ``OSError``、raw dict → dataclass 的
        ``TypeError`` / ``KeyError``、页号脏值 ``ValueError``。
        """
        from . import rotated_backfill, table_geometry_switches, two_stage

        enabled = table_geometry_switches.rotated_page_use_vl_text_enabled()
        # 先给一个空判决：万一后面的写盘炸了，summary 里也要如实写出「已经改了哪几页」，
        # 不能因为最后一步失败就把前面的替换说成没发生。
        result = rotated_backfill.RotatedBackfillResult()
        try:
            raw_pages = two_stage.load_pages(storage)
            if not raw_pages:
                # 取字产物缺失（重排/人工重提的异常路径）：没有 pages 可回填，如实记一条
                logger.warning("pdf_split_rotated_backfill_pages_missing", extra={"job_id": str(job.id)})
                return rotated_backfill.summary_block(rotated_backfill.RotatedBackfillResult(), enabled=enabled)

            view = rotated_backfill.vl_page_view(outcome)
            pages = rotated_backfill.pages_from_raw(raw_pages)
            chars_before = {page.page_no: len(str(page.text or "")) for page in pages}
            result = rotated_backfill.apply_rotated_backfill(
                pages,
                angles=view.angles,
                vl_text=view.text,
                vl_blocks=view.blocks,
                enabled=enabled,
                template_key=str(getattr(job, "template_key", "") or ""),
            )
            if result.applied:
                self._write_back_pages(storage=storage, raw_pages=raw_pages, pages=pages, applied=result.applied)
            storage.write_json(
                storage.rotated_backfill_json_path,
                rotated_backfill.backfill_report(
                    result,
                    angles=view.angles,
                    chars_before=chars_before,
                    pages=pages,
                    enabled=enabled,
                    written_at=timezone.now().isoformat(),
                ),
            )
        except (OSError, TypeError, ValueError, KeyError) as exc:
            logger.warning(
                "pdf_split_rotated_backfill_failed",
                exc_info=True,
                extra={"job_id": str(job.id), "error": type(exc).__name__},
            )
            return rotated_backfill.summary_block(result, enabled=enabled, error=type(exc).__name__)
        return rotated_backfill.summary_block(result, enabled=enabled)

    def _write_back_pages(
        self,
        *,
        storage: PdfSplitStorage,
        raw_pages: list[dict[str, Any]],
        pages: list[PageDescriptor],
        applied: tuple[int, ...],
    ) -> None:
        """把回填结果写回 pages.json：先备份，再改 raw dict，最后整体回写。

        ## 为什么改 raw dict 而不是重新 ``asdict(pages)``

        pages.json 是**跨阶段契约**（extract 写、segment 读）。重新序列化整份会把别的
        版本写进去的、本版本不认识的键全部丢掉——而那些键可能正是下游要的。所以只改
        本次真正动过的页的那几个字段（``rotated_backfill.BACKFILL_FIELDS``）。

        ## 备份

        覆盖前把旧文件复制成 ``pages.json.bak-<ts>``：回填是律师看不见的正文替换，
        出问题时必须能一眼看到「换之前是什么」。

        ## ⚠️ 前提：本函数只能在 segment 阶段**之前**跑

        ``two_stage.table_geometry_is_stale()`` 用 mtime 判定几何产物是否过期。
        cross_check 在 segment 之前，那时几何产物还不存在，这次 mtime 更新无害；
        **若将来有人把 cross_check 排到 segment 之后**，几何产物就会被判成 stale
        重量一次（多花一笔云端钱）。
        """
        from . import rotated_backfill

        if storage.pages_json_path.exists():
            backup_name = f"{storage.pages_json_path.name}.bak-{timezone.now().strftime('%Y%m%dT%H%M%S')}"
            storage.save_overwrite(
                storage.pages_json_path.with_name(backup_name), ContentFile(storage.pages_json_path.read_bytes())
            )

        wanted = set(applied)
        by_page = {page.page_no: page for page in pages if page.page_no in wanted}
        for item in raw_pages:
            page = by_page.get(int(item.get("page_no") or 0))
            if page is None:
                continue
            for field_name in rotated_backfill.BACKFILL_FIELDS:
                item[field_name] = getattr(page, field_name)
        storage.write_json(storage.pages_json_path, raw_pages)

    def _bbox_backend(self, *, job_id: Any, storage: PdfSplitStorage, pages: list[PageDescriptor]) -> str:
        """两阶段任务的坐标系来源：读**实际引擎**，不是任务上的平台偏好。

        ``job.cloud_backend`` 可能是 ``auto``（容灾偏好，不是平台名），
        ``resolve_bbox_unit("auto")`` 返回 unknown → ``build_positioned_blocks``
        直接返回 []。这就是「两阶段 + auto 的任务绿框恒空」的根因，而单任务入口
        用的是取字 summary 里的实际 ``ocr_provider``——两个入口必须同一口径。

        取字 summary 拿不到时（旧任务没有这份产物）按页记录的取字来源推断，
        并明确记一条 warning：推断出来的坐标系不如取字阶段自己报的可信。
        **不退回 "auto"**——那等于把恒空的 bug 留着。
        """
        from . import two_stage

        # 产物缺失/损坏时 load_extract_summary 自己回空表，这里只需处理「空」这一种情况
        provider = str(two_stage.load_extract_summary(storage).get("ocr_provider") or "")
        if provider and provider != "auto":
            return provider

        inferred = _provider_from_pages(pages)
        if inferred:
            logger.warning(
                "pdf_split_bbox_backend_inferred",
                extra={"job_id": str(job_id), "provider": inferred, "pages": len(pages)},
            )
            return inferred
        logger.warning(
            "pdf_split_bbox_backend_unknown",
            extra={"job_id": str(job_id), "pages": len(pages), "summary_provider": provider},
        )
        return ""

    def _enter_cross_check(self, job: PdfSplitJob) -> None:
        """进入交叉比对：确认阶段名、写心跳、把进度压回 90。

        stage 通常已由 `two_stage.advance_to_cross_check_stage` 写好，这里再写一次
        是幂等的——任务可能被看门狗重排或被人工重提，那些路径下不会先走推进函数。

        为什么 progress 要**回退**到 90（取字那边已经写满 100）：双引擎还没跑，
        停在 100 就等于骗人说「快完了」。90→99 这一段留给比对本身，律师能看出
        确实还在动。

        为什么 processed_pages **不回退**：那是取字的真实完成量（164/164），
        回退会让前端以为取字还没做完，也会污染看门狗/自救重排对「有没有成果」
        的判据。
        """
        now = timezone.now()
        PdfSplitJob.objects.filter(id=job.id).update(
            stage=PdfSplitStage.CROSS_CHECK,
            progress=90,
            heartbeat_at=now,
            updated_at=now,
        )

    def _exit_cross_check(self, job: PdfSplitJob) -> None:
        """交叉比对收工：进度推到 99、刷一次心跳。

        **刻意不改 stage**：交叉比对现在是一个独立的阶段任务，它的下一步
        （`two_stage.advance_to_segment_stage`）会把 stage 写成 segment。
        这里如果像以前那样把 stage 写回 extract，任务链的每一个推进点都会
        先把阶段倒退一次，前端会看到阶段来回跳。

        进度留 99 而不是 100：后面的分段还没开始，报 100 就是谎报。
        """
        now = timezone.now()
        PdfSplitJob.objects.filter(id=job.id).update(
            progress=99,
            heartbeat_at=now,
            updated_at=now,
        )

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
        """后台导出任务：把整包写到 ``exports/split_result.zip``（供旧调用方直接取文件）。

        包内现在也带 md（与 ``build_download_zip`` 用同一套条目构造），否则
        「后台导出出来的包」与「端点下载的包」内容不一致——同一份卷宗两个下载
        入口给不一样的东西，用户无法判断哪个是完整的。

        进度与取消保留在原位：整包渲 93 页虽然只需秒级，但几十段的导出仍可能
        放在慢盘上，律师点「取消」必须能停。
        """
        storage = PdfSplitStorage(job.id)
        storage.ensure_dirs()
        segments = self._download_segments(job=job, segment_ids=None)
        if not segments:
            # 后台任务没有「空响应」这条路：它就是失败，任务会被标 failed 并写明原因，
            # 不能像下载端点那样静默回 404。
            raise ValueError("没有可导出的片段")

        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.EXPORTING,
            progress=0,
            error_message="",
        )

        entries: list[tuple[str, bytes]] = []
        markdown_by_order = load_segment_markdown_map(storage.segments_md_path)
        with fitz.open(storage.source_pdf_path) as source_doc:
            total = len(segments)
            seen_names: set[str] = set()
            ordinals = self._ordinals_in_job(job)
            for index, segment in enumerate(segments, start=1):
                job.refresh_from_db(fields=["cancel_requested"])
                if job.cancel_requested:
                    PdfSplitJob.objects.filter(id=job.id).update(
                        status=PdfSplitJobStatus.CANCELLED,
                        finished_at=timezone.now(),
                    )
                    return

                entries.extend(
                    self._segment_zip_entries(
                        source_doc,
                        segment,
                        seq=ordinals.get(segment.id, index),
                        markdown_by_order=markdown_by_order,
                        seen_names=seen_names,
                    )
                )

                progress = int(index * 100 / total)
                PdfSplitJob.objects.filter(id=job.id).update(progress=progress)

        storage.save_overwrite(storage.export_zip_path, ContentFile(_zip_bytes(entries)))

    # ==================================================================
    # 下载产物（单段 pdf / 单段 md / 整包与多选 zip）
    # ==================================================================

    def build_download_pdf(self, job: PdfSplitJob, segment_id: int, *, rotations: str = "") -> tuple[bytes, str]:
        """单段 PDF：返回 ``(pdf 字节, 安全文件名)``。

        文件名只由「数据库里的段名 → sanitize → 本模块重生扩展名」构成，
        不接受任何客户端拼串（否则 ``../`` 与引号就能穿进 Content-Disposition）。
        """
        segment = self._get_segment(job=job, segment_id=segment_id)
        storage = PdfSplitStorage(job.id)
        if not storage.source_pdf_path.exists():
            raise NotFoundError(
                message="原始 PDF 不存在，无法切出该分段",
                code="PDF_SPLIT_SOURCE_MISSING",
                errors={"segment_id": segment_id},
            )
        with fitz.open(storage.source_pdf_path) as source_doc:
            # 人工转正先烧进页对象再切：insert_pdf 复制页对象，/Rotate 跟着走
            apply_page_rotations(source_doc, parse_page_rotations(rotations))
            pdf_bytes = export_segment_pdf(source_doc, segment.page_start, segment.page_end)
        return pdf_bytes, f"{self._segment_stem(segment)}.pdf"

    def build_download_markdown(self, job: PdfSplitJob, segment_id: int) -> tuple[str, str]:
        """单段 Markdown：返回 ``(markdown 文本, 安全文件名)``。

        正文取 ``segments_md.json`` 里那一段——即律师在界面上看到的 ``content_md``
        本人，不是现场重算的近似物。该段没有 md 产物（旧任务 / 该段没取到字）时
        404 而不是回空文件：空 md 看起来像「下载成功但内容是空的」，比明确报错
        更难排查。
        """
        segment = self._get_segment(job=job, segment_id=segment_id)
        markdown_by_order = load_segment_markdown_map(PdfSplitStorage(job.id).segments_md_path)
        markdown = markdown_by_order.get(segment.order) or ""
        if not markdown.strip():
            raise NotFoundError(
                message="该分段没有 Markdown 产物",
                code="PDF_SPLIT_SEGMENT_MD_NOT_FOUND",
                errors={"segment_id": segment_id, "order": segment.order},
            )
        return markdown, f"{self._segment_stem(segment)}.md"

    def build_download_zip(
        self,
        job: PdfSplitJob,
        *,
        segment_ids: list[int] | None = None,
        rotations: str = "",
    ) -> tuple[bytes, str] | None:
        """整包 / 多选打包：返回 ``(zip 字节, zip 文件名)``，包内**平铺**且每段配同名 md。

        ``segment_ids`` 为 ``None`` 时是整包（与既有 ``/download`` 语义一致，只是
        包里多了 md）；给值时只渲选中的段——未选中的段**不渲**，否则多选下载的耗时
        与整包一样，勾 3 段要等 93 页。

        返回 ``None`` 而不是抛异常表示「没有可打包的段」：旧 ``/download`` 对
        「产物缺失」的契约是 **404 + 空响应体**（不能把半个包发给律师），API 层据此
        直接回空 404 即可，不必为它写 try/except。
        """
        segments = self._download_segments(job=job, segment_ids=segment_ids)
        if not segments:
            return None
        storage = PdfSplitStorage(job.id)
        if not storage.source_pdf_path.exists():
            return self._fallback_archive(job=job, storage=storage, segment_ids=segment_ids)

        markdown_by_order = load_segment_markdown_map(storage.segments_md_path)
        ordinals = self._ordinals_in_job(job)
        entries: list[tuple[str, bytes]] = []
        seen_names: set[str] = set()
        with fitz.open(storage.source_pdf_path) as source_doc:
            # 包内所有段共用这一份源文档：角度一次 apply 到位（页级属性，与段无关）
            apply_page_rotations(source_doc, parse_page_rotations(rotations))
            for segment in segments:
                entries.extend(
                    self._segment_zip_entries(
                        source_doc,
                        segment,
                        seq=ordinals.get(segment.id, 1),
                        markdown_by_order=markdown_by_order,
                        seen_names=seen_names,
                    )
                )
        return _zip_bytes(entries), self._zip_filename(segment_ids)

    def _fallback_archive(
        self, *, job: PdfSplitJob, storage: PdfSplitStorage, segment_ids: list[int] | None
    ) -> tuple[bytes, str]:
        """源 PDF 已不在时的降级：整包请求回历史整包，多选请求明确报错。

        为什么整包可以回旧包：``/download`` 以前就是「文件在就给文件」，源 PDF 被
        清理后旧整包仍在的存量任务是真实存在的；把它们从 200 变成 404 是回归。
        但旧包可能没有 md，所以记一条 warning——这是唯一会出现「pdf 配不上 md」
        的入口，日志里必须能查到原因。

        多选做不了同样的降级：历史整包是**整包**，拿它当「只选中几段」返回等于
        把没勾的材料也塞给律师，比报错更糟。
        """
        if segment_ids is None and storage.export_zip_path.exists():
            logger.warning(
                "pdf_split_download_source_missing",
                extra={"job_id": str(job.id), "fallback": "persisted_zip"},
            )
            return storage.export_zip_path.read_bytes(), self._zip_filename(None)
        raise NotFoundError(
            message="原始 PDF 不存在，无法重新打包",
            code="PDF_SPLIT_SOURCE_MISSING",
            errors={"job_id": str(job.id)},
        )

    def _zip_filename(self, segment_ids: list[int] | None) -> str:
        """zip 的下载名：整包沿用旧名 ``split_result.zip``，多选另取一个。

        不改整包文件名是为了向后兼容（脚本/旧前端按名字认产物）；多选单独命名
        则让律师在下载目录里能一眼分辨「这是我勾的几段」还是「整包」。
        """
        return "split_result.zip" if segment_ids is None else "split_result_selected.zip"

    def _download_segments(self, *, job: PdfSplitJob, segment_ids: list[int] | None) -> list[PdfSplitSegment]:
        """本次要打包的段（按卷宗顺序）。

        ``ids`` 校验规则：每个 id 都必须是**该任务**的段主键，有一个不合法就整体
        400 并列出是哪些——不静默跳过。律师勾了 12 段、包里只有 10 段时，他无法
        从界面上看出少了哪两段；整包悄悄缺页是这类卷宗工具最坏的失败模式。
        """
        segments = list(job.segments.order_by("order", "id"))
        if segment_ids is None:
            return segments
        # 显式选中但一段也取不到（任务没有段 / ids 是空表）→ 回空表，由调用方决定
        # 怎么反应：下载端点回空 404（旧契约），后台导出任务报失败。同一个「没东西
        # 可打」在两个入口的正确反应不同。
        if not segments:
            return []

        by_id = {segment.id: segment for segment in segments}
        unknown = [segment_id for segment_id in segment_ids if segment_id not in by_id]
        if unknown:
            raise ValidationException(
                message=f"以下分段不属于该任务：{', '.join(str(item) for item in unknown)}",
                errors={"ids": unknown},
            )
        # dict.fromkeys 去重：前端可能把同一段拼接进 ids 两次，同一份材料在包里
        # 出现两遍只会被当成「重复上传」；再按 order 排序，包内顺序恒等于卷宗顺序。
        selected = [by_id[segment_id] for segment_id in dict.fromkeys(segment_ids)]
        return sorted(selected, key=lambda segment: (int(segment.order or 0), int(segment.id or 0)))

    def _get_segment(self, *, job: PdfSplitJob, segment_id: int) -> PdfSplitSegment:
        """取本任务的某一段；不存在（含其他任务的段）一律 404。

        走 ``job.segments`` 而不是 ``PdfSplitSegment.objects``：段归属由任务关系定，
        拿别人的段主键来试本来就该按「不存在」处理，不该泄露它是否存在。
        """
        segment = job.segments.filter(id=segment_id).first()
        if segment is None:
            raise NotFoundError(
                message="分段不存在",
                code="PDF_SPLIT_SEGMENT_NOT_FOUND",
                errors={"segment_id": segment_id},
            )
        return segment

    def _ordinals_in_job(self, job: PdfSplitJob) -> dict[int, int]:
        """段主键 → 该段在**整卷**里的 1 起序号（与是否多选无关）。

        为什么不直接用 ``segment.order``：它的起始值取决于写入侧（实测真实任务从 0
        起），补零后包内会出现 ``00_`` —— 律师看到会以为编号错乱。也不按「包内第几个」
        编号：勾了第 1、3 段时，``01_起诉状`` / ``03_证据目录`` 比 ``01_`` / ``02_``
        多保住一个信息——这两份在整卷里是第几段。卷宗顺序由排序保证，与下载顺序无关。
        """
        ordered = job.segments.order_by("order", "id").values_list("id", flat=True)
        return {segment_id: index for index, segment_id in enumerate(ordered, start=1)}

    def _segment_zip_entries(
        self,
        source_doc: fitz.Document,
        segment: PdfSplitSegment,
        *,
        seq: int,
        markdown_by_order: dict[int, str],
        seen_names: set[str],
    ) -> list[tuple[str, bytes]]:
        """一段 → zip 条目列表（``[pdf]`` 或 ``[pdf, md]``）。

        缺 md 时降级为只放 pdf + 一条 warning，绝不因此让整包失败：md 是这次
        新加的产物，旧任务/未取到字的段本来就没有；因为一个副产物让律师拿不到
        已经切好的 pdf，是把主产物赔给附属产物。
        """
        # 前缀取**本次导出集合内**的 1 起序号，不取 ``segment.order``：后者的起始值
        # 取决于写入侧（实测真实任务从 0 起），直接拿来补零会让包内出现 ``00_`` 前缀，
        # 律师看到会以为是编号错乱。这个名字只用于包内排序，与卷宗顺序由入参保证。
        pdf_name = deduplicate_filename(f"{seq:02d}_{self._segment_stem(segment)}.pdf", seen_names)
        entries: list[tuple[str, bytes]] = [
            (pdf_name, export_segment_pdf(source_doc, segment.page_start, segment.page_end))
        ]
        markdown = markdown_by_order.get(segment.order) or ""
        if not markdown.strip():
            logger.warning(
                "pdf_split_export_markdown_missing",
                extra={"job_id": str(segment.job_id), "segment_id": segment.id, "order": segment.order},
            )
            return entries
        # md 名跟 pdf 名同 stem（含去重后的 ``_2`` 尾巴）：一个 pdf 配一个同名 md
        # 是这次需求的核心，两边各算一次名字迟早会劈叉。
        entries.append((Path(pdf_name).with_suffix(".md").name, markdown.encode("utf-8")))
        return entries

    def _segment_stem(self, segment: PdfSplitSegment) -> str:
        """段的展示名 stem（去扩展名、已安全化）。

        名字只来自数据库字段 + ``sanitize_upload_filename``，任何客户端输入都不参与
        ——pdf/md 的下载名与 zip 条目名都从这里出。
        """
        safe = sanitize_upload_filename(segment.filename or get_default_filename(segment.segment_type))
        stem = _SEGMENT_SUFFIX_RE.sub("", safe).strip(" .")
        return stem or "片段"

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
        merge_summary: bool = True,
    ) -> None:  # pragma: no cover
        """把 pipeline 产物落库落盘：pages / segments / segments_md + 任务摘要（含取字与分段的观测字段）。

        ``merge_summary``：整条流水线跑完（analyze_job）时 True，outcome.summary 就是完整快照；
        两阶段链路的分段阶段只产出分段相关字段，必须 False——否则会把取字阶段写入并落库的
        ``ocr_profile`` / ``layout_mode`` / ``material_kind`` 等字段从 summary 里抹掉。
        summary 只增不删，前端可能还有旧消费方在读这些键。
        """
        from . import two_stage

        storage.write_json(storage.pages_json_path, [asdict(item) for item in outcome.pages])
        storage.write_json(storage.segments_json_path, [asdict(item) for item in outcome.drafts])
        storage.write_json(storage.segments_md_path, outcome.segments_md)
        # 几何产物：单任务入口（analyze_pdf）把量好的产物随 outcome 带回来，由这里落盘。
        # 不落盘 = “用户确认分段后重建”那条路径拿不到几何 → 格子又画成整表框。
        table_geometry_payload = getattr(outcome, "table_geometry", None)
        if isinstance(table_geometry_payload, dict) and table_geometry_payload:
            two_stage.save_table_geometry(storage, table_geometry_payload)
            logger.info(
                "pdf_split_table_geometry_saved",
                extra={
                    "job_id": str(job.id),
                    "pages": len(table_geometry_payload.get("pages") or {}),
                    "summary": table_geometry_payload.get("summary") or {},
                },
            )

        # 同名去重：LLM 常把同一类材料切成多段并给同一个名字
        # （实测一份 164 页卷宗里出现两个「居民户口簿.pdf」、两个
        # 「个人房产抵押贷款合同.pdf」）。它们确实不是重复——分别是不同
        # 当事人的户口簿、合同正本与副本——但文件名一样，归案后分不清。
        #
        # 以前只在**导出**时调 deduplicate_filename，数据库里仍是重名；
        # 而前端分段列表、归案建材料、Copilot 读的都是库里的名字，所以
        # 必须在这里就消歧。
        seen_names: set[str] = set()
        deduped = []
        for item in outcome.drafts:
            name = item.filename
            if not name.lower().endswith(".pdf"):
                name = f"{name}.pdf"
            deduped.append((item, deduplicate_filename(name, seen_names)))

        # S16-13（2026-11-23 二轮审计）：原来「先 delete 再 bulk_create」不在事务里，
        # 中途失败/进程被杀 → 该任务的分段全部丢失（要重跑整份 OCR/分段，几十元）。
        # 两步放进同一事务：要么整批换新，要么保持原样。
        rows = [
            PdfSplitSegment(
                job=job,
                order=item.order,
                page_start=item.page_start,
                page_end=item.page_end,
                segment_type=item.segment_type,
                filename=name,
                confidence=item.confidence,
                source_method=item.source_method,
                review_flag=item.review_flag,
            )
            for item, name in deduped
        ]
        with transaction.atomic():
            PdfSplitSegment.objects.filter(job=job).delete()
            PdfSplitSegment.objects.bulk_create(rows)

        # 分段阶段（merge_summary=False）要合入取字阶段已写的键，逐页质量 / 取字参数都靠它保留
        previous_summary = {} if merge_summary else dict(job.summary_payload or {})
        PdfSplitJob.objects.filter(id=job.id).update(
            status=PdfSplitJobStatus.REVIEW_REQUIRED,
            progress=100,
            total_pages=len(outcome.pages),
            processed_pages=len(outcome.pages),
            current_page=len(outcome.pages),
            summary_payload={
                **previous_summary,
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

        **实现在 `services/heartbeat.touch_heartbeat`，这里只转调**：同一件事以前有两份
        拷贝（本方法与 heartbeat 模块各一份），逐页 OCR 的线程池又需要第三个入口时，
        三份实现必然漏改其中一份——而心跳一旦和看门狗的判据不一致，就是“在跑的任务被
        判死重排”。保留本方法只为守住 `PdfSplitService` 的公开 API。
        """
        _touch_heartbeat_row(job_id=job_id)


# 版面标题提取已下沉 split_models（pipeline / service 共用）；此处保留旧名再导出，
# 既有测试与潜在调用方仍从本模块引用
from .split_models import extract_layout_title as _extract_layout_title
