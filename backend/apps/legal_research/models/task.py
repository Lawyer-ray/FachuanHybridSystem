from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from django.db import models

class LegalResearchTaskStatus(models.TextChoices):
    PENDING = "pending", "待执行"
    QUEUED = "queued", "排队中"
    RUNNING = "running", "执行中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"

class LegalResearchSearchMode(models.TextChoices):
    EXPANDED = "expanded", "扩展检索"
    SINGLE = "single", "单检索"

class LegalResearchTask(models.Model):
    legacy_uuid = models.UUIDField(default=uuid4, editable=False, db_index=True, verbose_name="历史UUID")
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legal_research_tasks",
        verbose_name="创建人",
    )
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.PROTECT,
        related_name="legal_research_tasks",
        verbose_name="站点账号",
    )

    source = models.CharField(max_length=32, default="weike", verbose_name="数据源")
    search_url = models.URLField(max_length=2000, blank=True, verbose_name="WKInfo搜索URL")
    keyword = models.CharField(max_length=255, verbose_name="检索关键词")
    # 高级检索：JSON 数组，每项 {"field": "courtOpinion", "keyword": "逾期利息", "op": "AND"}
    # field 可选值：fullText / title / causeOfAction / courtOpinion / judgmentResult / disputeFocus / caseNumber
    # 为空时使用 keyword 字段做全文检索
    advanced_query = models.JSONField(
        default=list,
        blank=True,
        verbose_name="高级检索条件",
        help_text='JSON 数组，例如：[{"field":"courtOpinion","keyword":"逾期利息","op":"AND"}]',
    )
    court_filter = models.CharField(max_length=128, blank=True, verbose_name="法院筛选")
    cause_of_action_filter = models.CharField(max_length=128, blank=True, verbose_name="案由筛选")
    date_from = models.CharField(max_length=10, blank=True, verbose_name="裁判日期起")
    date_to = models.CharField(max_length=10, blank=True, verbose_name="裁判日期止")
    case_summary = models.TextField(verbose_name="案情简述")
    search_mode = models.CharField(
        max_length=16,
        choices=LegalResearchSearchMode.choices,
        default=LegalResearchSearchMode.EXPANDED,
        verbose_name="检索模式",
    )
    target_count = models.PositiveIntegerField(default=3, verbose_name="目标案例数")
    max_candidates = models.PositiveIntegerField(default=100, verbose_name="最大扫描案例数")
    min_similarity_score = models.FloatField(default=0.9, verbose_name="最低相似度")

    status = models.CharField(
        max_length=16,
        choices=LegalResearchTaskStatus.choices,
        default=LegalResearchTaskStatus.PENDING,
        verbose_name="状态",
    )
    progress = models.PositiveIntegerField(default=0, verbose_name="进度百分比")
    scanned_count = models.PositiveIntegerField(default=0, verbose_name="已扫描数")
    matched_count = models.PositiveIntegerField(default=0, verbose_name="已命中数")
    candidate_count = models.PositiveIntegerField(default=0, verbose_name="候选总数")

    message = models.CharField(max_length=255, blank=True, verbose_name="状态说明")
    error = models.TextField(blank=True, verbose_name="错误信息")

    llm_backend = models.CharField(max_length=64, default="", verbose_name="LLM后端")
    llm_model = models.CharField(max_length=128, blank=True, verbose_name="LLM模型")
    llm_scoring_concurrency = models.PositiveIntegerField(
        default=5,
        verbose_name="LLM评分并发数",
        help_text="同时并发的 LLM 评分线程数。默认 5，kimi26 模型建议 100。",
    )
    q_task_id = models.CharField(max_length=64, blank=True, verbose_name="DjangoQ任务ID")

    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "案例检索任务"
        verbose_name_plural = "案例检索任务"
        indexes: ClassVar = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.id} | {self.keyword} | {self.status}"
