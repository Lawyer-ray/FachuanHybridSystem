"""工作台会话模型"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class SessionStatus(models.TextChoices):
    ACTIVE = "active", _("活跃")
    ARCHIVED = "archived", _("已归档")


class WorkbenchSession(models.Model):
    """工作台会话"""

    id: int
    session_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workbench_sessions",
    )
    title = models.CharField(_("标题"), max_length=255, blank=True, default="")
    llm_model = models.CharField(
        _("LLM 模型"),
        max_length=255,
        blank=True,
        default="",
        help_text="使用的 LLM 模型 ID",
    )
    status = models.CharField(
        _("状态"),
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE,
    )
    metadata = models.JSONField(_("元数据"), default=dict, blank=True)
    storage_bytes = models.PositiveIntegerField(
        _("存储字节数"),
        default=0,
        help_text="该会话所有消息内容的总字节数（UTF-8）",
    )
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "workbench_session"
        verbose_name = _("工作台会话")
        verbose_name_plural = _("工作台会话")
        ordering = ["-updated_at"]
        indexes: ClassVar = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return self.title or str(self.session_id)[:8]
