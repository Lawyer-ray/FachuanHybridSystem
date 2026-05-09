"""批量分析异步任务

Django Q2 入口，内部使用 ThreadPoolExecutor 实现并发 LLM 调用。
遵循 PdfSplitJob 的协作式取消和节流式进度更新模式。

优化特性：
- asyncio.Semaphore 并发限流，避免 API rate limit
- asyncio.Event 取消机制，即时中断
- LLM 结构化输出（JSON Schema），正则作为 fallback
- 长文档分段分析
- SSE 事件发布到 Django cache
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
from pydantic import BaseModel

from .models import BatchJob, BatchJobItem, BatchJobStatus
from .services.doc_extractor import DocTextExtractor

logger = logging.getLogger(__name__)

# 常量
PROGRESS_UPDATE_EVERY = 5  # 每 N 个 item 更新一次进度
CANCEL_CHECK_EVERY = 5  # 每 N 个 item 检查一次取消标志
CHUNK_SIZE = 15000  # 长文档分段大小
CHUNK_OVERLAP = 2000  # 分段重叠字符数
CHUNK_THRESHOLD = 20000  # 超过此长度触发分段

# 活跃任务引用（用于即时取消）
_active_tasks: dict[str, asyncio.Task[None]] = {}


# ─── 结构化输出模型 ──────────────────────────────────────────────────────────


class CaseAnalysisResult(BaseModel):
    """LLM 分析结果的结构化输出"""

    case_number: str = "未注明"
    cause: str = "未注明"
    court: str = "未注明"
    judge: str = "未注明"
    clerk: str = "未注明"
    is_relevant: bool = True
    conclusion: str = ""
    analysis: str = ""


# ─── 系统提示词 ──────────────────────────────────────────────────────────────

_ANALYSIS_INSTRUCTIONS = (
    "你是一位专业的法律文档分析专家。请根据用户提供的分析要求，对文档内容进行分析。\n\n"
    "## 分析步骤\n"
    "第一步：判断本案是否与用户的研究问题相关。\n"
    "- 如果无关，is_relevant 设为 false，conclusion 说明无关原因，analysis 简要说明即可。\n"
    "- 如果有关，is_relevant 设为 true，继续下一步。\n\n"
    "第二步（仅相关案例）：\n"
    "1. 分析本案的全部争议焦点和裁判要旨\n"
    "2. 但只详细输出与用户查询问题直接相关的争议焦点和裁判要旨，其他内容简要提及即可\n"
    "3. 给出针对用户查询问题的明确结论\n\n"
    "## 输出格式要求\n"
    "- 如果用户提供了案号、审理法院等元数据，请使用这些信息，不要编造\n"
    "- 使用专业但易懂的语言\n"
    "- 使用清晰的结构化格式\n\n"
    "## 重要\n"
    "- case_number、cause、court、judge、clerk 字段必须从文档中提取，找不到则填「未注明」\n"
    "- conclusion 字段填写针对用户研究问题的结论\n"
    "- analysis 字段填写完整的分析正文（Markdown 格式）"
)

from apps.core.llm.structured_output import json_schema_instructions

_SCHEMA_INSTRUCTIONS = json_schema_instructions(CaseAnalysisResult)

ANALYSIS_SYSTEM_PROMPT = _ANALYSIS_INSTRUCTIONS + "\n\n" + _SCHEMA_INSTRUCTIONS

# 正则 fallback（当 JSON 解析失败时使用）
METADATA_BLOCK_RE = __import__("re").compile(
    r"```[^\n]*\n\s*【案例元数据汇总】\s*\n([\s\S]*?)\n\s*```\s*\Z"
    r"|【案例元数据汇总】\s*\n([\s\S]*?)\Z",
)
METADATA_FIELD_RE = __import__("re").compile(
    r"^(案号|案由|审理法院|法官|书记员|与研究问题相关|结论)\s*[：:]\s*(.+)$", __import__("re").MULTILINE
)
_CONCLUSION_RE = __import__("re").compile(
    r"(?:^|\n)#{1,3}\s*(?:针对.*研究.*结论|结论)\s*\n([\s\S]*?)(?=\n(?:```|【案例元数据汇总】|#{1,3}\s)|\Z)",
    __import__("re").MULTILINE,
)


# ─── SSE 事件发布（已废弃，SSE 端点改为数据库轮询）────────────────────────────


async def _publish_sse_event(_job_id: UUID, _event_type: str, _data: dict[str, Any]) -> None:
    """不再需要：SSE 端点已改为直接轮询数据库。保留函数签名避免改动调用方。"""


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


# ─── 文档分段 ────────────────────────────────────────────────────────────────


def _chunk_text(text: str, max_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将长文本分成重叠的段落"""
    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_size
        if end < len(text):
            # 尝试在句号、换行处断开
            for sep in ["\n\n", "\n", "。", "；", ".", "\r\n"]:
                pos = text.rfind(sep, start + max_size // 2, end)
                if pos > start:
                    end = pos + len(sep)
                    break
        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else end
    return chunks


# ─── 结果解析 ────────────────────────────────────────────────────────────────


def _parse_llm_result(result_text: str, file_name: str) -> dict[str, Any]:
    """解析 LLM 输出，优先 JSON 结构化，fallback 到正则"""
    from apps.core.llm.structured_output import parse_model_content

    # 尝试 JSON 结构化解析
    try:
        parsed = parse_model_content(result_text, CaseAnalysisResult)
        return {
            "case_number": parsed.case_number,
            "cause": parsed.cause,
            "court": parsed.court,
            "judge": parsed.judge,
            "clerk": parsed.clerk,
            "is_relevant": parsed.is_relevant,
            "conclusion": parsed.conclusion,
            "analysis": parsed.analysis,
            "parse_method": "json",
        }
    except Exception:
        logger.debug("JSON 解析失败，回退到正则: %s", file_name)

    # Fallback：正则提取
    fields: dict[str, str] = {}
    block_match = METADATA_BLOCK_RE.search(result_text)
    if block_match:
        block_text = (block_match.group(1) or block_match.group(2) or "").strip()
        for field_match in METADATA_FIELD_RE.finditer(block_text):
            fields[field_match.group(1).strip()] = field_match.group(2).strip()

    conclusion = fields.get("结论", "")
    conclusion_match = _CONCLUSION_RE.search(result_text)
    if conclusion_match:
        full_conclusion = conclusion_match.group(1).strip()
        if full_conclusion:
            conclusion = full_conclusion

    # 去掉元数据块，保留分析正文
    analysis = result_text
    if block_match:
        analysis = result_text[: block_match.start()].strip()

    return {
        "case_number": fields.get("案号", "未注明"),
        "cause": fields.get("案由", "未注明"),
        "court": fields.get("审理法院", "未注明"),
        "judge": fields.get("法官", "未注明"),
        "clerk": fields.get("书记员", "未注明"),
        "is_relevant": fields.get("与研究问题相关", "是") == "是",
        "conclusion": conclusion or "未注明",
        "analysis": analysis,
        "parse_method": "regex",
    }


# ─── 共享分析逻辑 ────────────────────────────────────────────────────────────


def _build_case_info(metadata: dict[str, str | None]) -> str:
    """从文档元数据构建案例信息字符串"""
    parts = []
    if metadata.get("case_number"):
        parts.append(f"案号：{metadata['case_number']}")
    if metadata.get("court"):
        parts.append(f"审理法院：{metadata['court']}")
    if metadata.get("cause"):
        parts.append(f"案由：{metadata['cause']}")
    if metadata.get("judge"):
        parts.append(f"法官：{metadata['judge']}")
    if metadata.get("clerk"):
        parts.append(f"书记员：{metadata['clerk']}")
    return "\n".join(parts) + "\n" if parts else ""


def _merge_chunk_results(chunk_results: list[str], file_name: str) -> str:
    """合并多个 chunk 的分析结果"""
    if len(chunk_results) == 1:
        return chunk_results[0]

    all_analysis = []
    last_parsed = _parse_llm_result(chunk_results[-1], file_name)
    for cr in chunk_results:
        parsed = _parse_llm_result(cr, file_name)
        if parsed["analysis"]:
            all_analysis.append(parsed["analysis"])
    last_parsed["analysis"] = "\n\n---\n\n".join(all_analysis)
    return json.dumps(last_parsed, ensure_ascii=False)


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
    case_info = _build_case_info(metadata)

    chunks = _chunk_text(text) if len(text) > CHUNK_THRESHOLD else [text]
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

    return _merge_chunk_results(chunk_results, item.file_name)


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
        _active_tasks[str(job_id)] = task

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
        loop = asyncio.get_event_loop()
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

            # 节流式进度更新
            if index % PROGRESS_UPDATE_EVERY == 0 or index == len(items) - 1:
                await _update_progress(job_id)
                # 发布进度 SSE 事件
                refreshed_job = await sync_to_async(BatchJob.objects.get)(id=job_id)
                await _publish_sse_event(
                    job_id,
                    "progress",
                    {
                        "completed_items": refreshed_job.completed_items,
                        "failed_items": refreshed_job.failed_items,
                        "total_items": refreshed_job.total_items,
                        "progress": refreshed_job.progress,
                    },
                )

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
            await _publish_sse_event(job_id, "job_completed", {"status": "cancelled"})
            logger.info("批量分析已取消: job=%s", job_id)
            return

        # ── Phase 3: 汇总 ──
        completed_items = [
            item async for item in BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.COMPLETED)
        ]

        if completed_items:
            logger.info("Phase 3: 生成汇总报告 (%d 个已完成)", len(completed_items))
            summary = await _generate_summary(job_id, job.prompt, completed_items)
            await _generate_detail_zip(job_id, completed_items)
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.COMPLETED,
                summary=summary,
                progress=100,
                finished_at=timezone.now(),
            )
            await _publish_sse_event(job_id, "job_completed", {"status": "completed", "summary": summary})
            logger.info("批量分析完成: job=%s", job_id)
        else:
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.FAILED,
                error_message="所有文件分析失败",
                finished_at=timezone.now(),
            )
            await _publish_sse_event(job_id, "job_completed", {"status": "failed"})
            logger.warning("批量分析全部失败: job=%s", job_id)

    except Exception as e:
        logger.exception("批量分析任务异常: job=%s", job_id)
        await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
            status=BatchJobStatus.FAILED,
            error_message=str(e)[:4000],
            finished_at=timezone.now(),
        )
        await _publish_sse_event(job_id, "job_completed", {"status": "failed", "error": str(e)[:200]})
    finally:
        _active_tasks.pop(str(job_id), None)
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
        loop = asyncio.get_event_loop()
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

            except asyncio.CancelledError:
                return

            except Exception as e:
                logger.error("重试分析失败: %s - %s", item.file_name, e, exc_info=True)
                await sync_to_async(BatchJobItem.objects.filter(id=item.id).update)(
                    status=BatchJobStatus.FAILED,
                    error=str(e)[:2000],
                )

            if index % PROGRESS_UPDATE_EVERY == 0 or index == len(items) - 1:
                await _update_progress(job_id)

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
            summary = await _generate_summary(job_id, job.prompt, completed_items)
            await _generate_detail_zip(job_id, completed_items)
            await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
                status=BatchJobStatus.COMPLETED,
                summary=summary,
                progress=100,
                finished_at=timezone.now(),
            )
            await _publish_sse_event(job_id, "job_completed", {"status": "completed", "summary": summary})

    except Exception as e:
        logger.exception("重试任务异常: job=%s", job_id)
        await sync_to_async(BatchJob.objects.filter(id=job_id).update)(
            status=BatchJobStatus.FAILED,
            error_message=str(e)[:4000],
            finished_at=timezone.now(),
        )
    finally:
        extractor.cleanup()


