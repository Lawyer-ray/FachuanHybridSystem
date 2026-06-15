"""工作流模板"""

from __future__ import annotations

from django.db import models


class WorkflowTemplate(models.Model):
    """流程模板"""

    class Category(models.TextChoices):
        LITIGATION = "litigation", "诉讼"
        PRESERVATION = "preservation", "保全"
        ENFORCEMENT = "enforcement", "执行"

    name = models.CharField(max_length=200, unique=True, verbose_name="模板名称")
    slug = models.SlugField(unique=True, max_length=100, verbose_name="标识")
    category = models.CharField(max_length=20, choices=Category.choices, verbose_name="类别")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    temporal_workflow_name = models.CharField(
        max_length=200,
        verbose_name="Temporal Workflow 名称",
        help_text="如 'SalesContractDisputeWorkflow'",
    )
    steps_schema = models.JSONField(
        verbose_name="步骤定义",
        help_text='[{"id":"collect_facts","name":"收集案件事实","type":"activity",...}]',
    )
    is_active = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "流程模板"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.name
