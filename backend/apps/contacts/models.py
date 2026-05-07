from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.core.models.enums import CaseStage, ContactRole


class CaseContact(models.Model):
    """案件工作人员联系方式"""

    id: int

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name=_("案件"),
    )
    authority = models.ForeignKey(
        "cases.SupervisingAuthority",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contacts",
        verbose_name=_("主管机关"),
    )
    name = models.CharField(max_length=100, verbose_name=_("姓名"))
    role = models.CharField(
        max_length=32,
        choices=ContactRole.choices,
        default=ContactRole.OTHER,
        verbose_name=_("角色"),
    )
    phone = models.CharField(max_length=32, blank=True, null=True, verbose_name=_("电话"))
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("收件地址"))
    stage = models.CharField(
        max_length=64,
        choices=CaseStage.choices,
        blank=True,
        null=True,
        verbose_name=_("所属阶段"),
    )
    note = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("案件工作人员")
        verbose_name_plural = _("案件工作人员")
        ordering: ClassVar = ["created_at"]
        indexes: ClassVar = [
            models.Index(fields=["case"]),
            models.Index(fields=["authority"]),
            models.Index(fields=["stage"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self) -> str:
        role_display = self.get_role_display()
        return f"{self.name} ({role_display})"
