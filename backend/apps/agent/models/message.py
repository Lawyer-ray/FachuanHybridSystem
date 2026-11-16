"""Agent 会话消息模型（审计与回放的权威）。"""

from __future__ import annotations

from django.db import models

from .session import AgentSession


class AgentMessage(models.Model):
    """会话中的一条消息。"""

    class Role(models.TextChoices):
        USER = "user", "用户"
        ASSISTANT = "assistant", "助手"
        TOOL = "tool", "工具"

    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="所属会话",
    )
    role = models.CharField(max_length=16, choices=Role.choices, verbose_name="角色")
    content = models.TextField(blank=True, default="", verbose_name="内容")
    tool_name = models.CharField(max_length=200, blank=True, default="", verbose_name="工具名")
    tool_call_id = models.CharField(max_length=200, blank=True, default="", verbose_name="工具调用标识")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="附加数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Agent 消息"
        verbose_name_plural = "Agent 消息"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["session", "created_at"], name="agent_msg_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"
