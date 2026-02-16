"""
案由数据模型

本模块定义案由的层级结构和分类信息.
"""

from typing import ClassVar

from django.db import models


class CauseOfAction(models.Model):
    """案由数据模型

    存储案由的层级结构和分类信息,支持民事、刑事、行政三种案件类型.
    通过自引用外键实现层级结构.
    """

    id: int

    class CaseType(models.TextChoices):
        """案件类型"""

        CIVIL = "civil", "民事"
        CRIMINAL = "criminal", "刑事"
        ADMINISTRATIVE = "administrative", "行政"

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="案由编码",
        help_text="案由的唯一编码标识",
    )
    name = models.CharField(
        max_length=255,
        verbose_name="案由名称",
        help_text="案由的中文名称",
    )
    case_type = models.CharField(
        max_length=32,
        choices=CaseType.choices,
        verbose_name="案件类型",
        help_text="案由所属的案件类型",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name="上级案由",
        help_text="父级案由,用于构建层级结构",
    )
    level = models.IntegerField(
        default=1,
        verbose_name="层级",
        help_text="案由在层级结构中的深度,从1开始",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="是否启用",
        help_text="是否在系统中启用此案由",
    )
    is_deprecated = models.BooleanField(
        default=False,
        verbose_name="是否已废弃",
        help_text="案由是否已被法院系统废弃",
    )
    deprecated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="废弃时间",
        help_text="案由被标记为废弃的时间",
    )
    deprecated_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="废弃原因",
        help_text="案由被废弃的原因说明",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="创建时间",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="更新时间",
    )

    class Meta:
        verbose_name: str = "案由"
        verbose_name_plural: str = "案由"
        ordering: ClassVar = ["case_type", "code"]
        indexes: ClassVar = [
            models.Index(fields=["case_type"], name="core_causeo_case_ty_0bbdcd_idx"),
            models.Index(fields=["name"], name="core_causeo_name_742c92_idx"),
            models.Index(fields=["is_active"], name="core_causeo_is_acti_fc1798_idx"),
            models.Index(fields=["is_deprecated"], name="core_causeo_is_depr_7ecc77_idx"),
        ]

    def __str__(self) -> None:
        return f"{self.name} ({self.get_case_type_display()})"

    @property
    def full_path(self) -> str:
        """获取案由的完整路径名称"""
        path_parts = [self.name]
        parent = self.parent
        while parent:
            path_parts.insert(0, parent.name)
            parent = parent.parent
        return " > ".join(path_parts)
