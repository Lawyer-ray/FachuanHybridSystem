"""工作流运行实例"""

from __future__ import annotations

from django.db import models


class WorkflowRun(models.Model):
    """一次 workflow 运行实例"""

    class Status(models.TextChoices):
        RUNNING = "running"
        WAITING_HUMAN = "waiting_human"
        WAITING_EVENT = "waiting_event"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"
        TIMED_OUT = "timed_out"

    template = models.ForeignKey(
        "workflow.WorkflowTemplate",
        on_delete=models.PROTECT,
        related_name="runs",
        verbose_name="流程模板",
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.PROTECT,
        related_name="workflow_runs",
        verbose_name="案件",
    )
    temporal_workflow_id = models.CharField(max_length=200, unique=True, verbose_name="Temporal Workflow ID")
    temporal_run_id = models.CharField(max_length=200, verbose_name="Temporal Run ID")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
        verbose_name="状态",
    )
    current_step_id = models.CharField(max_length=100, blank=True, default="", verbose_name="当前步骤")
    result = models.JSONField(null=True, blank=True, verbose_name="运行结果")
    created_by = models.ForeignKey(
        "organization.Lawyer",
        null=True,
        on_delete=models.SET_NULL,
        related_name="initiated_workflows",
        verbose_name="发起人",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="启动时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "工作流运行"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["case", "status"]),
            models.Index(fields=["template"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.template.name} - {self.case.name} ({self.get_status_display()})"
