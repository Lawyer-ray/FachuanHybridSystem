"""InboxMessage — 统一消息模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class InboxMessage(models.Model):
    """统一收件箱消息，来自各数据源的消息聚合到此表。"""

    source = models.ForeignKey(
        "message_hub.MessageSource",
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("来源"),
    )
    # 原始消息 ID（IMAP UID / 平台消息 ID），用于去重
    message_id = models.CharField(max_length=512, verbose_name=_("原始消息 ID"))

    subject = models.CharField(max_length=512, blank=True, verbose_name=_("主题"))
    sender = models.CharField(max_length=512, blank=True, verbose_name=_("发件人"))
    received_at = models.DateTimeField(verbose_name=_("接收时间"))

    body_text = models.TextField(blank=True, verbose_name=_("正文（纯文本）"))
    body_html = models.TextField(blank=True, verbose_name=_("正文（HTML）"))

    has_attachments = models.BooleanField(default=False, verbose_name=_("有附件"))
    # [{"filename": "xxx.pdf", "original_filename": "xxx.pdf", "custom_filename": "新名字.pdf", "size": 12345, "content_type": "application/pdf", "part_index": 0}]
    attachments_meta = models.JSONField(default=list, verbose_name=_("附件元信息"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("入库时间"))

    class Meta:
        verbose_name = _("收件箱消息")
        verbose_name_plural = _("收件箱消息")
        ordering: ClassVar = ["-received_at"]
        unique_together: ClassVar = [("source", "message_id")]
        indexes: ClassVar = [
            models.Index(fields=["source", "-received_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.source.display_name}] {self.subject or '(无主题)'}"
