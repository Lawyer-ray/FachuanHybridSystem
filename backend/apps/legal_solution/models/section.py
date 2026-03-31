from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class SectionType(models.TextChoices):
    CASE_ANALYSIS = "case_analysis", _("案情分析")
    LEGAL_RELATION = "legal_relation", _("法律关系认定")
    DISPUTE_FOCUS = "dispute_focus", _("争议焦点")
    SIMILAR_CASES = "similar_cases", _("类案参考")
    LITIGATION_STRATEGY = "litigation_strategy", _("诉讼策略建议")
    RISK_ASSESSMENT = "risk_assessment", _("风险评估")
    COST_ESTIMATE = "cost_estimate", _("费用预估")


SECTION_ORDER = [
    SectionType.CASE_ANALYSIS,
    SectionType.LEGAL_RELATION,
    SectionType.DISPUTE_FOCUS,
    SectionType.SIMILAR_CASES,
    SectionType.LITIGATION_STRATEGY,
    SectionType.RISK_ASSESSMENT,
    SectionType.COST_ESTIMATE,
]

SECTION_TITLES = {
    SectionType.CASE_ANALYSIS: "案情分析",
    SectionType.LEGAL_RELATION: "法律关系认定",
    SectionType.DISPUTE_FOCUS: "争议焦点",
    SectionType.SIMILAR_CASES: "类案参考",
    SectionType.LITIGATION_STRATEGY: "诉讼策略建议",
    SectionType.RISK_ASSESSMENT: "风险评估",
    SectionType.COST_ESTIMATE: "费用预估",
}


class SectionStatus(models.TextChoices):
    PENDING = "pending", _("待生成")
    GENERATING = "generating", _("生成中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")


class SolutionSection(models.Model):
    task = models.ForeignKey(
        "legal_solution.SolutionTask",
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name=_("方案任务"),
    )
    section_type = models.CharField(
        max_length=32,
        choices=SectionType.choices,
        verbose_name=_("段落类型"),
    )
    order = models.PositiveIntegerField(default=0, verbose_name=_("排序"))
    title = models.CharField(max_length=128, verbose_name=_("标题"))
    content = models.TextField(blank=True, verbose_name=_("内容(markdown)"))
    html_content = models.TextField(blank=True, verbose_name=_("HTML内容"))
    prompt_used = models.TextField(blank=True, verbose_name=_("使用的Prompt"))
    user_feedback = models.TextField(blank=True, verbose_name=_("用户调整意见"))
    version = models.PositiveIntegerField(default=1, verbose_name=_("版本号"))
    status = models.CharField(
        max_length=16,
        choices=SectionStatus.choices,
        default=SectionStatus.PENDING,
        verbose_name=_("状态"),
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("扩展信息"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("方案段落")
        verbose_name_plural = _("方案段落")
        ordering: ClassVar = ["order"]
        unique_together: ClassVar = [("task", "section_type")]

    def __str__(self) -> str:
        return f"{self.task_id} | {self.get_section_type_display()} | v{self.version}"
