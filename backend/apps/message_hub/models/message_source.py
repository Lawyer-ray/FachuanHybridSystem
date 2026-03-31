"""MessageSource — 消息来源配置。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class SourceType(models.TextChoices):
    IMAP = "imap", _("IMAP 邮箱")
    COURT_INBOX = "court_inbox", _("一张网收件箱")


class SyncStatus(models.TextChoices):
    PENDING = "pending", _("待同步")
    SUCCESS = "success", _("同步成功")
    FAILED = "failed", _("同步失败")


class MessageSource(models.Model):
    """消息来源配置，关联 AccountCredential，描述如何拉取消息。"""

    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.CASCADE,
        related_name="message_sources",
        verbose_name=_("账号凭证"),
    )
    source_type = models.CharField(
        max_length=32,
        choices=SourceType.choices,
        default=SourceType.IMAP,
        verbose_name=_("来源类型"),
    )
    display_name = models.CharField(max_length=128, verbose_name=_("显示名称"))
    is_enabled = models.BooleanField(default=True, verbose_name=_("启用"))
    poll_interval_minutes = models.PositiveIntegerField(default=30, verbose_name=_("轮询间隔（分钟）"))
    sync_since = models.DateTimeField(verbose_name=_("同步起始时间"), help_text=_("只拉取此时间之后的消息"))

    # IMAP 专用：主机名（覆盖从 credential.url 推断的值）和最后同步 UID
    imap_host = models.CharField(max_length=255, blank=True, verbose_name=_("IMAP 主机"), help_text=_("留空则从凭证 URL 自动推断，如 mail.jtn.com"))
    imap_account = models.CharField(max_length=255, blank=True, verbose_name=_("IMAP 账号"), help_text=_("留空则使用凭证账号，如需覆盖填写完整邮箱地址"))
    # IMAP 专用：记录最后同步的 UID，用于增量拉取
    last_synced_uid = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("最后同步 UID"))

    # 同步状态
    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name=_("最后同步时间"))
    last_sync_status = models.CharField(
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
        verbose_name=_("同步状态"),
    )
    last_sync_error = models.TextField(blank=True, verbose_name=_("同步错误信息"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("消息来源")
        verbose_name_plural = _("消息来源")
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.get_source_type_display()})"
