"""批量分析异步任务

Django Q2 入口，内部使用 asyncio.Semaphore + asyncio.gather 实现并发 LLM 调用。
遵循 PdfSplitJob 的协作式取消和节流式进度更新模式。
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.db.models import F
from django.utils import timezone

from .models import BatchJob, BatchJobItem, BatchJobStatus
from .services.doc_extractor import DocTextExtractor

logger = logging.getLogger(__name__)

# 常量
PROGRESS_UPDATE_EVERY = 5  # 每 N 个 item 更新一次进度
CANCEL_CHECK_EVERY = 5  # 每 N 个 item 检查一次取消标志
ANALYSIS_SYSTEM_PROMPT = (
    "你是一位专业的法律文档分析专家。请根据用户提供的分析要求，对文档内容进行深入分析，"
    "并给出明确的结论。你的分析应当：\n"
    "1. 基于文档中的具体事实和法律依据\n"
    "2. 指出关键的法律问题和争议焦点\n"
    "3. 给出清晰的分析结论\n"
    "4. 使用专业但易懂的语言"
)
SUMMARY_SYSTEM_PROMPT = (
    "你是一位法律研究助理。请根据多个案例的分析结论，撰写一份综合研究报告。"
    "报告应当：\n"
    "1. 概括所有案例的共同规律和趋势\n"
    "2. 指出各案例之间的异同点\n"
    "3. 提炼出有价值的法律见解\n"
    "4. 使用清晰的结构化格式"
)


def run_batch_analysis(job_id: str) -> None:
    """Django Q2 入口点

    接收 job_id 字符串，调用异步逻辑。
    """
    asyncio.run(_run_batch_async(UUID(job_id)))


async def _run_batch_async(job_id: UUID) -> None:
    """批量分析主逻辑

    Phase 1: 批量文本提取（.doc 转 .docx）
    Phase 2: 并发 LLM 分析
    Phase 3: 汇总报告
    """
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
        status=BatchJobStatus.RUNNING,
        started_at=timezone.now(),
    )

    try:
        items = [item async for item in BatchJobItem.objects.filter(job_id=job_id)]

        # ── Phase 1: 批量文本提取 ──
        extractor = DocTextExtractor()
        doc_items = [i for i in items if i.file_name.lower().endswith(".doc") and not i.file_name.lower().endswith(".docx")]
        if doc_items:
            logger.info("Phase 1: 批量转换 %d 个 .doc 文件", len(doc_items))
            doc_paths = [item.file.path for item in doc_items]
            await sync_to_async(extractor.batch_convert_doc_to_docx)(doc_paths)

        # ── Phase 2: 并发 LLM 分析 ──
        logger.info("Phase 2: 开始并发分析 %d 个文件 (concurrency=%d)", len(items), job.metadata.get("concurrency", 50))
        from apps.core.llm.service import get_llm_service

        llm = get_llm_service()
        concurrency = job.metadata.get("concurrency", 50)
        semaphore = asyncio.Semaphore(concurrency)

        async def analyze_item(item: BatchJobItem, index: int) -> None:
            async with semaphore:
                # 检查取消
                if await _is_cancelled(job_id):
                    return

                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.RUNNING,
                )
                start = time.perf_counter()

                try:
                    # 提取文本
                    text = await sync_to_async(extractor.extract_text)(item.file.path)

                    # LLM 分析
                    response = await llm.achat(
                        messages=[
                            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                            {"role": "user", "content": f"分析要求：{job.prompt}\n\n以下是从文件「{item.file_name}」中提取的内容：\n\n{text}\n\n请根据以上分析要求，对本文档内容进行分析并给出结论。"},
                        ],
                        model=job.llm_model,
                        temperature=0.3,
                    )

                    duration = (time.perf_counter() - start) * 1000
                    await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                        status=BatchJobStatus.COMPLETED,
                        result=response.content,
                        duration_ms=round(duration, 2),
                    )
                    await _increment_counter(job_id, "completed_items")

                except Exception as e:
                    logger.error("文件分析失败: %s - %s", item.file_name, e, exc_info=True)
                    await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                        status=BatchJobStatus.FAILED,
                        error=str(e)[:2000],
                    )
                    await _increment_counter(job_id, "failed_items")

                # 节流式进度更新
                if index % PROGRESS_UPDATE_EVERY == 0 or index == len(items) - 1:
                    await _update_progress(job_id)

        # 并发执行
        tasks = [analyze_item(item, i) for i, item in enumerate(items)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # ── Phase 3: 汇总 ──
        if await _is_cancelled(job_id):
            return

        completed_items = [
            item async for item in BatchJobItem.objects.filter(
                job_id=job_id, status=BatchJobStatus.COMPLETED
            )
        ]

        if completed_items:
            logger.info("Phase 3: 生成汇总报告 (%d 个已完成)", len(completed_items))
            summary = await _generate_summary(llm, job.llm_model, job.prompt, completed_items)
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.COMPLETED,
                summary=summary,
                progress=100,
                finished_at=timezone.now(),
            )
            logger.info("批量分析完成: job=%s", job_id)
        else:
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.FAILED,
                error_message="所有文件分析失败",
                finished_at=timezone.now(),
            )
            logger.warning("批量分析全部失败: job=%s", job_id)

    except Exception as e:
        logger.exception("批量分析任务异常: job=%s", job_id)
        await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
            status=BatchJobStatus.FAILED,
            error_message=str(e)[:4000],
            finished_at=timezone.now(),
        )


async def _is_cancelled(job_id: UUID) -> bool:
    """检查任务是否被取消"""
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    return job.cancel_requested


async def _increment_counter(job_id: UUID, field: str) -> None:
    """原子递增计数器"""
    await sync_to_async(
        lambda: BatchJob.objects.filter(id=job_id).update(**{field: F(field) + 1})
    )()


async def _update_progress(job_id: UUID) -> None:
    """更新进度百分比"""
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    if job.total_items > 0:
        progress = int((job.completed_items + job.failed_items) * 100 / job.total_items)
        await sync_to_async(BatchJob.objects.filter(id=job_id).update)(progress=progress)


async def _generate_summary(
    llm: Any,
    model: str,
    prompt: str,
    completed_items: list[BatchJobItem],
) -> str:
    """汇总所有分析结论，生成综合报告"""
    # 收集所有结论
    conclusions = []
    for item in completed_items:
        conclusions.append(f"## {item.file_name}\n{item.result}")

    all_conclusions = "\n\n---\n\n".join(conclusions)

    # 如果结论太长，截断
    if len(all_conclusions) > 50000:
        all_conclusions = all_conclusions[:50000] + "\n\n...(已截断)"

    response = await llm.achat(
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"原始分析要求：{prompt}\n\n以下是 {len(completed_items)} 个案例的分析结论：\n\n{all_conclusions}\n\n请撰写一份综合研究报告。"},
        ],
        model=model,
        temperature=0.3,
    )
    return response.content
