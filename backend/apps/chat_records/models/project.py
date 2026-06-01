"""Module for project."""

from typing import ClassVar

from django.db import models


class ChatRecordProject(models.Model):
    name = models.CharField(max_length=255, verbose_name="项目名称")
    id: int
    description = models.TextField(blank=True, verbose_name="说明")
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="chat_record_projects",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "梳理聊天记录"
        verbose_name_plural = "梳理聊天记录"
        indexes: ClassVar = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["created_by"]),
        ]

    def __str__(self) -> str:
        return f"{self.id}-{self.name}"
