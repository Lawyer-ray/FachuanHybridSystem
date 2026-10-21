"""Agent 会话 / 消息 / 审批模型。

## 为什么不复用 apps.workbench 的模型

（workbench 已于 v27.7.20 整体移除；本节保留当初的选型理由。）
它的 ``WorkbenchSession`` / ``WorkbenchMessage`` 绑定了该域的语义
（批量分析来源、附件、存储计量等）。Agent 运行时需要的是纯净的「会话-消息」
两表，便于后续多入口（对话 / 案件内 / 任务式）共用同一套持久化。

## 会话状态归 Django 所有

pi 以 ``--no-session`` 启动，不落任何 session 文件。会话历史由本 app 的消息表
持有，因此多进程 / 多机部署时不需要共享 pi 的磁盘目录。

## 审批落库

workbench 的 ``ApprovalManager`` 是纯内存的，进程重启即丢。这里把审批请求
持久化，支持三种场景：
- 用户离开后回来再同意
- 超时自动置 ``timeout``（fail-closed）
- 事后审计「谁批了哪个高危操作」
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AgentSession(models.Model):
    """一次 agent 对话会话。"""

    class Status(models.TextChoices):
        ACTIVE = "active", "进行中"
        ARCHIVED = "archived", "已归档"

    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="会话标识",
    )
    title = models.CharField(max_length=200, blank=True, default="", verbose_name="标题")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="状态",
    )
    llm_model = models.CharField(max_length=100, blank=True, default="", verbose_name="模型")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="附加数据")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_sessions",
        null=True,
        blank=True,
        verbose_name="所属用户",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "Agent 会话"
        verbose_name_plural = "Agent 会话"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="agent_session_user_idx"),
        ]

    def __str__(self) -> str:
        return self.title or str(self.session_id)


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


class AgentApproval(models.Model):
    """高风险工具调用的审批请求。

    fail-closed：调用方只认 ``is_granted``，其余状态一律按拒绝处理。
    """

    class Status(models.TextChoices):
        PENDING = "pending", "待审批"
        APPROVED = "approved", "已同意"
        REJECTED = "rejected", "已拒绝"
        TIMEOUT = "timeout", "超时未响应"
        CANCELLED = "cancelled", "已取消"

    approval_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="审批标识",
    )
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="approvals",
        null=True,
        blank=True,
        verbose_name="所属会话",
    )
    tool_name = models.CharField(max_length=200, verbose_name="工具名")
    tool_args = models.JSONField(default=dict, blank=True, verbose_name="工具参数")
    reason = models.TextField(blank=True, default="", verbose_name="请求理由")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="状态",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_approvals",
        null=True,
        blank=True,
        verbose_name="决定人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="决定时间")

    class Meta:
        verbose_name = "Agent 审批"
        verbose_name_plural = "Agent 审批"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="agent_approval_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.tool_name} [{self.status}]"

    @property
    def is_granted(self) -> bool:
        """唯一的放行条件。"""
        return self.status == self.Status.APPROVED
