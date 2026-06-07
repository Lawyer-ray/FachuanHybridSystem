"""MessageSource — 消息来源配置。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class SourceType(models.TextChoices):
    IMAP = "imap", "IMAP 邮箱"
    COURT_INBOX = "court_inbox", "一张网收件箱"
    COURT_SCHEDULE = "court_schedule", "一张网庭审日程"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "待同步"
    SUCCESS = "success", "同步成功"
    FAILED = "failed", "同步失败"


class MessageSource(models.Model):
    """消息来源配置，关联 AccountCredential，描述如何拉取消息。"""

    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.CASCADE,
        related_name="message_sources",
        verbose_name="账号凭证",
    )
    source_type = models.CharField(
        max_length=32,
        choices=SourceType.choices,
        default=SourceType.IMAP,
        verbose_name="来源类型",
    )
    display_name = models.CharField(max_length=128, verbose_name="显示名称")
    is_enabled = models.BooleanField(default=True, verbose_name="启用")
    poll_interval_minutes = models.PositiveIntegerField(default=30, verbose_name="轮询间隔（分钟）")
    sync_since = models.DateTimeField(verbose_name="同步起始时间", help_text="只拉取此时间之后的消息")

    # IMAP 专用：主机名（覆盖从 credential.url 推断的值）和最后同步 UID
    imap_host = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="IMAP 主机",
        help_text="留空则从凭证 URL 自动推断，如 mail.jtn.com",
    )
    imap_account = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="IMAP 账号",
        help_text="留空则使用凭证账号，如需覆盖填写完整邮箱地址",
    )
    last_synced_uid = models.PositiveIntegerField(null=True, blank=True, verbose_name="最后同步 UID")

    # 发件人过滤（邮箱或名称，每行一个，大小写不敏感）
    sender_whitelist = models.TextField(
        blank=True,
        verbose_name="只同步这些发件人",
        help_text="每行一个邮箱或名称，留空则不限制",
    )
    sender_blacklist = models.TextField(
        blank=True,
        verbose_name="不同步这些发件人",
        help_text="每行一个邮箱或名称，留空则不排除",
    )

    last_sync_at = models.DateTimeField(null=True, blank=True, verbose_name="最后同步时间")
    last_sync_status = models.CharField(
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
        verbose_name="同步状态",
    )
    last_sync_error = models.TextField(blank=True, verbose_name="同步错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "消息来源"
        verbose_name_plural = "消息来源"
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["source_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.source_type})"
