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
    parse_dual_engines,
)
from apps.pdf_splitting.services.heartbeat import periodic_heartbeat
from apps.pdf_splitting.services.heartbeat import touch_heartbeat as _touch_heartbeat_row
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.pdf_splitting.services.template_registry import get_default_filename

from .consistency_summary import attach_quality_flags_to_markdown, detect_inconsistencies, pick_top_inconsistencies
from .dual_engine_runner import plan_dual_engine_factories, run_dual_engine
from .export_utils import ExportUtils, deduplicate_filename, export_segment_pdf
from .markdown_builder import build_segments_markdown
from .ocr_handler import OCRHandler, cloud_backend_of_method
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
        """
        engines = parse_dual_engines(getattr(job, "dual_engines", ""))
        if len(engines) < 2:
            return {}

        # pdf_path 只在测试里显式传入；生产路径总是走任务目录下那份源文件副本
        # （任务目录自带 source/original.pdf，不依赖附件是否还在）。
        if pdf_path is None:
            pdf_path = PdfSplitStorage(job.id).source_pdf_path
        self._enter_cross_check(job)
        try:
            factories, unavailable = plan_dual_engine_factories(engines)
            try:
                # 心跳线程覆盖整个阻塞段。它不能阻止 worker 超时（那要杀进程），
                # 但能让看门狗分清楚「还活着」与「真死了」，避免误重排。
                with periodic_heartbeat(job.id):
                    outcome = run_dual_engine(pdf_path, engine_factories=factories)
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
        return summary

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
        # LLM 分段在 164 页上是 4-8 分钟、全程无回调，必须靠后台心跳撑着，
        # 否则 `_begin_stage` 写的那一次心跳之后再无声息，看门狗会来杀。
        with periodic_heartbeat(job.id):
            drafts, segment_summary = detect_segments_with_fallback(
                pages,
                template_key=job.template_key,
                # 批级成果落在 job 目录里：worker 被杀后重跑接着已完成的批跑，
                # 不再为同一批 LLM 付第二次钱。
                checkpoint_path=storage.analysis_dir / "segment_checkpoint.json",
            )

        # 跨页一致性校对与段级质量标记：与 analyze_pdf 走同一条路径（同一份判据、
        # 同一份文案），避免「单任务入口有、两阶段入口没有」的劈叉。
        inconsistencies = detect_inconsistencies(pages)
        segments_md = attach_page_quality_flags(
            attach_quality_flags_to_markdown(
                build_segments_markdown(
                    drafts, pages, bbox_backend=self._bbox_backend(job_id=job.id, storage=storage, pages=pages)
                ),
                inconsistencies,
            ),
            qualities_by_page(pages),
        )
        outcome = PdfAnalysisOutcome(
            pages=pages,
            drafts=drafts,
            segments_md=segments_md,
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
            },
        )
        # merge_summary=False：本阶段只产出分段相关字段，不能把取字阶段写下的
        # ocr_profile / layout_mode / material_kind 抹掉（summary 只增不删）。
        self._persist_analysis(job=job, storage=storage, outcome=outcome, merge_summary=False)
        PdfSplitJob.objects.filter(id=job.id).update(stage=PdfSplitStage.DONE)

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
        merge_summary: bool = True,
    ) -> None:  # pragma: no cover
        """把 pipeline 产物落库落盘：pages / segments / segments_md + 任务摘要（含取字与分段的观测字段）。

        ``merge_summary``：整条流水线跑完（analyze_job）时 True，outcome.summary 就是完整快照；
        两阶段链路的分段阶段只产出分段相关字段，必须 False——否则会把取字阶段写入并落库的
        ``ocr_profile`` / ``layout_mode`` / ``material_kind`` 等字段从 summary 里抹掉。
        summary 只增不删，前端可能还有旧消费方在读这些键。
        """
        storage.write_json(storage.pages_json_path, [asdict(item) for item in outcome.pages])
        storage.write_json(storage.segments_json_path, [asdict(item) for item in outcome.drafts])
        storage.write_json(storage.segments_md_path, outcome.segments_md)

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

        PdfSplitSegment.objects.filter(job=job).delete()
        PdfSplitSegment.objects.bulk_create(
            [
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
        )

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
