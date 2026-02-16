"""Module for template binding."""

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class BindingSource(models.TextChoices):
    """绑定来源"""

    AUTO_RECOMMENDED = "auto_recommended", _("自动推荐")
    MANUAL_BOUND = "manual_bound", _("手动绑定")


class CaseTemplateBinding(models.Model):
    """案件模板绑定关系"""

    id: int
    case: Any = models.ForeignKey(
        "cases.Case", on_delete=models.CASCADE, related_name="template_bindings", verbose_name=_("案件")
    )
    template: Any = models.ForeignKey(
        "documents.DocumentTemplate", on_delete=models.CASCADE, related_name="case_bindings", verbose_name=_("文书模板")
    )
    binding_source: Any = models.CharField(
        max_length=20, choices=BindingSource.choices, default=BindingSource.AUTO_RECOMMENDED, verbose_name=_("绑定来源")
    )
    created_at: Any = models.DateTimeField(auto_now_add=True, verbose_name=_("绑定时间"))

    class Meta:
        verbose_name = _("案件模板绑定")
        verbose_name_plural = _("案件模板绑定")
        unique_together: ClassVar = ["case", "template"]
        indexes: ClassVar = [
            models.Index(fields=["case", "binding_source"]),
            models.Index(fields=["template"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.template_id}-{self.binding_source}"
