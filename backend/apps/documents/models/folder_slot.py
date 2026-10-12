"""
法律文书生成系统 - 文件夹槽位模型

槽位是文书落位的语义锚点：文书模板声明自己占据哪个槽位，
文件夹模板的 structure 节点通过 kind 标记自己提供哪个槽位，
生成时刻按槽位解析出实际路径（不落库）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django_lifecycle import LifecycleModel

from apps.documents.models.choices import FolderSlotCategory

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .document_template import DocumentTemplate


class FolderSlot(LifecycleModel):
    """
    文件夹槽位（受控词表）

    全所唯一一份语义目录，如 power_of_attorney（委托材料）、identity_proof（当事人身份证明）。
    键一经被引用不可修改；名称可随时改（身份是键不是名）。
    """

    id: int

    key: Any = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name="槽位键",
        help_text="小写英文与下划线；一经引用不可修改（身份标识）",
    )
    name = models.CharField(max_length=100, verbose_name="名称", help_text="展示名，可随时修改，不影响落位")
    category: Any = models.CharField(
        max_length=32,
        choices=FolderSlotCategory.choices,
        default=FolderSlotCategory.GENERAL,
        verbose_name="分类",
        help_text="落位下拉的分组；仅影响展示，不影响落位",
    )
    description = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="说明",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    if TYPE_CHECKING:
        document_templates: RelatedManager[DocumentTemplate]

    class Meta:
        app_label = "documents"
        verbose_name = "文件夹槽位"
        verbose_name_plural = "文件夹槽位"
        ordering: ClassVar = ["name"]
        indexes: ClassVar = [
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"
