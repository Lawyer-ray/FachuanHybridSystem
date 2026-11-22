"""Agent 综合结论 —— 落库快照（``AgentSynthesis``）与后台任务（``AgentSynthesisJob``）。

## 为什么单独一张表，不塞进 AgentReview

两件事的成本与时机完全不同：``Review`` 是 N×M 次二元判定（三栏 × 7 条 = 21 次调用），
``Synthesis`` 是一次生成（一次调用、输出上千字）。合并成一行会让「只想看结论、不想要打分」
的律师被迫付 21 次 judge 的钱；反过来只跑评审的人也不该有一条空的合成记录。

## 快照与转录各存一份

``AgentSynthesis`` 是**快照**（含 dropped / citations / unverified，刷新回放与审计用）；
综合正文另在会话转录里写一条 ``agent_kind="synthesis"`` 的 assistant 消息（历史回放、
检索、后续追问都按消息表走，见 ``services/synthesis/store.save_synthesis_message``）。
前端按 kind 把它排除在"各栏回答"之外，不会凭空多出一栏。

## 为什么 lanes_used 与 dropped 都存

只存"用了几栏"会让「少了一栏」看起来像聚合者漏读；把被丢的栏与原因一起存下来，
复盘时才能回答"为什么这份结论没提 B 栏的观点"——答案可能是 B 栏本轮根本没出话。

## 为什么要有任务表

一次综合（评审 + agent 综合 + 威科核验）常常跑几分钟，不能放在一个 HTTP 请求里等。
``AgentSynthesisJob`` 记录后台任务的状态，前端轮询它；同一会话同一轮**同时只能有一个
进行中的任务**（部分唯一约束 ``agent_synth_job_one_active``），重复点击拿到的是已在跑的
那一个，不会重复花钱。
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


class AgentSynthesisJob(models.Model):
    """一次「生成综合结论」的后台任务（状态机见 :class:`Status`）。"""

    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "已完成"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"

    #: 进行中的状态（部分唯一约束与幂等判断都用它）。
    ACTIVE_STATUSES = (Status.QUEUED, Status.RUNNING)

    #: 对外标识（``uuid4().hex``）。
    job_id = models.CharField(max_length=32, unique=True, verbose_name="任务标识")
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="synthesis_jobs",
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_synthesis_jobs",
        null=True,
        blank=True,
        verbose_name="发起人",
    )
    turn = models.PositiveIntegerField(verbose_name="轮次")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, verbose_name="状态")
    #: 当前阶段（``review`` / ``synthesis`` / ``verify`` / ``saving``；空 = 未开始或已结束）。
    stage = models.CharField(max_length=16, blank=True, default="", verbose_name="阶段")
    #: 提交时的参数（agents / model / kind / review / credential_id），后台按它重放。
    params = models.JSONField(default=dict, blank=True, verbose_name="参数")
    #: 运行中收到的取消请求。运行中的任务每次心跳读它，读到就自行取消（跨 worker 生效）。
    cancel_requested = models.BooleanField(default=False, verbose_name="已请求取消")
    #: 失败原因（给人看的一句话，不含堆栈）。
    error = models.CharField(max_length=255, blank=True, default="", verbose_name="失败原因")
    #: 后台队列的任务 id（排队中取消时用它出队）。
    task_id = models.CharField(max_length=64, blank=True, default="", verbose_name="队列任务 ID")
    #: 成功时的产物。
    synthesis = models.ForeignKey(
        AgentSynthesis,
        on_delete=models.SET_NULL,
        related_name="jobs",
        null=True,
        blank=True,
        verbose_name="综合结论",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    #: 心跳：运行中的任务定期刷新它；长时间不刷新 = 进程已不在（重启 / 被杀），按失败收口。
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    class Meta:
        verbose_name = "Agent 综合结论任务"
        verbose_name_plural = "Agent 综合结论任务"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "turn"], name="agent_synth_job_sess_turn_idx"),
        ]
        constraints = [
            # 同一会话同一轮同时只能有一个进行中的任务：并发的重复点击由数据库挡住，
            # 不靠前端禁用按钮。
            models.UniqueConstraint(
                fields=["session", "turn"],
                condition=models.Q(status__in=["queued", "running"]),
                name="agent_synth_job_one_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.turn}:{self.status}"
