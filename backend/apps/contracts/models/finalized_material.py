"""Module for finalized material."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models

from .contract import Contract

if TYPE_CHECKING:
    pass

class MaterialCategory(models.TextChoices):
    CONTRACT_ORIGINAL = "contract_original", "合同正本"
    SUPPLEMENTARY_AGREEMENT = "supplementary_agreement", "补充协议"
    INVOICE = "invoice", "发票"
    ARCHIVE_DOCUMENT = "archive_document", "归档文书"
    SUPERVISION_CARD = "supervision_card", "监督卡"
    AUTHORIZATION_MATERIAL = "authorization_material", "授权委托材料"
    CASE_MATERIAL = "case_material", "案件材料同步"
    ARCHIVE_UPLOAD = "archive_upload", "归档上传"

class FinalizedMaterial(models.Model):
    """归档材料模型，存储上传的 PDF 文件元数据。"""

    id: int
    contract_id: int
    contract: models.ForeignKey[Contract] = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="finalized_materials",
        verbose_name="合同",
    )
    file_path: models.CharField = models.CharField(max_length=500, verbose_name="文件路径", db_index=True)
    original_filename: models.CharField = models.CharField(max_length=255, verbose_name="原始文件名")
    category: models.CharField = models.CharField(
        max_length=32,
        choices=MaterialCategory.choices,
        default=MaterialCategory.ARCHIVE_DOCUMENT,
        verbose_name="材料分类",
    )
    uploaded_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")
    remark: models.TextField = models.TextField(blank=True, default="", verbose_name="备注")
    order: models.PositiveIntegerField = models.PositiveIntegerField(default=0, verbose_name="排序")
    archive_item_code: models.CharField = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="归档清单编号",
        help_text="关联归档检查清单的标识符，如 'nl_1'、'lt_6'",
    )
    content_hash: models.CharField = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="内容哈希",
        help_text="SHA-256, 用于去重",
        db_index=True,
    )

    class Meta:
        ordering: ClassVar = ["order", "-uploaded_at"]
        verbose_name = "归档材料"
        verbose_name_plural = "归档材料"
        indexes: ClassVar = [
            models.Index(fields=["contract", "order", "-uploaded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_category_display()})"
