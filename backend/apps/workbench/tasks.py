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
    "你是一位专业的法律文档分析专家。请根据用户提供的分析要求，对文档内容进行分析。\n\n"
    "## 分析步骤\n"
    "第一步：判断本案是否与用户的研究问题相关。\n"
    "- 如果无关，直接输出：「本案与用户研究的{问题}无关，跳过。」然后在末尾输出元数据汇总块即可，不需要其他分析内容。\n"
    "- 如果有关，继续下一步。\n\n"
    "第二步（仅相关案例）：\n"
    "1. 分析本案的全部争议焦点和裁判要旨\n"
    "2. 但只详细输出与用户查询问题直接相关的争议焦点和裁判要旨，其他内容简要提及即可\n"
    "3. 给出针对用户查询问题的明确结论\n\n"
    "## 输出格式要求\n"
    "- 如果用户提供了案号、审理法院等元数据，请使用这些信息，不要编造\n"
    "- 使用专业但易懂的语言\n"
    "- 使用清晰的结构化格式\n\n"
    "## 元数据汇总（必须输出，不可省略）\n"
    "在分析内容之后，必须输出以下结构化数据块（用于后续汇总）：\n"
    "```\n"
    "【案例元数据汇总】\n"
    "案号：{案号}\n"
    "案由：{案由}\n"
    "审理法院：{审理法院}\n"
    "法官：{法官}\n"
    "书记员：{书记员}\n"
    "与研究问题相关：是/否\n"
    "结论：{针对用户查询问题的一句话结论}\n"
    "```\n"
    "注意：元数据汇总块中的字段必须从文档中提取，不要编造。如果某字段在文档中找不到，填写「未注明」。"
)
METADATA_BLOCK_RE = __import__("re").compile(
    r"【案例元数据汇总】\s*\n([\s\S]*?)(?:\n```|```\s*\Z|\Z)",
)
METADATA_FIELD_RE = __import__("re").compile(r"^(案号|案由|审理法院|法官|书记员|与研究问题相关|结论)\s*[：:]\s*(.+)$", __import__("re").MULTILINE)


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
                                "content": (
                                    f"{case_info}用户研究问题：{job.prompt}\n\n"
                                    f"以下是从文件「{item.file_name}」中提取的内容：\n\n{text}\n\n"
                                    "请先判断本案是否与用户研究问题相关。如无关，直接说明无关并跳过；如有关，请进行分析。"
                                    "分析完成后，必须在末尾输出【案例元数据汇总】块。"
                                ),
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
            summary = await _generate_summary(job_id, job.prompt, completed_items)
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
    job_id: UUID,
    prompt: str,
    completed_items: list[BatchJobItem],
) -> str:
    """从每个案例的分析结果中提取元数据汇总块，生成 CSV 文件并返回统计摘要。"""
    import csv
    import io

    from django.core.files.base import ContentFile

    csv_rows: list[dict[str, str]] = []
    missing_count = 0

    for item in completed_items:
        if not item.result:
            continue

        # 提取【案例元数据汇总】块
        block_match = METADATA_BLOCK_RE.search(item.result)
        if not block_match:
            missing_count += 1
            csv_rows.append({
                "文件名": item.file_name,
                "案号": "",
                "案由": "",
                "审理法院": "",
                "法官": "",
                "书记员": "",
                "与研究问题相关": "",
                "结论": "未提取到元数据汇总块",
            })
            continue

        block_text = block_match.group(1).strip()
        fields: dict[str, str] = {}
        for field_match in METADATA_FIELD_RE.finditer(block_text):
            fields[field_match.group(1).strip()] = field_match.group(2).strip()

        csv_rows.append({
            "文件名": item.file_name,
            "案号": fields.get("案号", "未注明"),
            "案由": fields.get("案由", "未注明"),
            "审理法院": fields.get("审理法院", "未注明"),
            "法官": fields.get("法官", "未注明"),
            "书记员": fields.get("书记员", "未注明"),
            "与研究问题相关": fields.get("与研究问题相关", "未注明"),
            "结论": fields.get("结论", "未注明"),
        })

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

    summary_text += f"\n汇总表已生成为 CSV 文件，可点击下载。\n"

    if missing_count:
        summary_text += f"\n> 注意：有 {missing_count} 个案例未提取到元数据汇总块，可能是分析结果格式不符合预期。\n"

    return summary_text
