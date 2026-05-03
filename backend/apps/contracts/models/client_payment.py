"""客户回款记录模型"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from apps.cases.models import Case

    from .contract import Contract


class ClientPaymentRecord(models.Model):
    """客户回款记录"""

    id: int
    contract: models.ForeignKey[Contract | None, Contract] = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        related_name="client_payment_records",
        verbose_name=_("关联合同"),
    )
    case: models.ForeignKey[Any | None, Any] = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_payment_records",
        verbose_name=_("关联案件"),
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name=_("回款金额"),
    )
    image_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("凭证图片路径"),
    )
    note = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("备注"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("更新时间"),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("客户回款")
        verbose_name_plural = _("客户回款")
        ordering = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["contract"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract.name} - ¥{self.amount}"
