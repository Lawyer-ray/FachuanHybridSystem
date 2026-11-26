from __future__ import annotations

import logging
from uuid import UUID

from django.utils import timezone

from apps.core.services.storage_service import normalize_to_media_rel
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode, PdfSplitStage
from apps.pdf_splitting.services import PdfSplitJobService, PdfSplitService
from apps.pdf_splitting.services.storage import PdfSplitStorage

logger = logging.getLogger("apps.pdf_splitting")


def run_extract_stage(job_id: str) -> None:  # pragma: no cover
    """两阶段任务链 ①：只做取字，完成后把任务推进到分段阶段。

    独立成任务的理由：Django-Q 的 worker 超时（默认 600s）是整个任务的闐值。
    164 页实测取字 + 分段合起来会超时被杀（实测跑到 499s 就被杀），拆开
    后每段各有完整预算。取字产物落 pages.json + 逐页 OCR 缓存，
    即使第二阶段被杀也不用重跑云端。
    """
    from apps.pdf_splitting.services.split import two_stage

    job_uuid = UUID(job_id)
    split_service = PdfSplitService()
    try:
        job = PdfSplitJob.objects.get(id=job_uuid)
        job.refresh_from_db(fields=["cancel_requested", "split_mode"])
        if job.cancel_requested:
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.CANCELLED, finished_at=timezone.now())
            return

        pages, summary = split_service.extract_stage(job)
        storage = PdfSplitStorage(job.id)
        two_stage.save_pages(storage, pages)
        # 取字摘要必须落盘：分段阶段换算 bbox 单位要的是**实际生效**的 ocr_provider
        # （容灾后与首选不同），而 job.cloud_backend 只是用户偏好（默认 auto → 单位
        # unknown → positioned 恒空）。失败不阻断：坐标是附加信息，正文已经拿到了。
        try:
            two_stage.save_extract_summary(storage, dict(summary))
        except Exception:
            logger.exception("pdf_split_extract_summary_save_failed", extra={"job_id": job_id})
        # 页面质量画像必须在这里落盘：段级 quality_flags 要到分段阶段才贴得上，
        # 而那时只剩 pages.json，取不回逐页判定（详见 page_quality_summary 模块注释）。
        # 判据是启发式，只当提示用：算它出错也不能让取字阶段失败。
        try:
            two_stage.save_page_quality(storage, dict(summary.get("page_quality") or {}))
        except Exception:
            logger.exception("pdf_split_page_quality_save_failed", extra={"job_id": job_id})
        # 双引擎分歧**不在这里写**：那时它还没算（双引擎已拆到 cross_check 阶段，
        # 见 run_cross_check_stage）。在这里写只会拿一个空 dict 把上一步的产物覆盖掉。
        job.refresh_from_db(fields=["progress", "total_pages"])
        # 开了双引擎就先去交叉比对（它有自己的 600s），否则直接分段
        two_stage.advance_after_extract(job, pages_count=len(pages))
    except Exception as exc:
        logger.exception("pdf_split_extract_stage_failed", extra={"job_id": job_id})
        two_stage.mark_stage_failed(job_uuid, PdfSplitStage.EXTRACT, str(exc))


