"""律师采纳记录 —— 影子期最便宜的一手数据。

## 为什么不把采纳写回 ``AgentReview``

``AgentReview`` 是一次 judge 判定的**不可变快照**：某轮回答在某版 rubric 下被判成
什么样。采纳是之后才发生的用户动作，而且可能反复（先选 B 栏，看过原文后改成
A 栏）。把采纳写回评审行，等于让"昨天那轮到底怎么评的"随用户点击变化——B6 校准
拿到的历史就不可复现了。所以单独一张表，一行对应一次评审的**当前**采纳结果。

## 为什么 review 是 OneToOne

"同一 review 只允许一条采纳"是产品语义：律师要看的是"这一轮最后采纳了谁"，
不是点击流水。重复采纳走 ``update_or_create`` 覆盖同一行，``adopted_at`` 记最后
一次；真正的点击流水在访问日志里，不在这张表。

## lane 为什么可空

``lane=None`` + ``merged=True`` = 采纳的是三栏合并结果，不归属某一栏；
``lane=None`` + ``merged=False`` 留给"律师自己改写/纠错"，理由写 ``note``。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .review import AgentReview


class AgentReviewAdoption(models.Model):
    """一条评审的当前采纳结果（重复采纳覆盖同一行）。"""

    review = models.OneToOneField(
        AgentReview,
        on_delete=models.CASCADE,
        related_name="adoption",
        verbose_name="评审",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_review_adoptions",
        null=True,
        blank=True,
        verbose_name="采纳人",
    )
    #: 采纳的栏（agent_kind）；空 = 不归属某一栏（合并/手改）。
    lane = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        default=None,
        verbose_name="采纳栏",
    )
    #: 采纳的是三栏合并后的结果（不归属单一栏）。
    merged = models.BooleanField(default=False, verbose_name="合并采纳")
    note = models.CharField(max_length=500, blank=True, default="", verbose_name="备注")
    #: 最后一次采纳时间（重复采纳会刷新，保留"律师最终怎么选"的时点）。
    adopted_at = models.DateTimeField(auto_now=True, verbose_name="采纳时间")

    class Meta:
        verbose_name = "Agent 评审采纳"
        verbose_name_plural = "Agent 评审采纳"

    def __str__(self) -> str:
        return f"{self.review_id}:{self.lane or '-'}"
