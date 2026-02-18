"""Module for material."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .case import Case, SupervisingAuthority
from .log import CaseLogAttachment
from .party import CaseParty


class CaseMaterialCategory(models.TextChoices):
    PARTY = "party", _("当事人材料")
    NON_PARTY = "non_party", _("非当事人材料")


class CaseMaterialSide(models.TextChoices):
    OUR = "our", _("我方当事人材料")
    OPPONENT = "opponent", _("对方当事人材料")


class CaseMaterialType(models.Model):
    id: int
    category: models.CharField[str, str] = models.CharField(
        max_length=32, choices=CaseMaterialCategory.choices, verbose_name=_("材料大类")
    )
    name: models.CharField[str, str] = models.CharField(max_length=64, verbose_name=_("类型名称"))
    law_firm: models.ForeignKey[Any, Any] = models.ForeignKey(
        "organization.LawFirm",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="case_material_types",
        verbose_name=_("律所"),
    )
    is_active: models.BooleanField[bool, bool] = models.BooleanField(default=True, verbose_name=_("是否启用"))
    created_at: models.DateTimeField[Any, Any] = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("案件材料类型")
        verbose_name_plural = _("案件材料类型")
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["law_firm", "category", "name"], name="uniq_case_material_type_scope"),
        ]
        indexes: ClassVar = [
            models.Index(fields=["category", "name"]),
            models.Index(fields=["law_firm", "category"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        scope = self.law_firm.name if self.law_firm_id else "全局"  # type: ignore[attr-defined]
        category_display = self.get_category_display()  # type: ignore[attr-defined]
        return f"{scope}-{category_display}-{self.name}"


class CaseMaterial(models.Model):
    id: int
    case: models.ForeignKey[Any, Any] = models.ForeignKey(
        Case, on_delete=models.CASCADE, related_name="materials", verbose_name=_("案件")
    )
    category: models.CharField[str, str] = models.CharField(
        max_length=32, choices=CaseMaterialCategory.choices, verbose_name=_("材料大类")
    )
    type: models.ForeignKey[Any, Any] = models.ForeignKey(
        CaseMaterialType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="materials",
        verbose_name=_("材料类型"),
    )
    type_name: models.CharField[str, str] = models.CharField(max_length=64, verbose_name=_("类型名称"))
    source_attachment: models.OneToOneField[Any, Any] = models.OneToOneField(
        CaseLogAttachment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bound_material",
        verbose_name=_("来源日志附件"),
    )
    side: models.CharField[str | None, str | None] = models.CharField(
        max_length=32,
        choices=CaseMaterialSide.choices,
        null=True,
        blank=True,
        verbose_name=_("当事人方向"),
    )
    parties: models.ManyToManyField[Any, Any] = models.ManyToManyField(
        CaseParty, blank=True, related_name="materials", verbose_name=_("关联当事人")
    )
    supervising_authority: models.ForeignKey[Any, Any] = models.ForeignKey(
        SupervisingAuthority,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="materials",
        verbose_name=_("主管机关"),
    )
    created_at: models.DateTimeField[Any, Any] = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("案件材料")
        verbose_name_plural = _("案件材料")
        indexes: ClassVar = [
            models.Index(fields=["case", "category", "created_at"]),
            models.Index(fields=["case", "category", "side"]),
            models.Index(fields=["case", "category", "supervising_authority"]),
            models.Index(fields=["type_name"]),
        ]

    def __str__(self) -> str:
        category_display = self.get_category_display()  # type: ignore[attr-defined]
        return f"{self.case_id}-{category_display}-{self.type_name}"  # type: ignore[attr-defined]


class CaseMaterialGroupOrder(models.Model):
    id: int
    case: models.ForeignKey[Any, Any] = models.ForeignKey(
        Case, on_delete=models.CASCADE, related_name="material_group_orders", verbose_name=_("案件")
    )
    category: models.CharField[str, str] = models.CharField(
        max_length=32, choices=CaseMaterialCategory.choices, verbose_name=_("材料大类")
    )
    side: models.CharField[str | None, str | None] = models.CharField(
        max_length=32,
        choices=CaseMaterialSide.choices,
        null=True,
        blank=True,
        verbose_name=_("当事人方向"),
    )
    supervising_authority: models.ForeignKey[Any, Any] = models.ForeignKey(
        SupervisingAuthority,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="material_group_orders",
        verbose_name=_("主管机关"),
    )
    type: models.ForeignKey[Any, Any] = models.ForeignKey(
        CaseMaterialType, on_delete=models.CASCADE, related_name="group_orders", verbose_name=_("材料类型")
    )
    sort_index: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(default=0, verbose_name=_("排序"))

    class Meta:
        verbose_name = _("案件材料分组顺序")
        verbose_name_plural = _("案件材料分组顺序")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["case", "category", "side", "supervising_authority", "type"],
                name="uniq_case_material_group_order",
            ),
        ]
        indexes: ClassVar = [
            models.Index(fields=["case", "category", "side", "sort_index"]),
            models.Index(fields=["case", "category", "supervising_authority", "sort_index"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.category}-{self.sort_index}"  # type: ignore[attr-defined]


class CaseFolderBinding(models.Model):
    """案件文件夹绑定"""

    id: int
    case: models.OneToOneField[Any, Any] = models.OneToOneField(
        Case, on_delete=models.CASCADE, related_name="folder_binding", verbose_name=_("案件")
    )
    folder_path: models.CharField[str, str] = models.CharField(
        max_length=1000, verbose_name=_("文件夹路径"), help_text=_("绑定的本地或网络文件夹路径")
    )
    created_at: models.DateTimeField[Any, Any] = models.DateTimeField(auto_now_add=True, verbose_name=_("绑定时间"))
    updated_at: models.DateTimeField[Any, Any] = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("案件文件夹绑定")
        verbose_name_plural = _("案件文件夹绑定")
        indexes: ClassVar = [
            models.Index(fields=["case"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.case.name} - {self.folder_path}"

    @property
    def folder_path_display(self) -> str:
        """格式化显示路径"""
        if not self.folder_path:
            return ""
        max_length = 50
        if len(self.folder_path) <= max_length:
            return self.folder_path
        start_len = max_length // 2 - 2
        end_len = max_length - start_len - 3
        return f"{self.folder_path[:start_len]}...{self.folder_path[-end_len:]}"
