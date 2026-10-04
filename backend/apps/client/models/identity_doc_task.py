"""证件识别异步任务轻量记录（安全修复：轮询归属校验的数据载体）。

此前 submit 端点直接返回 Django-Q 原始 task_id，轮询端点按 Q id 直查
队列无归属校验——持 Q id 者可读他人证件 OCR 结果（PII）。本模型让
提交/轮询两端点走「业务记录 id 对外、Q id 内部关联」模式
（参照 legal_solution.SolutionTask.q_task_id）。

轻量内部记录：不注册 admin，不承载文件。
"""

from __future__ import annotations

from django.db import models


class ClientIdentityDocParseTask(models.Model):
    """证件识别异步任务的提交记录（q_task_id 关联 + 归属人）。"""

    id: int
    created_by_id: int

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    q_task_id = models.CharField(
        "队列任务ID",
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Django-Q 任务 ID（对外仅暴露本记录 id，Q id 仅内部反查用）",
    )
    doc_type = models.CharField("证件类型", max_length=50, blank=True, default="")
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_identity_doc_parse_tasks",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "证件识别任务"
        verbose_name_plural = "证件识别任务"

    def __str__(self) -> str:
        return f"#{self.id} {self.doc_type} ({self.get_status_display()})"