def run_cross_check_stage(job_id: str) -> None:  # pragma: no cover
    """任务链 ②：双引擎交叉比对（只有开了双引擎才排这个任务）。

    为什么要独立成任务：整本再解析两遍在 164 页上要十几分钟，而
    `Q_CLUSTER.timeout`（默认 600s）是**单任务**硬阀值——超时直接杀 worker
    进程，`finally` 不执行，任务不留任何 django_q_task 记录，DB 里只剩一个
    `stage=cross_check` 的僵尸。心跳线程救不了：进程没了，线程也没了。
    拆开之后本阶段有自己完整的 600s，与 extract / segment 平级。
    """
    from apps.pdf_splitting.services.split import two_stage

    job_uuid = UUID(job_id)
    split_service = PdfSplitService()
    job = None
    try:
        job = PdfSplitJob.objects.get(id=job_uuid)
        job.refresh_from_db(fields=["cancel_requested", "dual_engines"])
        if job.cancel_requested:
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.CANCELLED)
            return

        summary = split_service.cross_check_stage(job)
        storage = PdfSplitStorage(job.id)
        # 分歧必须落盘：分段阶段只读 pages.json，拿不到双引擎结果；重跑一遍
        # 就是整本再付一次云端费。失败不影响主流程（空分歧也照写，读取端按空处理）。
        try:
            two_stage.save_engine_disagreements(
                storage,
                {
                    "engine_disagreements": list(summary.get("engine_disagreements") or []),
                    "engine_disagree_summary": dict(summary.get("engine_disagree_summary") or {}),
                    "dual_engine": dict(summary.get("dual_engine") or {}),
                    # 转正页回填的记账也要跟着落盘：summary 到分段阶段才写进 DB，
                    # 不落盘的话「哪几页被 VL 换过正文」就只剩 rotated_backfill.json 一处。
                    "rotated_backfill": dict(summary.get("rotated_backfill") or {}),
                    # 分歧裁定的总账（开关状态 + 采信/留人工计数 + 原因分布）。
                    # 不落盘的话分段阶段展开不出这个键，前端就永远看不到「本次自动裁定几条」。
                    "engine_disagreements_judge": dict(summary.get("engine_disagreements_judge") or {}),
                },
            )
        except Exception:
            logger.exception("pdf_split_engine_disagreements_save_failed", extra={"job_id": job_id})

        job.refresh_from_db(fields=["progress", "total_pages"])
        two_stage.advance_to_segment_stage(job, pages_count=job.total_pages or 0)
    except Exception as exc:
        logger.exception("pdf_split_cross_check_stage_failed", extra={"job_id": job_id})
        # 交叉比对是附加信息：它挂了不应该把整份卷宗判失败。能把阶段推下去就推，
        # 推不动（比如 DB 写不进去）才算真失败。
        try:
            if job is None:
                job = PdfSplitJob.objects.get(id=job_uuid)
            job.refresh_from_db(fields=["progress", "total_pages"])
            two_stage.advance_to_segment_stage(job, pages_count=job.total_pages or 0)
        except Exception:
            logger.exception("pdf_split_cross_check_stage_advance_failed", extra={"job_id": job_id})
            two_stage.mark_stage_failed(job_uuid, PdfSplitStage.CROSS_CHECK, str(exc))


def run_segment_stage(job_id: str) -> None:  # pragma: no cover
    """任务链 ③：从 pages.json 读回取字结果，只做分段与落库。"""
    from apps.pdf_splitting.services.split import two_stage

    job_uuid = UUID(job_id)
    split_service = PdfSplitService()
    try:
        job = PdfSplitJob.objects.get(id=job_uuid)
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            PdfSplitJob.objects.filter(id=job.id).update(status=PdfSplitJobStatus.CANCELLED)
            return

        split_service.segment_stage(job)
    except Exception as exc:
        logger.exception("pdf_split_segment_stage_failed", extra={"job_id": job_id})
        two_stage.mark_stage_failed(job_uuid, PdfSplitStage.SEGMENT, str(exc))


def execute_pdf_split_job(job_id: str) -> None:  # pragma: no cover
    job_service = PdfSplitJobService()
    split_service = PdfSplitService()
    job_uuid = UUID(job_id)
    try:
        job = job_service.get_job(job_uuid)
        job.refresh_from_db(fields=["split_mode"])
        # 手动拆分模式跳过后台分析，直接进入待复核状态
        if job.split_mode == PdfSplitMode.MANUAL_SPLIT:
            PdfSplitJob.objects.filter(id=job.id).update(
                status=PdfSplitJobStatus.REVIEW_REQUIRED,
                progress=100,
            )
            return
        split_service.analyze_job(job)
        job.refresh_from_db(fields=["split_mode", "status", "cancel_requested"])
        if (
            job.split_mode == PdfSplitMode.PAGE_SPLIT
            and job.status == PdfSplitJobStatus.REVIEW_REQUIRED
            and not job.cancel_requested
        ):
            split_service.export_job(job)
            storage = PdfSplitStorage(job.id)
            job.refresh_from_db(fields=["status", "cancel_requested"])
            if job.cancel_requested:
                return
            job_service.mark_completed(
                job_id=job_uuid,
                export_zip_relpath=normalize_to_media_rel(storage.export_zip_path.as_posix()),
            )
    except Exception as exc:
        logger.exception("pdf_split_job_failed", extra={"job_id": job_id})
        job_service.mark_failed(job_id=job_uuid, error_message=str(exc))


def export_pdf_split_job(job_id: str) -> None:  # pragma: no cover
    job_service = PdfSplitJobService()
    split_service = PdfSplitService()
    job_uuid = UUID(job_id)
    try:
        job = job_service.get_job(job_uuid)
        split_service.export_job(job)
        storage = PdfSplitStorage(job.id)
        job.refresh_from_db(fields=["status", "cancel_requested"])
        if job.cancel_requested:
            return
        job_service.mark_completed(
            job_id=job_uuid, export_zip_relpath=normalize_to_media_rel(storage.export_zip_path.as_posix())
        )
    except Exception as exc:
        logger.exception("pdf_split_export_failed", extra={"job_id": job_id})
        job_service.mark_failed(job_id=job_uuid, error_message=str(exc))
