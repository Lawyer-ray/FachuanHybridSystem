from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.core.filesystem.upload_paths import DatedUUIDPath


class SolutionTaskStatus(models.TextChoices):
    PENDING = "pending", "待执行"
    RESEARCHING = "researching", "检索中"
    GENERATING = "generating", "生成中"
    COMPLETED = "completed", "已完成"
    PARTIAL = "partial", "部分完成"
    FAILED = "failed", "失败"


class SolutionTask(models.Model):
    case_summary = models.TextField(verbose_name="案情简述")
    keyword = models.CharField(max_length=255, blank=True, verbose_name="检索关键词")
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.PROTECT,
        related_name="solution_tasks",
        verbose_name="站点账号",
    )
    research_task = models.ForeignKey(
        "legal_research.LegalResearchTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solution_tasks",
        verbose_name="案例检索任务",
    )
    status = models.CharField(
        max_length=16,
        choices=SolutionTaskStatus.choices,
        default=SolutionTaskStatus.PENDING,
        verbose_name="状态",
    )
    progress = models.PositiveIntegerField(default=0, verbose_name="进度")
    message = models.CharField(max_length=255, blank=True, verbose_name="状态说明")
    error = models.TextField(blank=True, verbose_name="错误信息")
    llm_model = models.CharField(max_length=128, blank=True, verbose_name="LLM模型")
    html_content = models.TextField(blank=True, verbose_name="HTML方案")
    pdf_file = models.FileField(
        upload_to=DatedUUIDPath("legal_solution"),
        max_length=255,
        null=True,
        blank=True,
        verbose_name="PDF文件",
    )
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solution_tasks",
        verbose_name="创建人",
    )
    q_task_id = models.CharField(max_length=64, blank=True, verbose_name="队列任务ID")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "法律服务方案"
        verbose_name_plural = "法律服务方案"
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.id} | {self.case_summary[:30]} | {self.status}"
