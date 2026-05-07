"""批量分析异步任务

Django Q2 入口，内部使用 ThreadPoolExecutor 实现并发 LLM 调用。
遵循 PdfSplitJob 的协作式取消和节流式进度更新模式。

注意：LLMService.achat() 内部的 is_available() 会同步读取 SystemConfig，
不能在 async 上下文中直接调用。因此 LLM 调用通过 run_in_executor 在线程池中执行。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from datetime import UTC, datetime
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
    "4. 使用专业但易懂的语言\n"
    "5. 使用清晰的结构化格式\n"
    "6. 如果用户提供了案号、审理法院等元数据，请在分析中使用这些信息，不要编造\n"
    "7. 最后详细列出案例的案号、案由、法官和书记员姓名、关于用户查询的问题在本案中的结论"
)
SUMMARY_SYSTEM_PROMPT = (
    "你是一位法律研究助理。请根据多个案例的分析结论，撰写一份综合研究报告。"
    "报告应当：\n"
    "1. 概括所有案例的共同规律和趋势\n"
    "2. 指出各案例之间的异同点\n"
    "3. 提炼出有价值的法律见解\n"
    "4. 使用清晰的结构化格式\n"
    f"5. 报告日期使用今天的实际日期（{datetime.now(UTC).strftime('%Y年%m月%d日')}），不要编造日期\n"
    "6. 最后要添加附件部分，把每个案例的分析结论和案号、案由、法官和书记员姓名、关于用户查询的问题在本案中的结论列出来"
)


def run_batch_analysis(job_id: str) -> None:
    """Django Q2 入口点

    接收 job_id 字符串，调用异步逻辑。
    Django Q2 worker 已有事件循环，需要用线程隔离执行 asyncio.run()。
    """
    try:
        asyncio.get_running_loop()
        # 已有运行中的循环 → 用线程隔离执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_batch_async(UUID(job_id)))
            future.result(timeout=3600)
    except RuntimeError:
        # 没有运行中的循环 → 直接用 asyncio.run()
        asyncio.run(_run_batch_async(UUID(job_id)))


def _sync_llm_chat(llm: Any, messages: list[dict[str, str]], model: str, temperature: float) -> str:
    """同步调用 LLM（在线程池中运行，使用同步 chat() 方法避免 async 上下文问题）"""
    response = llm.chat(messages=messages, model=model, temperature=temperature)
    return response.content


async def _run_batch_async(job_id: UUID) -> None:
    """批量分析主逻辑

    Phase 1: 批量文本提取（.doc 转 .docx）
    Phase 2: 并发 LLM 分析（ThreadPoolExecutor）
    Phase 3: 汇总报告
    """
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
        status=BatchJobStatus.RUNNING,
        started_at=timezone.now(),
    )

    extractor = DocTextExtractor()
    try:
        items = [item async for item in BatchJobItem.objects.filter(job_id=job_id)]

        # ── Phase 1: 批量文本提取 ──
        doc_items = [
            i for i in items if i.file_name.lower().endswith(".doc") and not i.file_name.lower().endswith(".docx")
        ]
        if doc_items:
            logger.info("Phase 1: 批量转换 %d 个 .doc 文件", len(doc_items))
            doc_paths = [item.file.path for item in doc_items]
            await sync_to_async(extractor.batch_convert_doc_to_docx)(doc_paths)

        # ── Phase 2: 并发 LLM 分析 ──
        from apps.core.llm.service import get_llm_service

        # 在 sync 上下文中初始化 LLM 服务（内部会读取 SystemConfig）
        llm = await sync_to_async(get_llm_service)()
        concurrency = job.metadata.get("concurrency", 50)
        logger.info("Phase 2: 开始并发分析 %d 个文件 (concurrency=%d)", len(items), concurrency)

        # 使用 ThreadPoolExecutor 实现并发（避免 LLMService 内部 sync ORM 调用问题）
        loop = asyncio.get_event_loop()
        thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)

        async def analyze_item(item: BatchJobItem, index: int) -> None:
            # 检查取消
            if await _is_cancelled(job_id):
                return

            await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                status=BatchJobStatus.RUNNING,
            )
            start = time.perf_counter()

            try:
                # 提取文本（在 sync 线程中）
                text = await sync_to_async(extractor.extract_text)(item.file.path)

                # 从文档中提取元数据（案号、法院、案由、法官、书记员）
                metadata = await sync_to_async(extractor.extract_doc_metadata)(item.file.path)
                meta_parts = []
                if metadata.get("case_number"):
                    meta_parts.append(f"案号：{metadata['case_number']}")
                if metadata.get("court"):
                    meta_parts.append(f"审理法院：{metadata['court']}")
                if metadata.get("cause"):
                    meta_parts.append(f"案由：{metadata['cause']}")
                if metadata.get("judge"):
                    meta_parts.append(f"法官：{metadata['judge']}")
                if metadata.get("clerk"):
                    meta_parts.append(f"书记员：{metadata['clerk']}")
                case_info = "\n".join(meta_parts) + "\n" if meta_parts else ""

                # LLM 分析（在线程池中执行，避免 async 上下文 ORM 问题）
                result_text = await loop.run_in_executor(
                    thread_pool,
                    lambda: _sync_llm_chat(
                        llm,
                        messages=[
                            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": f"{case_info}分析要求：{job.prompt}\n\n以下是从文件「{item.file_name}」中提取的内容：\n\n{text}\n\n请根据以上分析要求，对本文档内容进行分析并给出结论。",
                            },
                        ],
                        model=job.llm_model,
                        temperature=0.3,
                    ),
                )

                duration = (time.perf_counter() - start) * 1000
                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.COMPLETED,
                    result=result_text,
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

        thread_pool.shutdown(wait=False)

        # ── Phase 3: 汇总 ──
        if await _is_cancelled(job_id):
            return

        completed_items = [
            item async for item in BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.COMPLETED)
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
    finally:
        extractor.cleanup()


async def _is_cancelled(job_id: UUID) -> bool:
    """检查任务是否被取消"""
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    return job.cancel_requested


async def _increment_counter(job_id: UUID, field: str) -> None:
    """原子递增计数器"""
    await sync_to_async(lambda: BatchJob.objects.filter(id=job_id).update(**{field: F(field) + 1}))()


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
    conclusions = []
    for item in completed_items:
        conclusions.append(f"## {item.file_name}\n{item.result}")

    all_conclusions = "\n\n---\n\n".join(conclusions)

    if len(all_conclusions) > 50000:
        all_conclusions = all_conclusions[:50000] + "\n\n...(已截断)"

    result = await sync_to_async(_sync_llm_chat)(
        llm,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"原始分析要求：{prompt}\n\n以下是 {len(completed_items)} 个案例的分析结论：\n\n{all_conclusions}\n\n请撰写一份综合研究报告。",
            },
        ],
        model=model,
        temperature=0.3,
    )
    return result
