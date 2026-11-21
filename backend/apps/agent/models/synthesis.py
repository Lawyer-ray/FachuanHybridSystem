"""Agent 综合结论 —— MoA aggregator 那一步的落库快照。

## 为什么单独一张表，不塞进 AgentReview

两件事的成本与时机完全不同：``Review`` 是 N×M 次二元判定（三栏 × 7 条 = 21 次调用），
``Synthesis`` 是一次生成（一次调用、输出上千字）。合并成一行会让「只想看结论、不想要打分」
的律师被迫付 21 次 judge 的钱；反过来只跑评审的人也不该有一条空的合成记录。

## 为什么不落成 assistant 消息

转录里的 assistant 消息**等于"某一栏的回答"**：多答轮次按 ``agent_kind`` 分栏渲染，
凭空多一条会变成凭空多一栏，律师会以为还跑了第四个 agent。综合结论是**我们对各栏
的加工产物**，不是任何一家的回答，所以独立成表、独立回放。

## 为什么 lanes_used 与 dropped 都存

只存"用了几栏"会让「少了一栏」看起来像聚合者漏读；把被丢的栏与原因一起存下来，
复盘时才能回答"为什么这份结论没提 B 栏的观点"——答案可能是 B 栏本轮根本没出话。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .session import AgentSession


class AgentSynthesis(models.Model):
    """一次「综合结论」（默认影子模式：只展示，不触发任何自动动作）。"""

    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="syntheses",
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_syntheses",
        null=True,
        blank=True,
        verbose_name="发起人",
    )
    #: 对外标识（``uuid4().hex``），不暴露自增主键（同 ``AgentReview.review_id``）。
    synthesis_id = models.CharField(max_length=32, unique=True, verbose_name="综合结论标识")
    #: 会话内的第几轮（从 1 起，与 ``AgentMessage.turn_no`` / 评审同口径）。
    turn = models.PositiveIntegerField(verbose_name="轮次")
    #: 执行合成的模型（不是候选模型）。
    model = models.CharField(max_length=200, blank=True, default="", verbose_name="合成模型")
    #: 合成正文（Markdown）。
    text = models.TextField(blank=True, default="", verbose_name="综合结论")
    #: 真正进了 prompt 的栏（顺序 = 请求顺序）。
    lanes_used = models.JSONField(default=list, blank=True, verbose_name="参与栏")
    #: 被丢弃的栏及原因（``[{lane, reason}]``）；与 ``lanes_used`` 互斥。
    dropped = models.JSONField(default=list, blank=True, verbose_name="丢弃栏")
    #: 逐条来源锚点（``[{lane, quote}]``）。
    citations = models.JSONField(default=list, blank=True, verbose_name="来源锚点")
    #: 提到但核验没兜住的引用。
    unverified = models.JSONField(default=list, blank=True, verbose_name="未核验项")
    #: 合成自身的 token 成本。
    tokens = models.JSONField(default=dict, blank=True, verbose_name="合成 token")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Agent 综合结论"
        verbose_name_plural = "Agent 综合结论"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "turn"], name="agent_synth_session_turn_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.turn}"
