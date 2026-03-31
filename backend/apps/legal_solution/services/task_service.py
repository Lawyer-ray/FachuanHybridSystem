from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.core.interfaces import ServiceLocator
from apps.core.llm.config import LLMConfig
from apps.legal_solution.models import SolutionTask, SolutionTaskStatus
from apps.legal_solution.services.html_renderer import HtmlRenderer
from apps.legal_solution.services.solution_generator import SolutionGenerator

logger = logging.getLogger(__name__)


class SolutionTaskService:
    CREATE_PENDING_MESSAGE = "任务已创建，等待调度"
    QUEUED_MESSAGE = "任务已提交到队列"

    def create_and_dispatch(
        self,
        *,
        case_summary: str,
        credential: Any,
        user: Any,
        llm_model: str = "",
    ) -> SolutionTask:
        task = SolutionTask.objects.create(
            case_summary=case_summary.strip(),
            credential=credential,
            created_by=user if hasattr(user, "id") else None,
            status=SolutionTaskStatus.PENDING,
            message=self.CREATE_PENDING_MESSAGE,
            llm_model=(llm_model.strip() if llm_model else LLMConfig.get_default_model()),
        )
        self._dispatch(task)
        return task

    def regenerate_section(self, *, section_id: int, feedback: str) -> None:
        from apps.legal_solution.models import SectionStatus, SolutionSection

        section = SolutionSection.objects.select_related("task").get(id=section_id)
        if section.status == SectionStatus.GENERATING:
            raise ValueError("该段落正在生成中，请稍后再试")

        generator = SolutionGenerator()
        generator.regenerate_section(section, feedback)

        # 重新组装 HTML，清除旧 PDF
        task = section.task
        renderer = HtmlRenderer()
        task.html_content = renderer.render(task)
        task.pdf_file = None
        task.save(update_fields=["html_content", "pdf_file", "updated_at"])

    def _dispatch(self, task: SolutionTask) -> None:
        try:
            q_task_id = ServiceLocator.get_task_submission_service().submit(
                "apps.legal_solution.tasks.run_solution_task",
                args=[task.id],
                task_name=f"legal_solution_{task.id}",
                timeout=3600,
            )
            task.q_task_id = q_task_id
            task.status = SolutionTaskStatus.PENDING
            task.message = self.QUEUED_MESSAGE
            task.save(update_fields=["q_task_id", "status", "message", "updated_at"])
        except Exception as exc:
            task.status = SolutionTaskStatus.FAILED
            task.error = str(exc)
            task.message = "任务提交失败"
            task.save(update_fields=["status", "error", "message", "updated_at"])
            logger.error("法律服务方案任务提交失败: %s", exc, extra={"task_id": task.id})
