from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_RESEARCH_POLL_INTERVAL = 10  # 秒
_RESEARCH_TIMEOUT = 600  # 10分钟


def run_solution_task(task_id: int) -> dict[str, Any]:
    """django-q 异步任务主入口：检索 → 生成方案 → 组装 HTML。"""
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

    from django.utils import timezone

    from apps.legal_research.models.task import LegalResearchTaskStatus
    from apps.legal_research.schemas import LegalResearchTaskCreateIn
    from apps.legal_research.services.keywords import normalize_keyword_query
    from apps.legal_research.services.task_service import LegalResearchTaskService
    from apps.legal_solution.models import SolutionTask, SolutionTaskStatus
    from apps.legal_solution.services.html_renderer import HtmlRenderer
    from apps.legal_solution.services.solution_generator import SolutionGenerator

    task = SolutionTask.objects.select_related("credential", "research_task").get(id=task_id)
    task.started_at = timezone.now()
    task.save(update_fields=["started_at", "updated_at"])

    try:
        # ── 阶段1: 自动提取关键词 ──
        if not task.keyword:
            from apps.legal_research.services.executor import LegalResearchExecutor

            elements = LegalResearchExecutor._extract_legal_elements(case_summary=task.case_summary)
            if elements:
                queries = LegalResearchExecutor._build_element_based_queries(elements)
                task.keyword = normalize_keyword_query(queries[0] if queries else task.case_summary[:50])
            else:
                task.keyword = normalize_keyword_query(task.case_summary[:80])
            task.save(update_fields=["keyword", "updated_at"])

        # ── 阶段2: 创建并触发案例检索 ──
        task.status = SolutionTaskStatus.RESEARCHING
        task.message = "正在检索类案..."
        task.save(update_fields=["status", "message", "updated_at"])

        if task.research_task_id is None:
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

            admin_user = type("_AdminUser", (), {"is_superuser": True, "id": None, "law_firm_id": None})()
            research_task = research_service.create_task(payload=payload, user=admin_user)
            task.research_task = research_task
            task.save(update_fields=["research_task", "updated_at"])

        # ── 阶段3: 等待检索完成 ──
        deadline = time.time() + _RESEARCH_TIMEOUT
        while time.time() < deadline:
            task.research_task.refresh_from_db()  # type: ignore[union-attr]
            status = task.research_task.status  # type: ignore[union-attr]
            if status in (
                LegalResearchTaskStatus.COMPLETED,
                LegalResearchTaskStatus.FAILED,
                LegalResearchTaskStatus.CANCELLED,
            ):
                break
            time.sleep(_RESEARCH_POLL_INTERVAL)
        else:
            logger.warning("案例检索超时，继续生成方案（可能无类案）", extra={"task_id": task_id})

        # ── 阶段4: 分段生成方案 ──
        task.status = SolutionTaskStatus.GENERATING
        task.message = "正在生成法律服务方案..."
        task.save(update_fields=["status", "message", "updated_at"])

        generator = SolutionGenerator()
        generator.generate(task)

        # ── 阶段5: 组装 HTML ──
        renderer = HtmlRenderer()
        task.html_content = renderer.render(task)

        # 判断是否有段落失败
        from apps.legal_solution.models import SectionStatus

        failed_count = task.sections.filter(status=SectionStatus.FAILED).count()
        task.status = SolutionTaskStatus.PARTIAL if failed_count else SolutionTaskStatus.COMPLETED
        task.progress = 100
        task.message = f"方案生成完成（{failed_count} 段失败）" if failed_count else "方案生成完成"
        task.finished_at = timezone.now()
        task.save(update_fields=["html_content", "status", "progress", "message", "finished_at", "updated_at"])

        return {"task_id": task_id, "status": task.status}

    except Exception as exc:
        logger.exception("法律服务方案任务失败", extra={"task_id": task_id})
        task.status = SolutionTaskStatus.FAILED
        task.error = str(exc)
        task.message = "任务执行失败"
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "error", "message", "finished_at", "updated_at"])
        return {"task_id": task_id, "status": "failed", "error": str(exc)}
