"""用户工具收藏模型。"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ToolFavorite(models.Model):
    """记录用户在「其他工具」中收藏的具体工具（模型级别）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tool_favorites",
        verbose_name="用户",
    )
    tool_url = models.CharField(max_length=255, verbose_name="工具 URL")
    tool_name = models.CharField(max_length=100, blank=True, default="", verbose_name="工具名称")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收藏时间")

    class Meta:
        verbose_name = "工具收藏"
        verbose_name_plural = "工具收藏"
        unique_together = ("user", "tool_url")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} → {self.tool_name or self.tool_url}"
