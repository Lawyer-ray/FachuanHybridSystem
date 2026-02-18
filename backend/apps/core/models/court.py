"""
法院数据模型

本模块定义法院的层级结构和编码信息.
"""

from typing import ClassVar

from django.db import models


class Court(models.Model):
    """法院数据模型

    存储法院的层级结构和编码信息.
    通过自引用外键实现层级结构(省份 -> 高院 -> 中院 -> 基层法院).
    """

    id: int
    parent_id: int  # 外键ID字段
    code = models.CharField(max_length=50, unique=True, verbose_name="法院编码")
    name = models.CharField(max_length=200, verbose_name="法院名称")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="上级法院",
    )
    level = models.IntegerField(default=1, verbose_name="层级")
    province = models.CharField(max_length=50, blank=True, verbose_name="省份")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        verbose_name = "法院"
        verbose_name_plural = "法院"
        ordering: ClassVar = ["province", "level", "name"]
        indexes: ClassVar = [
            models.Index(fields=["province"], name="core_court_provinc_9fe4bb_idx"),
            models.Index(fields=["level"], name="core_court_level_dc4c2b_idx"),
            models.Index(fields=["name"], name="core_court_name_6afac9_idx"),
            models.Index(fields=["is_active"], name="core_court_is_acti_16a9bd_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def full_path(self) -> str:
        """获取法院的完整路径名称"""
        path_parts = [self.name]
        parent = self.parent
        while parent:
            path_parts.insert(0, parent.name)
            parent = parent.parent
        return " > ".join(path_parts)
