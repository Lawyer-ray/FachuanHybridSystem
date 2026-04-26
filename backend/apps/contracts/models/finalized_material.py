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
    ARCHIVE_DOCUMENT = "archive_document", _("归档文书")
    SUPERVISION_CARD = "supervision_card", _("监督卡")
    AUTHORIZATION_MATERIAL = "authorization_material", _("授权委托材料")
    CASE_MATERIAL = "case_material", _("案件材料同步")
    ARCHIVE_UPLOAD = "archive_upload", _("归档上传")


class FinalizedMaterial(models.Model):
    """归档材料模型，存储上传的 PDF 文件元数据。"""

    id: int
    contract_id: int
    contract: models.ForeignKey[Contract] = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="finalized_materials",
        verbose_name=_("合同"),
    )
    file_path: models.CharField = models.CharField(max_length=500, verbose_name=_("文件路径"))
    original_filename: models.CharField = models.CharField(max_length=255, verbose_name=_("原始文件名"))
    category: models.CharField = models.CharField(
        max_length=32,
        choices=MaterialCategory.choices,
        default=MaterialCategory.ARCHIVE_DOCUMENT,
        verbose_name=_("材料分类"),
    )
    uploaded_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))
    remark: models.TextField = models.TextField(blank=True, default="", verbose_name=_("备注"))
    order: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name=_("排序"))
    archive_item_code: models.CharField = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("归档清单编号"),
        help_text=_("关联归档检查清单的标识符，如 'nl_1'、'lt_6'"),
    )
    content_hash: models.CharField = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("内容哈希"),
        help_text=_("SHA-256, 用于去重"),
        db_index=True,
    )

    class Meta:
        ordering: ClassVar = ["order", "-uploaded_at"]
        verbose_name = _("归档材料")
        verbose_name_plural = _("归档材料")
        indexes: ClassVar = [
            models.Index(fields=["contract", "order", "-uploaded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_category_display()})"
