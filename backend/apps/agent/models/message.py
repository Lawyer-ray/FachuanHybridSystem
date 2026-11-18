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
    #: 这条消息是哪个 agent 说的。
    #:
    #: 为什么消息级需要它（会话级已经有 ``AgentSession.agent_kind``）：
    #: 「同一问题同时问 pi 和 dsh」模式下，同一轮的助手回答有**两条**，都挂在
    #: 同一个 ``session`` 外键下。只有会话标识就分不出哪条是谁说的——历史回放
    #: 时两栏会混成一段，律师看到的是「AI 自相矛盾」而不是「两个模型的不同意见」。
    #: 工具结果（``role=tool``）同理：哪些证据属于哪一栏必须能还原。
    #:
    #: 空串表示**旧数据 / 未标注**（不是错误）：引入本字段之前的消息没有 agent
    #: 概念，回填时猜成 ``pi`` 会把「其实来自别的后端」的旧记录坐实成错的。
    #: 前端渲染时把空串当 ``pi`` 处理——引入双答之前本系统只有 pi 在跑。
    agent_kind = models.CharField(max_length=32, blank=True, default="", db_index=True, verbose_name="Agent 后端")
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
