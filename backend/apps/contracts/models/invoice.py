"""发票模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .payment import ContractPayment


class Invoice(models.Model):
    """与某条 ContractPayment 关联的发票文件。"""

    id: int
    payment_id: int
    payment = models.ForeignKey(
        ContractPayment,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name=_("收款记录"),
    )
    file_path = models.CharField(max_length=500, verbose_name=_("文件路径"))
    original_filename = models.CharField(max_length=255, verbose_name=_("原始文件名"))
    remark = models.TextField(blank=True, default="", verbose_name=_("备注"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))
    
    # 发票识别结果字段（可选）
    invoice_code = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("发票代码")
    )
    invoice_number = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("发票号码")
    )
    invoice_date = models.DateField(null=True, blank=True, verbose_name=_("开票日期"))
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("金额"),
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("税额"),
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("价税合计"),
    )

    class Meta:
        ordering: ClassVar = ["-uploaded_at"]
        verbose_name = _("发票")
        verbose_name_plural = _("发票")
        indexes: ClassVar = [
            models.Index(fields=["payment", "-uploaded_at"]),
        ]

    def __str__(self) -> str:
        return self.original_filename or f"发票 #{self.id}"
