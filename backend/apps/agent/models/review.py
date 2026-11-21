"""Agent 多答评审记录 —— 一轮回答的 rubric 判定与分栏汇总。

## 为什么要落库

判定走的是外部 judge 模型：一次三栏 × 7 条就是 21 次调用，既慢又花钱。
如果结果只存在请求内存里，律师一刷新页面就没了——而"昨天那轮到底怎么评的"
正是复盘与校准（B6）最需要的数据。

## 为什么 verdicts / lanes 存 JSON 而不是拆表

判定是**一次请求的完整快照**：rubric 改版后重跑会得到不同条目，拆表反而要
处理"旧 rubric 已不存在"的外键悬空。整块 JSON 与 ``Review`` 契约一一对应，
回放时直接按契约反序列化，不做二次拼装。检索/统计维度（session、turn、
created_at）仍是真正的列与索引。

## 为什么 review_id 与主键分开

``review_id`` 是对外契约里的标识（会出现在前端与日志里），主键是自增整数。
暴露自增值会让人能数出全所跑了多少次评审；而 ``review_id`` 用随机 hex，
不可枚举。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .session import AgentSession


class AgentReview(models.Model):
    """一轮多答的评审结果（默认影子模式：只展示，不触发动作）。"""

    class Stage(models.TextChoices):
        SHADOW = "shadow", "影子（只展示）"

    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_reviews",
        null=True,
        blank=True,
        verbose_name="发起人",
    )
    #: 对外标识（``uuid4().hex``），不暴露自增主键。
    review_id = models.CharField(max_length=32, unique=True, verbose_name="评审标识")
    #: 会话内的第几轮（从 1 起，按 user 消息顺序计数）。
    turn = models.PositiveIntegerField(verbose_name="轮次")
    rubric_id = models.CharField(max_length=64, verbose_name="评分标准")
    stage = models.CharField(
        max_length=16,
        choices=Stage.choices,
        default=Stage.SHADOW,
        verbose_name="评审阶段",
    )
    #: 本次实际使用的 judge 模型清单（重试换模型后仍保留原清单，便于复盘）。
    judge_models = models.JSONField(default=list, blank=True, verbose_name="评审模型")
    #: ``LaneReview.model_dump()`` 的数组。
    lanes = models.JSONField(default=list, blank=True, verbose_name="分栏汇总")
    #: ``CriteriaVerdict.model_dump()`` 的数组（逐条判定，含判不了的原因）。
    verdicts = models.JSONField(default=list, blank=True, verbose_name="逐条判定")
    headline = models.CharField(max_length=500, blank=True, default="", verbose_name="一句话导航")
    #: 提到但本轮没有核验兜住的东西（B3 接引用核验后写入）。
    unverified = models.JSONField(default=list, blank=True, verbose_name="未核验项")
    #: 评审自身的 token 成本（与三栏生成成本分开记）。
    tokens = models.JSONField(default=dict, blank=True, verbose_name="评审 token")
    #: ``EquivalenceCluster`` 的数组（三栏答案是否同一立场）。
    #:
    #: 为什么不拆表：与 verdicts 同理——成团是**一次评审的完整快照**，reroll 后成员
    #: 与代表全变；拆表就要处理「上一轮的簇已不存在」的悬空。
    clusters = models.JSONField(default=list, blank=True, verbose_name="立场成团")
    #: 成团失败原因（空串 = 成功或未跑）。失败与「三份真的全异」必须可区分。
    clusters_error = models.CharField(max_length=200, blank=True, default="", verbose_name="成团失败原因")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Agent 评审"
        verbose_name_plural = "Agent 评审"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "turn"], name="agent_review_session_turn_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.turn}:{self.rubric_id}"
