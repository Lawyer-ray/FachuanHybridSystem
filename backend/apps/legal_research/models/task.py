from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from django.db import models
from django.utils.translation import gettext_lazy as _


class LegalResearchTaskStatus(models.TextChoices):
    PENDING = "pending", _("待执行")
    QUEUED = "queued", _("排队中")
    RUNNING = "running", _("执行中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    CANCELLED = "cancelled", _("已取消")


class LegalResearchSearchMode(models.TextChoices):
    EXPANDED = "expanded", _("扩展检索")
    SINGLE = "single", _("单检索")


class LegalResearchTask(models.Model):
    legacy_uuid = models.UUIDField(default=uuid4, editable=False, db_index=True, verbose_name=_("历史UUID"))
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legal_research_tasks",
        verbose_name=_("创建人"),
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.PROTECT,
        related_name="legal_research_tasks",
        verbose_name=_("站点账号"),
    )

    source = models.CharField(max_length=32, default="weike", verbose_name=_("数据源"))
    keyword = models.CharField(max_length=255, verbose_name=_("检索关键词"))
    case_summary = models.TextField(verbose_name=_("案情简述"))
    search_mode = models.CharField(
        max_length=16,
        choices=LegalResearchSearchMode.choices,
        default=LegalResearchSearchMode.EXPANDED,
        verbose_name=_("检索模式"),
    )
    target_count = models.PositiveIntegerField(default=3, verbose_name=_("目标案例数"))
    max_candidates = models.PositiveIntegerField(default=100, verbose_name=_("最大扫描案例数"))
    min_similarity_score = models.FloatField(default=0.9, verbose_name=_("最低相似度"))

    status = models.CharField(
        max_length=16,
        choices=LegalResearchTaskStatus.choices,
        default=LegalResearchTaskStatus.PENDING,
        verbose_name=_("状态"),
    )
    progress = models.PositiveIntegerField(default=0, verbose_name=_("进度百分比"))
    scanned_count = models.PositiveIntegerField(default=0, verbose_name=_("已扫描数"))
    matched_count = models.PositiveIntegerField(default=0, verbose_name=_("已命中数"))
    candidate_count = models.PositiveIntegerField(default=0, verbose_name=_("候选总数"))

    message = models.CharField(max_length=255, blank=True, verbose_name=_("状态说明"))
    error = models.TextField(blank=True, verbose_name=_("错误信息"))

    llm_backend = models.CharField(max_length=64, default="siliconflow", verbose_name=_("LLM后端"))
    llm_model = models.CharField(max_length=128, blank=True, verbose_name=_("LLM模型"))
    q_task_id = models.CharField(max_length=64, blank=True, verbose_name=_("DjangoQ任务ID"))

    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("案例检索任务")
        verbose_name_plural = _("案例检索任务")
        indexes: ClassVar = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.id} | {self.keyword} | {self.status}"
