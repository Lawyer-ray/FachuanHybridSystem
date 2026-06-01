"""Module for template binding."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class BindingSource(models.TextChoices):
    """绑定来源"""

    AUTO_RECOMMENDED = "auto_recommended", "自动推荐"
    MANUAL_BOUND = "manual_bound", "手动绑定"


class CaseTemplateBinding(models.Model):
    """案件模板绑定关系"""

    id: int
    case = models.ForeignKey(
        "cases.Case", on_delete=models.CASCADE, related_name="template_bindings", verbose_name="案件"
    )
    template = models.ForeignKey(
        "documents.DocumentTemplate", on_delete=models.CASCADE, related_name="case_bindings", verbose_name="文书模板"
    )
    binding_source = models.CharField(
        max_length=20, choices=BindingSource.choices, default=BindingSource.AUTO_RECOMMENDED, verbose_name="绑定来源"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="绑定时间")

    class Meta:
        verbose_name = "案件模板绑定"
        verbose_name_plural = "案件模板绑定"
        unique_together: ClassVar = ["case", "template"]
        indexes: ClassVar = [
            models.Index(fields=["case", "binding_source"]),
            models.Index(fields=["template"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.template_id}-{self.binding_source}"
