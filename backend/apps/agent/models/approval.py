"""Agent 审批模型：高危工具调用审批请求 + 用户审批策略。

审批落库（而非纯内存）支持三种场景：用户离开后回来再同意、超时自动置
``timeout``（fail-closed）、事后审计「谁批了哪个高危操作」。
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .session import AgentSession


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
    #: 驳回理由。与请求理由**分列**：一列两用会让审计分不清「为什么提」和「为什么拒」，
    #: 而且 `decide_approval` 会把发起方写的内容覆盖掉（2026-11 审计）。
    decision_reason = models.TextField(blank=True, default="", verbose_name="驳回理由")
    #: 运行标识 ``{session_id}:{agent_kind}:{turn}``（``services/chat/stream.next_run_turn``）。
    #: 多栏并答时这张卡属于「哪一栏、哪一轮」只能靠它——会话级字段区分不出来。
    run_id = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="运行标识")
    #: 工具调用标识（MCP/后端的 call id）：同一轮内两次 ``delete_case`` 靠它区分。
    tool_call_id = models.CharField(max_length=120, blank=True, default="", verbose_name="工具调用标识")
    #: 去重键 ``sha256(session|short_tool|args)``：三个入口（后端钩子 / MCP 闸门 /
    #: 写端点兜底）共用同一张卡，避免一次删除弹两张卡、等两次。
    dedupe_key = models.CharField(max_length=64, blank=True, default="", db_index=True, verbose_name="去重键")
    #: 被消费时间 —— 一次批准只放行一次调用（MCP 闸门重试命中台账时消费它）。
    consumed_at = models.DateTimeField(null=True, blank=True, verbose_name="消费时间")
    #: 过期时间 —— 到期后即使状态是 approved 也不再放行（不靠 created_at + 常量推）。
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="过期时间")
    #: 风险等级（low/medium/high/critical）。落库是为了审计时分得清
    #: 「删一条草稿」和「清空全库」，也便于事后统计哪类操作最常被拒。
    risk_level = models.CharField(max_length=16, blank=True, default="", verbose_name="风险等级")
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
            models.Index(fields=["dedupe_key", "status"], name="agent_approval_dedupe_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.tool_name} [{self.status}]"

    @property
    def is_granted(self) -> bool:
        """唯一的放行条件。"""
        return self.status == self.Status.APPROVED

    @property
    def is_live_grant(self) -> bool:
        """可用于「一次性放行」的批准：已批准 + 未被消费 + 未过期。

        MCP 服务端闸门用它判断「这轮请求是否被放行过」，而不是只看 ``status``：
        只看状态会让一次批准被反复重放。
        """
        if not self.is_granted or self.consumed_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


class AgentApprovalPolicy(models.Model):
    """审批策略 —— 用户 × 工具类别 → allow / ask / deny（P2-5）。

    ## 定位

    四级风险分级（classify_risk）是**系统兜底**——命中 DANGER/CRITICAL 一律
    人工审批，不可覆盖。策略表是**用户偏好层**：律师觉得某类操作不需要每次
    问，可以配 allow；觉得某类操作要更严，可以配 deny。

    ## 判定顺序（classify_risk 前置查询）

    1. 精确策略（tool_name 完全匹配该用户的策略）→ 按策略
    2. 前缀策略（工具名前缀匹配，如 ``delete_`` 匹配所有删除类）→ 按策略
    3. 无策略 → 走系统四级分级（现状不变）

    ## 安全约束

    - **critical 级工具不可被 allow 覆盖**（classify_risk 判 critical 的，
      即便策略写了 allow 也仍走人工审批——这是硬红线）；
    - 策略只影响「high 级 → allow/deny」与「medium 级 → ask/deny」两档；
    - deny = 直接拒绝不弹窗（比审批更严）。
    """

    class Action(models.TextChoices):
        ALLOW = "allow", "允许（不弹窗）"
        ASK = "ask", "每次询问（默认行为）"
        DENY = "deny", "拒绝（不弹窗直接拒）"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_approval_policies",
        verbose_name="所属用户",
    )
    #: 工具名（完整名如 mcp__fachuan__delete_case）或前缀（如 delete_）
    tool_pattern = models.CharField(max_length=200, verbose_name="工具名或前缀")
    action = models.CharField(
        max_length=8,
        choices=Action.choices,
        default=Action.ASK,
        verbose_name="策略动作",
    )
    #: 前缀匹配（true = tool_pattern 是前缀，匹配所有以它开头的工具）
    is_prefix = models.BooleanField(default=False, verbose_name="前缀匹配")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "审批策略"
        verbose_name_plural = "审批策略"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "tool_pattern"], name="agent_policy_user_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "tool_pattern"], name="agent_policy_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user}:{self.tool_pattern} → {self.action}"
