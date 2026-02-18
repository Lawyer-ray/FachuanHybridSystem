"""Module for proxy matter rule."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.enums import CaseStage, LegalStatus, SimpleCaseType


class ProxyMatterRule(models.Model):
    id: int

    class LegalStatusMatchMode(models.TextChoices):
        ANY = "any", _("任意匹配")
        ALL = "all", _("全部包含")
        EXACT = "exact", _("完全一致")

    case_type = models.CharField(
        max_length=32,
        choices=SimpleCaseType.choices,
        null=True,
        blank=True,
        verbose_name=_("案件类型"),
        help_text=_("为空表示匹配任意案件类型"),
    )
    case_stage = models.CharField(
        max_length=64,
        choices=CaseStage.choices,
        null=True,
        blank=True,
        verbose_name=_("当前阶段"),
        help_text=_("为空表示匹配任意案件阶段"),
    )
    legal_statuses: Any = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("我方诉讼地位"),
        help_text=_("可单选或多选;为空表示匹配任意诉讼地位"),
    )
    legal_status_match_mode = models.CharField(
        max_length=16,
        choices=LegalStatusMatchMode.choices,
        default=LegalStatusMatchMode.ANY,
        verbose_name=_("诉讼地位匹配模式"),
    )
    items_text = models.TextField(
        blank=True,
        default="",
        verbose_name=_("代理事项条目"),
        help_text=_("每行一条代理事项"),
    )
    priority = models.PositiveIntegerField(default=100, verbose_name=_("优先级"))
    is_active = models.BooleanField(default=True, verbose_name=_("是否启用"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("代理事项规则")
        verbose_name_plural = _("代理事项规则")
        indexes: ClassVar = [
            models.Index(fields=["is_active", "priority"]),
            models.Index(fields=["case_type", "case_stage", "is_active"]),
        ]

    def __str__(self) -> str:
        case_type = self.get_case_type_display() if self.case_type else "任意类型"
        case_stage = self.get_case_stage_display() if self.case_stage else "任意阶段"
        legal_statuses = self.get_legal_statuses_display() or "任意地位"
        mode = self.get_legal_status_match_mode_display() or ""
        return f"{case_type}-{case_stage}-{legal_statuses}-{mode}"

    def get_legal_statuses_display(self) -> str:
        choices = dict(LegalStatus.choices)
        statuses = self.legal_statuses or []
        labels = [str(choices.get(code, code)) for code in statuses]
        return "、".join([x for x in labels if x])
