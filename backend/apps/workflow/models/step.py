"""步骤执行记录"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
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
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    attempts = models.IntegerField(default=0, verbose_name="尝试次数")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    # 审批留痕（安全审计）：gate 步骤被人工审批（通过/拒绝）时记录操作人与时间。
    # 系统自动执行（Temporal worker 回写）不填写；MCP 无用户上下文时亦为空。
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="审批/执行人",
    )
    acted_at = models.DateTimeField(null=True, blank=True, verbose_name="审批/执行时间")

    class Meta:
        ordering = ["started_at"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["workflow_run", "step_id"], name="uniq_step_execution_run_step"),
        ]
        verbose_name = "步骤执行"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.step_name} ({self.get_status_display()})"
