from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from apps.core.infrastructure.sync_async_bridge import run_coro_sync

logger = logging.getLogger(__name__)

_RESEARCH_POLL_INTERVAL = 2  # 秒（从 10s 降到 2s，减少 worker 空等时间）
_RESEARCH_TIMEOUT = 600  # 10分钟


def run_solution_task(task_id: int) -> dict[str, Any]:  # pragma: no cover
    """django-q 异步任务主入口：检索 → 生成方案 → 组装 HTML。

    Django-Q worker 同步调用任务函数（django_q.worker 直接 f(*args)），
    async 任务体经统一桥接消费；桥退出前清理 Django 连接。
    """
    return run_coro_sync(
        _run_solution_task_async(task_id),
        thread_name_prefix="legal-solution",
    )


async def _run_solution_task_async(task_id: int) -> dict[str, Any]:  # pragma: no cover
    """任务 async 体：ORM 走 aget/asave/acount，重 sync 服务经 asyncio.to_thread 隔离。"""
    from django.utils import timezone

    from apps.legal_research.models.task import LegalResearchTask, LegalResearchTaskStatus
    from apps.legal_research.schemas import LegalResearchTaskCreateIn
    from apps.legal_research.services.task.service import LegalResearchTaskService
    from apps.legal_solution.models import SolutionTask, SolutionTaskStatus
    from apps.legal_solution.services.html_renderer import HtmlRenderer
    from apps.legal_solution.services.solution_generator import SolutionGenerator

    task = await SolutionTask.objects.select_related("credential", "research_task").aget(id=task_id)
    task.started_at = timezone.now()
    await task.asave(update_fields=["started_at", "updated_at"])

    try:
        # ── 阶段1: 自动提取关键词 ──
        if not task.keyword:
            from apps.legal_research.services.keywords import normalize_keyword_query
            from apps.legal_research.services.task.executor import LegalResearchExecutor

            elements = await asyncio.to_thread(
                LegalResearchExecutor._extract_legal_elements, case_summary=task.case_summary
            )
            if elements:
                queries = await asyncio.to_thread(LegalResearchExecutor._build_element_based_queries, elements)
                task.keyword = normalize_keyword_query(queries[0] if queries else task.case_summary[:50])
            else:
                task.keyword = normalize_keyword_query(task.case_summary[:80])
            await task.asave(update_fields=["keyword", "updated_at"])

        # ── 阶段2: 创建并触发案例检索 ──
        task.status = SolutionTaskStatus.RESEARCHING
        task.message = "正在检索类案..."
        await task.asave(update_fields=["status", "message", "updated_at"])

        research_task_id = task.research_task_id
        if research_task_id is None:
            research_service = LegalResearchTaskService()
            payload = LegalResearchTaskCreateIn(
                credential_id=task.credential_id,
                keyword=task.keyword,
                case_summary=task.case_summary,
                target_count=3,
                max_candidates=60,
                min_similarity_score=0.88,
                llm_model=task.llm_model or "",
            )
            # 用超级用户权限创建（内部调用）
            from apps.organization.models import Lawyer

            admin_user = await Lawyer.objects.filter(is_superuser=True).afirst()
            if admin_user is None:
                raise RuntimeError("系统中没有超级用户，无法创建检索任务")
            research_task = await asyncio.to_thread(research_service.create_task, payload=payload, user=admin_user)
            task.research_task = research_task
            await task.asave(update_fields=["research_task", "updated_at"])
            research_task_id = research_task.pk

        # ── 阶段3: 等待检索完成 ──
        deadline = time.monotonic() + _RESEARCH_TIMEOUT
        while time.monotonic() < deadline:
            status = await (
                LegalResearchTask.objects.filter(pk=research_task_id).values_list("status", flat=True).afirst()
            )
            if status in (
                LegalResearchTaskStatus.COMPLETED,
                LegalResearchTaskStatus.FAILED,
                LegalResearchTaskStatus.CANCELLED,
            ):
                break
            await asyncio.sleep(_RESEARCH_POLL_INTERVAL)
        else:
            logger.warning("案例检索超时，继续生成方案（可能无类案）", extra={"task_id": task_id})

        # ── 阶段4: 分段生成方案 ──
        task.status = SolutionTaskStatus.GENERATING
        task.message = "正在生成法律服务方案..."
        await task.asave(update_fields=["status", "message", "updated_at"])

        await asyncio.to_thread(SolutionGenerator().generate, task)

        # ── 阶段5: 组装 HTML ──
        task.html_content = await asyncio.to_thread(HtmlRenderer().render, task)

        # 判断是否有段落失败
        from apps.legal_solution.models import SectionStatus

        failed_count = await task.sections.filter(status=SectionStatus.FAILED).acount()
        task.status = SolutionTaskStatus.PARTIAL if failed_count else SolutionTaskStatus.COMPLETED
        task.progress = 100
        task.message = f"方案生成完成（{failed_count} 段失败）" if failed_count else "方案生成完成"
        task.finished_at = timezone.now()
        await task.asave(update_fields=["html_content", "status", "progress", "message", "finished_at", "updated_at"])

        return {"task_id": task_id, "status": task.status}

    except Exception as exc:
        logger.exception("法律服务方案任务失败", extra={"task_id": task_id})
        task.status = SolutionTaskStatus.FAILED
        task.error = str(exc)
        task.message = "任务执行失败"
        task.finished_at = timezone.now()
        await task.asave(update_fields=["status", "error", "message", "finished_at", "updated_at"])
        return {"task_id": task_id, "status": "failed", "error": str(exc)}
