"""Module for chat."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models.enums import ChatPlatform

from .case import Case

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class CaseChat(models.Model):
    """案件群聊"""

    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="chats", verbose_name=_("案件"))
    platform = models.CharField(
        max_length=32, choices=ChatPlatform.choices, default=ChatPlatform.FEISHU, verbose_name=_("平台")
    )
    chat_id = models.CharField(max_length=128, verbose_name=_("群聊ID"))
    name = models.CharField(max_length=255, verbose_name=_("群名"))
    is_active = models.BooleanField(default=True, verbose_name=_("是否有效"))

    owner_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name=_("群主ID"),
        help_text=_("飞书用户的open_id或其他平台的用户标识符"),
    )
    owner_verified = models.BooleanField(default=False, verbose_name=_("群主已验证"), help_text=_("群主设置是否已验证"))
    owner_verified_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("群主验证时间"), help_text=_("群主设置验证成功的时间")
    )
    creation_audit_log: dict[str, object] = models.JSONField(
        default=dict, verbose_name=_("创建审计日志"), help_text=_("群聊创建过程的详细日志,包含群主设置信息")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    if TYPE_CHECKING:
        audit_logs: RelatedManager[ChatAuditLog]

    class Meta:
        verbose_name = _("群聊")
        verbose_name_plural = _("群聊")
        unique_together: ClassVar = [["case", "platform", "chat_id"]]
        indexes: ClassVar = [
            models.Index(fields=["case", "platform"]),
            models.Index(fields=["chat_id"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["owner_id"]),
            models.Index(fields=["owner_verified"]),
            models.Index(fields=["owner_verified_at"]),
        ]

    def __str__(self) -> str:
        platform_display = self.get_platform_display()
        return f"[{platform_display}] {self.name}"

    def get_owner_display(self) -> str:
        """获取群主显示信息"""
        if not self.owner_id:
            return str(_("未设置群主"))
        status = str(_("已验证")) if self.owner_verified else str(_("未验证"))
        return f"{self.owner_id} ({status})"

    def is_owner_verified_recently(self, hours: int = 24) -> bool:
        """检查群主是否在最近时间内验证过"""
        if not self.owner_verified or not self.owner_verified_at:
            return False
        cutoff_time = timezone.now() - timedelta(hours=hours)
        return bool(self.owner_verified_at >= cutoff_time)

    def get_creation_summary(self) -> str:
        """获取创建摘要信息"""
        summary_parts = [f"群聊: {self.name}"]
        if self.owner_id:
            summary_parts.append(f"群主: {self.owner_id}")
        if self.owner_verified:
            summary_parts.append("已验证")
        return " | ".join(summary_parts)


class ChatAuditLog(models.Model):
    """群聊审计日志"""

    id: int
    ACTION_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("CREATE_START", _("开始创建")),
        ("CREATE_SUCCESS", _("创建成功")),
        ("CREATE_FAILED", _("创建失败")),
        ("OWNER_SET", _("设置群主")),
        ("OWNER_VERIFY", _("验证群主")),
        ("OWNER_RETRY", _("重试群主设置")),
        ("OWNER_SET_FAILED", _("群主设置失败")),
        ("CONFIG_ERROR", _("配置错误")),
    ]

    chat = models.ForeignKey(
        CaseChat,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
        verbose_name=_("关联群聊"),
        help_text=_("关联的群聊,某些操作(如配置错误)可能没有关联群聊"),
    )
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name="chat_audit_logs",
        null=True,
        blank=True,
        verbose_name=_("关联案件"),
        help_text=_("关联的案件"),
    )
    action = models.CharField(
        max_length=32, choices=ACTION_CHOICES, verbose_name=_("操作类型"), help_text=_("执行的操作类型")
    )
    details: dict[str, object] = models.JSONField(
        default=dict, verbose_name=_("操作详情"), help_text=_("操作的详细信息,以JSON格式存储")
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("时间戳"), help_text=_("操作发生的时间"))
    success = models.BooleanField(default=True, verbose_name=_("操作成功"), help_text=_("操作是否成功执行"))
    error_message = models.TextField(blank=True, verbose_name=_("错误信息"), help_text=_("操作失败时的错误信息"))
    external_chat_id = models.CharField(
        max_length=128, blank=True, verbose_name=_("群聊ID"), help_text=_("群聊的外部ID,便于查询")
    )
    platform = models.CharField(
        max_length=32,
        choices=ChatPlatform.choices,
        default=ChatPlatform.FEISHU,
        verbose_name=_("平台"),
        help_text=_("群聊平台"),
    )
    audit_version = models.CharField(
        max_length=16, default="1.0", verbose_name=_("审计版本"), help_text=_("审计日志格式版本")
    )

    class Meta:
        verbose_name = _("群聊审计日志")
        verbose_name_plural = _("群聊审计日志")
        ordering: ClassVar = ["-timestamp"]
        indexes: ClassVar = [
            models.Index(fields=["chat", "-timestamp"]),
            models.Index(fields=["case", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["success", "-timestamp"]),
            models.Index(fields=["external_chat_id", "-timestamp"]),
            models.Index(fields=["platform", "-timestamp"]),
            models.Index(fields=["-timestamp"]),
        ]

    def __str__(self) -> str:
        chat_info = f"Chat:{self.external_chat_id}" if self.external_chat_id else f"ChatModel:{self.chat_id}"
        case_info = f"Case:{self.case_id}" if self.case_id else "NoCase"
        status = "SUCCESS" if self.success else "FAILED"
        action_display = self.get_action_display()
        return f"[{action_display}] {chat_info} | {case_info} | {status}"

    @property
    def formatted_details(self) -> str:
        """获取格式化的详情信息"""
        try:
            return str(json.dumps(self.details, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            return str(self.details)

    @property
    def summary(self) -> str:
        """获取操作摘要"""
        action_display = self.get_action_display()
        summary_parts = [str(action_display)]
        if self.external_chat_id:
            summary_parts.append(f"群聊:{self.external_chat_id}")
        if self.case_id:
            summary_parts.append(f"案件:{self.case_id}")
        if not self.success and self.error_message:
            summary_parts.append(f"错误:{self.error_message[:50]}...")
        return " | ".join(summary_parts)
