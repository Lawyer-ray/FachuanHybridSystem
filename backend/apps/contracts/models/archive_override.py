"""归档文书占位符覆盖值模型

允许用户对特定合同+特定归档模板的占位符值进行手动覆盖，
覆盖后的值在预览和生成时优先使用。
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ArchivePlaceholderOverride(models.Model):
    """归档文书占位符覆盖值

    存储 用户对 某合同+某归档模板 的占位符手动覆盖值。
    每个合同+模板组合最多一条记录，overrides 为 JSONField 存储 {key: value}。
    """

    contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="archive_overrides",
        verbose_name=_("合同"),
    )
    template_subtype = models.CharField(
        max_length=50,
        verbose_name=_("归档模板子类型"),
        help_text=_("DocumentArchiveSubType 值，如 case_cover、closing_archive_register"),
    )
    overrides = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("覆盖值"),
        help_text=_("用户手动覆盖的占位符键值对，如 {'主办律师姓名': '张三'}"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("归档占位符覆盖")
        verbose_name_plural = _("归档占位符覆盖")
        unique_together = [("contract", "template_subtype")]
        indexes = [
            models.Index(fields=["contract", "template_subtype"]),
        ]

    def __str__(self) -> str:
        return f"Contract#{self.contract_id} {self.template_subtype}: {len(self.overrides)} overrides"
