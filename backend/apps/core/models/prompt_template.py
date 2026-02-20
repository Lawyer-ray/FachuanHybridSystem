"""
Prompt 模板数据模型

本模块定义 Prompt 模板的数据模型.
"""

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.infrastructure import CacheKeys, delete_cache_key


class PromptTemplate(models.Model):
    """Prompt 模板模型

    用于存储和管理 AI 对话的 Prompt 模板.
    """

    id: int
    name = models.CharField(max_length=100, unique=True, verbose_name=_("模板名称"))
    title = models.CharField(max_length=200, verbose_name=_("显示标题"))
    template = models.TextField(verbose_name=_("模板内容"))
    description = models.TextField(blank=True, verbose_name=_("模板描述"))
    variables = models.JSONField(default=list, verbose_name=_("变量列表"))
    category = models.CharField(default="general", max_length=50, verbose_name=_("分类"))
    is_active = models.BooleanField(default=True, verbose_name=_("启用"))
    version = models.CharField(default="1.0", max_length=20, verbose_name=_("版本"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("Prompt 模板")
        verbose_name_plural = _("Prompt 模板")
        db_table = "core_prompt_template"
        ordering: ClassVar = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.title} ({self.name})"

    def delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        name = self.name
        result = super().delete(using=using, keep_parents=keep_parents)
        delete_cache_key(CacheKeys.prompt_template(name))
        return result
