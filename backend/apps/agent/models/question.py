"""Agent 提问 —— 模型主动向律师澄清，而不是猜。

## 为什么不复用 AgentApproval

两者长得很像（都是「挂起等前端」），但语义完全不同：

| | AgentApproval | AgentQuestion |
|:-|:-|:-|
| 回答类型 | 布尔（同意 / 拒绝） | **结构化数据**（选了什么 / 自由输入 / 附言） |
| 目的 | 拦住危险操作 | **补齐缺失信息** |
| 谁关心结果 | 审批网关闭环（放行或阻断） | 模型自己（继续干活） |
| 会不会超时 | 超时 = 拒绝（fail-closed） | 超时 = 交回模型自己决定，不阻断 |

把提问塞进审批表会污染审批审计（「审批率」「拒绝率」这些运营指标会失真），
也会让前端两种卡片混在一起。所以单独立表。

## 为什么必须允许「律师不回答」

现实中律师常常正忙。如果提问是强制阻塞且无出路，整个任务就卡死在那里。
所以超时后不是报错，而是返回 ``timed_out``，让模型**按现有信息继续并显式
声明假设**——这正是 AGENTS.md 里「缺料不许猜」的落地方式：不确定的时候
要说明假设，而不是静默编一个。

## 与提示注入的关系

提问的**答案**是用户输入，属于可信意图（人自己说的）。这一点很重要：
审批「剥皮转录」时保留 human 的回答、剔除模型自我陈述，依据就在这里。
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AgentQuestion(models.Model):
    """一次「模型向律师提问」的完整生命周期。"""

    class Status(models.TextChoices):
        PENDING = "pending", "等待回答"
        ANSWERED = "answered", "已回答"
        TIMED_OUT = "timed_out", "超时未答"
        CANCELLED = "cancelled", "已取消"

    question_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="提问标识",
    )
    session = models.ForeignKey(
        "agent.AgentSession",
        on_delete=models.CASCADE,
        related_name="questions",
        null=True,
        blank=True,
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_questions",
        null=True,
        blank=True,
        verbose_name="被问的律师",
    )

    #: 题面。批量提问时是 JSON 数组：[{id, question, context?, options?, ...}]。
    #: 存 JSON 而不是拆表：提问是一次性的，不需要按选项做 SQL 聚合。
    questions = models.JSONField(default=list, verbose_name="问题列表")
    #: 回答。与 questions 按 id 对齐：[{id, status, selections?, text?, comment?}]。
    answers = models.JSONField(default=list, blank=True, verbose_name="回答列表")

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="状态",
    )
    #: 前端是「律师主动跳过」还是「没人答超时」——两者的后续动作不同：
    #: 跳过是「他看了但不想答」，超时是「他可能根本没看到」，都要如实记下来。
    skipped = models.BooleanField(default=False, verbose_name="律师主动跳过")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="提问时间")
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name="回答时间")

    class Meta:
        verbose_name = "Agent 提问"
        verbose_name_plural = "Agent 提问"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="agent_question_session_idx"),
            models.Index(fields=["status", "-created_at"], name="agent_question_status_idx"),
        ]

    def __str__(self) -> str:
        count = len(self.questions) if isinstance(self.questions, list) else 0
        return f"{self.status} {count} 问 {self.question_id}"
