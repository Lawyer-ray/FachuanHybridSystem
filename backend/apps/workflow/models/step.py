"""步骤执行记录"""

from __future__ import annotations

from django.db import models


class StepExecution(models.Model):
    """步骤执行记录（由 Temporal Activity 回写）"""

    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        WAITING = "waiting"
        SKIPPED = "skipped"

    workflow_run = models.ForeignKey(
        "workflow.WorkflowRun",
        on_delete=models.CASCADE,
        related_name="step_executions",
        verbose_name="工作流运行",
    )
    step_id = models.CharField(max_length=100, verbose_name="步骤 ID")
    step_name = models.CharField(max_length=200, verbose_name="步骤名称")
    step_type = models.CharField(max_length=20, verbose_name="步骤类型")
    status = models.CharField(max_length=20, choices=Status.choices, verbose_name="状态")
    input_data = models.JSONField(default=dict, blank=True, verbose_name="输入数据")
    output_data = models.JSONField(null=True, blank=True, verbose_name="输出数据")
    error_message = models.TextField(null=True, blank=True, verbose_name="错误信息")
    attempts = models.IntegerField(default=0, verbose_name="尝试次数")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        ordering = ["started_at"]
        unique_together = [("workflow_run", "step_id")]
        verbose_name = "步骤执行"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.step_name} ({self.get_status_display()})"
