"""批量分析主逻辑

Django Q2 入口，内部使用 ThreadPoolExecutor 实现并发 LLM 调用。
遵循 PdfSplitJob 的协作式取消和节流式进度更新模式。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from django.db.models import F
from django.utils import timezone

from ..models import BatchJob, BatchJobItem, BatchJobStatus
from ..services.doc_extractor import DocTextExtractor
from .constants import ANALYSIS_SYSTEM_PROMPT, CHUNK_THRESHOLD
from .parsing import build_case_info, chunk_text, merge_chunk_results
from .registry import task_registry
from .summary import generate_detail_zip, generate_summary

logger = logging.getLogger(__name__)


# ─── 取消监视器 ──────────────────────────────────────────────────────────────


async def _cancel_watcher(job_id: UUID, cancel_event: asyncio.Event) -> None:
    """每 2 秒检查一次 DB 的 cancel_requested 标志"""
    while not cancel_event.is_set():
        try:
            cancelled = await sync_to_async(
                lambda: BatchJob.objects.filter(id=job_id, cancel_requested=True).exists()
            )()
            if cancelled:
                logger.info("检测到取消请求: job=%s", job_id)
                cancel_event.set()
                return
        except Exception:
            pass
        await asyncio.sleep(2)


# ─── 入口点 ──────────────────────────────────────────────────────────────────


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


def run_batch_retry(job_id: str, item_ids: list[str]) -> None:
    """Django Q2 入口点：重试失败的 item"""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_batch_retry_async(UUID(job_id), [UUID(i) for i in item_ids]))
            future.result(timeout=3600)
    except RuntimeError:
        asyncio.run(_run_batch_retry_async(UUID(job_id), [UUID(i) for i in item_ids]))


def _sync_llm_chat(llm: Any, messages: list[dict[str, str]], model: str, temperature: float) -> str:
    """同步调用 LLM（在线程池中运行，使用同步 chat() 方法避免 async 上下文问题）"""
    response = llm.chat(messages=messages, model=model, temperature=temperature)
    return response.content  # type: ignore[no-any-return]


# ─── 辅助函数 ────────────────────────────────────────────────────────────────


async def _increment_counter(job_id: UUID, field: str) -> None:
    """原子递增计数器并更新进度百分比（2 次查询代替原来 3 次）"""
    job: Any = await sync_to_async(
        lambda: (
            BatchJob.objects.filter(id=job_id)
            .values(
                "total_items",
                "completed_items",
                "failed_items",
            )
            .first()
        )
    )()
    if not job or job["total_items"] == 0:
        return
    new_count = job[field] + 1
    # 计算新的已完成+失败数（当前值 + 本次递增的 1）
    new_processed = job["completed_items"] + job["failed_items"] + 1
    new_progress = min(int(new_processed * 100 / job["total_items"]), 100)
    await sync_to_async(
        lambda: BatchJob.objects.filter(id=job_id).update(
            **{
                field: new_count,
                "progress": new_progress,
            }
        )
    )()


# ─── 单文件分析 ──────────────────────────────────────────────────────────────


async def _analyze_single_item(
    item: BatchJobItem,
    *,
    job_prompt: str,
    job_llm_model: str,
    llm: Any,
    extractor: DocTextExtractor,
    thread_pool: Any,
    loop: Any,
    cancel_event: asyncio.Event,
) -> str:
    """对单个文件执行完整的分析流程，返回最终结果文本

    提取文本 → 提取元数据 → 分段 LLM 分析 → 合并结果。
    """
    text = await loop.run_in_executor(thread_pool, extractor.extract_text, item.file.path)

    if cancel_event.is_set():
        raise asyncio.CancelledError

    metadata = await loop.run_in_executor(thread_pool, extractor.extract_doc_metadata, item.file.path)
    case_info = build_case_info(metadata)

    chunks = chunk_text(text) if len(text) > CHUNK_THRESHOLD else [text]
    chunk_results: list[str] = []

    for chunk_idx, chunk in enumerate(chunks):
        if cancel_event.is_set():
            raise asyncio.CancelledError

        chunk_label = f"(第{chunk_idx + 1}/{len(chunks)}段)" if len(chunks) > 1 else ""
        result_text = await loop.run_in_executor(
            thread_pool,
            lambda c=chunk, cl=chunk_label: _sync_llm_chat(
                llm,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"{case_info}用户研究问题：{job_prompt}\n\n"
                            f"以下是从文件「{item.file_name}」中提取的内容{cl}：\n\n{c}\n\n"
                            "请先判断本案是否与用户研究问题相关。如无关，is_relevant 设为 false；如有关，请进行分析。"
                            "请以 JSON 格式输出结果。"
                        ),
                    },
                ],
                model=job_llm_model,
                temperature=0.3,
            ),
        )
        chunk_results.append(result_text)

    return merge_chunk_results(chunk_results, item.file_name)


# ─── 主逻辑 ──────────────────────────────────────────────────────────────────


async def _run_batch_async(job_id: UUID) -> None:
    """批量分析主逻辑

    Phase 1: 批量文本提取（.doc 转 .docx）
    Phase 2: 并发 LLM 分析（ThreadPoolExecutor + Semaphore 限流）
    Phase 3: 汇总报告
    """
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
        status=BatchJobStatus.RUNNING,
        started_at=timezone.now(),
    )

    # 注册活跃任务引用
    task = asyncio.current_task()
    if task:
        task_registry.register(str(job_id), task)

    cancel_event = asyncio.Event()
    cancel_task = asyncio.create_task(_cancel_watcher(job_id, cancel_event))

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
        loop = asyncio.get_running_loop()
        thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def analyze_item(item: BatchJobItem, index: int) -> None:
            if cancel_event.is_set():
                return

            await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                status=BatchJobStatus.RUNNING,
            )
            start = time.perf_counter()

            if index == 0:
                await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                    started_processing_at=timezone.now(),
                )

            try:
                final_result = await _analyze_single_item(
                    item,
                    job_prompt=job.prompt,
                    job_llm_model=job.llm_model,
                    llm=llm,
                    extractor=extractor,
                    thread_pool=thread_pool,
                    loop=loop,
                    cancel_event=cancel_event,
                )

                duration = (time.perf_counter() - start) * 1000
                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.COMPLETED,
                    result=final_result,
                    duration_ms=round(duration, 2),
                )
                await _increment_counter(job_id, "completed_items")

            except asyncio.CancelledError:
                return

            except Exception as e:
                logger.error("文件分析失败: %s - %s", item.file_name, e, exc_info=True)
                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.FAILED,
                    error=str(e)[:2000],
                )
                await _increment_counter(job_id, "failed_items")

        # 并发执行（Semaphore 限流）
        async def throttled_analyze(item: BatchJobItem, index: int) -> None:
            async with semaphore:
                await analyze_item(item, index)

        tasks = [throttled_analyze(item, i) for i, item in enumerate(items)]
        await asyncio.gather(*tasks, return_exceptions=True)

        thread_pool.shutdown(wait=False)

        # 取消监视器
        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass

        # ── 检查是否被取消 ──
        if cancel_event.is_set():
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.CANCELLED,
                finished_at=timezone.now(),
            )
            logger.info("批量分析已取消: job=%s", job_id)
            return

        # ── Phase 3: 汇总 ──
        completed_items = [
            item async for item in BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.COMPLETED)
        ]

        if completed_items:
            logger.info("Phase 3: 生成汇总报告 (%d 个已完成)", len(completed_items))
            summary = await generate_summary(job_id, job.prompt, completed_items)
            await generate_detail_zip(job_id, completed_items)
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
        task_registry.unregister(str(job_id))
        extractor.cleanup()


# ─── 重试逻辑 ────────────────────────────────────────────────────────────────


async def _run_batch_retry_async(job_id: UUID, item_ids: list[UUID]) -> None:
    """只重试指定的失败 item"""
    job = await sync_to_async(BatchJob.objects.get)(id=job_id)
    await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
        status=BatchJobStatus.RUNNING,
    )

    cancel_event = asyncio.Event()
    cancel_task = asyncio.create_task(_cancel_watcher(job_id, cancel_event))

    extractor = DocTextExtractor()
    try:
        items = [item async for item in BatchJobItem.objects.filter(job_id=job_id, id__in=item_ids)]

        from apps.core.llm.service import get_llm_service

        llm = await sync_to_async(get_llm_service)()
        concurrency = job.metadata.get("concurrency", 50)
        loop = asyncio.get_running_loop()
        thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def analyze_item(item: BatchJobItem, index: int) -> None:
            if cancel_event.is_set():
                return

            await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                status=BatchJobStatus.RUNNING,
                error="",
            )
            start = time.perf_counter()

            try:
                final_result = await _analyze_single_item(
                    item,
                    job_prompt=job.prompt,
                    job_llm_model=job.llm_model,
                    llm=llm,
                    extractor=extractor,
                    thread_pool=thread_pool,
                    loop=loop,
                    cancel_event=cancel_event,
                )

                duration = (time.perf_counter() - start) * 1000
                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.COMPLETED,
                    result=final_result,
                    duration_ms=round(duration, 2),
                )
                await sync_to_async(
                    lambda: BatchJob.objects.filter(id=job_id).update(
                        failed_items=F("failed_items") - 1,
                        completed_items=F("completed_items") + 1,
                    )
                )()
                # 重试成功后更新 progress
                job_info = await sync_to_async(
                    lambda: (
                        BatchJob.objects.filter(id=job_id)
                        .values(
                            "total_items",
                            "completed_items",
                            "failed_items",
                        )
                        .first()
                    )
                )()
                if job_info and job_info["total_items"] > 0:
                    new_progress = min(
                        int((job_info["completed_items"] + job_info["failed_items"]) * 100 / job_info["total_items"]),
                        100,
                    )
                    await sync_to_async(lambda: BatchJob.objects.filter(id=job_id).update(progress=new_progress))()

            except asyncio.CancelledError:
                return

            except Exception as e:
                logger.error("重试分析失败: %s - %s", item.file_name, e, exc_info=True)
                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.FAILED,
                    error=str(e)[:2000],
                )

        async def throttled_analyze(item: BatchJobItem, index: int) -> None:
            async with semaphore:
                await analyze_item(item, index)

        tasks = [throttled_analyze(item, i) for i, item in enumerate(items)]
        await asyncio.gather(*tasks, return_exceptions=True)

        thread_pool.shutdown(wait=False)
        cancel_task.cancel()
        try:
            await cancel_task
        except asyncio.CancelledError:
            pass

        if cancel_event.is_set():
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.CANCELLED,
                finished_at=timezone.now(),
            )
            return

        # 重新生成汇总
        completed_items = [
            item async for item in BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.COMPLETED)
        ]
        if completed_items:
            summary = await generate_summary(job_id, job.prompt, completed_items)
            await generate_detail_zip(job_id, completed_items)
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.COMPLETED,
                summary=summary,
                progress=100,
                finished_at=timezone.now(),
            )

    except Exception as e:
        logger.exception("重试任务异常: job=%s", job_id)
        await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
            status=BatchJobStatus.FAILED,
            error_message=str(e)[:4000],
            finished_at=timezone.now(),
        )
    finally:
        extractor.cleanup()
