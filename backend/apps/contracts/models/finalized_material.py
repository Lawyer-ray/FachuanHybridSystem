"""Module for finalized material."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract

if TYPE_CHECKING:
    pass


class MaterialCategory(models.TextChoices):
    CONTRACT_ORIGINAL = "contract_original", _("合同正本")
    SUPPLEMENTARY_AGREEMENT = "supplementary_agreement", _("补充协议")
    INVOICE = "invoice", _("发票")


class FinalizedMaterial(models.Model):
    """定稿材料模型，存储上传的 PDF 文件元数据。"""

    id: int
    contract_id: int
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="finalized_materials",
        verbose_name=_("合同"),
    )
    file_path = models.CharField(max_length=500, verbose_name=_("文件路径"))
    original_filename = models.CharField(max_length=255, verbose_name=_("原始文件名"))
    category = models.CharField(
        max_length=32,
        choices=MaterialCategory.choices,
        default=MaterialCategory.INVOICE,
        verbose_name=_("材料分类"),
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))
    remark = models.TextField(blank=True, default="", verbose_name=_("备注"))
    order = models.PositiveIntegerField(default=0, verbose_name=_("排序"))

    class Meta:
        ordering: ClassVar = ["order", "-uploaded_at"]
        verbose_name = _("定稿材料")
        verbose_name_plural = _("定稿材料")
        indexes: ClassVar = [
            models.Index(fields=["contract", "order", "-uploaded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_category_display()})"