# ─── 辅助函数 ────────────────────────────────────────────────────────────────


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
    job_id: UUID,
    prompt: str,
    completed_items: list[BatchJobItem],
) -> str:
    """从每个案例的分析结果中提取元数据，生成 CSV 文件并返回统计摘要。"""
    import csv
    import io

    from django.core.files.base import ContentFile

    csv_rows: list[dict[str, str]] = []
    missing_count = 0

    for item in completed_items:
        if not item.result:
            continue

        # 尝试 JSON 解析
        parsed = _parse_llm_result(item.result, item.file_name)

        if parsed["parse_method"] == "regex" and parsed["case_number"] == "未注明" and parsed["conclusion"] == "未注明":
            missing_count += 1
            csv_rows.append(
                {
                    "文件名": item.file_name,
                    "案号": "",
                    "案由": "",
                    "审理法院": "",
                    "法官": "",
                    "书记员": "",
                    "与研究问题相关": "",
                    "结论": "未提取到元数据",
                }
            )
            continue

        csv_rows.append(
            {
                "文件名": item.file_name,
                "案号": parsed["case_number"],
                "案由": parsed["cause"],
                "审理法院": parsed["court"],
                "法官": parsed["judge"],
                "书记员": parsed["clerk"],
                "与研究问题相关": "是" if parsed["is_relevant"] else "否",
                "结论": parsed["conclusion"],
            }
        )

    if not csv_rows:
        return "所有案例分析结果为空，无法生成汇总。"

    # 生成 CSV
    output = io.StringIO()
    fieldnames = ["文件名", "案号", "案由", "审理法院", "法官", "书记员", "与研究问题相关", "结论"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(csv_rows)
    csv_content = output.getvalue()

    # 写入文件（必须用 instance.save() 才能触发 upload_to 路径生成）
    csv_filename = f"案例分析汇总_{job_id.hex[:8]}.csv"
    csv_file = ContentFile(csv_content.encode("utf-8-sig"), name=csv_filename)

    def _save_summary() -> None:
        job = BatchJob.objects.get(id=job_id)
        job.summary_file.save(csv_filename, csv_file, save=True)

    await sync_to_async(_save_summary)()

    # 统计
    total = len(csv_rows)
    relevant = sum(1 for r in csv_rows if r.get("与研究问题相关") == "是")
    irrelevant = sum(1 for r in csv_rows if r.get("与研究问题相关") == "否")

    summary_text = (
        f"## 案例分析汇总\n\n"
        f"- 分析要求：{prompt}\n"
        f"- 案例总数：{total}\n"
        f"- 相关案例：{relevant}\n"
        f"- 无关案例：{irrelevant}\n"
    )
    if missing_count:
        summary_text += f"- 未提取到元数据：{missing_count}\n"

    summary_text += "\n汇总表已生成为 CSV 文件，可点击下载。\n"

    if missing_count:
        summary_text += f"\n> 注意：有 {missing_count} 个案例未提取到元数据，可能是分析结果格式不符合预期。\n"

    return summary_text


def build_detail_zip_sync(job_id: UUID) -> bool:
    """同步生成分析详情 ZIP 并保存到 job.detail_zip_file。

    如果没有已完成的项目则返回 False。
    """
    import io
    import re
    import zipfile

    from django.core.files.base import ContentFile

    completed_items = list(BatchJobItem.objects.filter(job_id=job_id, status=BatchJobStatus.COMPLETED))
    if not completed_items:
        return False

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}

        for item in completed_items:
            if not item.result:
                continue

            parsed = _parse_llm_result(item.result, item.file_name)

            md_parts: list[str] = []
            md_parts.append("# 案例分析报告\n")
            md_parts.append("## 基本信息\n")
            md_parts.append(f"- **文件名**：{item.file_name}")
            md_parts.append(f"- **案号**：{parsed['case_number']}")
            md_parts.append(f"- **案由**：{parsed['cause']}")
            md_parts.append(f"- **审理法院**：{parsed['court']}")
            md_parts.append(f"- **法官**：{parsed['judge']}")
            md_parts.append(f"- **书记员**：{parsed['clerk']}")
            md_parts.append(f"- **与研究问题相关**：{'是' if parsed['is_relevant'] else '否'}")
            md_parts.append("")
            md_parts.append("## 结论\n")
            md_parts.append(parsed["conclusion"])
            md_parts.append("")
            md_parts.append("## 详细分析\n")
            md_parts.append(parsed["analysis"])

            md_content = "\n".join(md_parts)

            # 从原始文件名派生 md 文件名
            base_name = item.file_name
            if "." in base_name:
                base_name = base_name.rsplit(".", 1)[0]
            base_name = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "_", base_name)
            base_name = re.sub(r"_+", "_", base_name).strip("_") or "unnamed"

            md_filename = f"{base_name}.md"

            # 处理重名
            if md_filename in seen_names:
                seen_names[md_filename] += 1
                md_filename = f"{base_name}_{seen_names[md_filename]}.md"
            else:
                seen_names[md_filename] = 0

            zf.writestr(md_filename, md_content.encode("utf-8"))

    zip_buffer.seek(0)
    hex_str = job_id.hex if isinstance(job_id, UUID) else UUID(str(job_id)).hex
    zip_filename = f"案例分析详情_{hex_str[:8]}.zip"
    zip_file = ContentFile(zip_buffer.getvalue(), name=zip_filename)

    job = BatchJob.objects.get(id=job_id)
    job.detail_zip_file.save(zip_filename, zip_file, save=True)
    return True


async def _generate_detail_zip(
    job_id: UUID,
    completed_items: list[BatchJobItem],
) -> None:
    """为每个已完成的案例生成独立的 .md 文件，打包为 ZIP。"""
    await sync_to_async(build_detail_zip_sync)(job_id)
