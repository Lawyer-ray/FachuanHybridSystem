"""DocSpaceDocument — 本地文件与 DocSpace 文档的映射。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class DocSpaceDocument(models.Model):
    """本地文件与 DocSpace 云端文档的映射记录。"""

    id: int

    lawyer = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.CASCADE,
        related_name="docspace_docs",
        verbose_name="所属律师",
    )
    title = models.CharField(max_length=255, verbose_name="文件名")
    docspace_file_id = models.PositiveIntegerField(unique=True, verbose_name="DocSpace 文件 ID")
    docspace_folder_id = models.PositiveIntegerField(verbose_name="DocSpace 文件夹 ID")
    file_ext = models.CharField(max_length=16, default=".docx", verbose_name="文件类型")
    content_length = models.PositiveIntegerField(default=0, verbose_name="文件大小(bytes)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    last_editor = models.ForeignKey(
        "organization.Lawyer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="last_edited_docspace_docs",
        verbose_name="最后编辑者",
    )

    class Meta:
        verbose_name = "DocSpace 文档"
        verbose_name_plural = "DocSpace 文档"
        ordering: ClassVar = ["-updated_at"]
        indexes: ClassVar = [
            models.Index(fields=["lawyer", "-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} (file_id={self.docspace_file_id})"
