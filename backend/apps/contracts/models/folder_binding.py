"""Module for folder binding."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .contract import Contract


class ContractFolderBinding(models.Model):
    """合同文件夹绑定"""

    id: int
    contract_id: int
    contract = models.OneToOneField(
        Contract, on_delete=models.CASCADE, related_name="folder_binding", verbose_name=_("合同")
    )
    folder_path = models.CharField(
        max_length=1000, verbose_name=_("文件夹路径"), help_text=_("绑定的本地或网络文件夹路径")
    )
    folder_inode = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("inode"), help_text=_("文件夹 inode 编号，用于路径自动修复")
    )
    folder_device = models.IntegerField(
        null=True, blank=True, verbose_name=_("设备号"), help_text=_("文件夹所在设备号，与 inode 配合使用")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("绑定时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("合同文件夹绑定")
        verbose_name_plural = _("合同文件夹绑定")
        indexes: ClassVar = [
            models.Index(fields=["contract"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract.name} - {self.folder_path}"
