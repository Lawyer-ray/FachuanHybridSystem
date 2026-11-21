"""Agent 运行记录模型 —— 一轮对话的成本、耗时与结果。

## 为什么单独一张表

``AgentMessage.metadata.output_tokens`` 是**逐条消息**的，回答不了运营与
管理最关心的三类问题：

- 这个律师 / 这个律所本月花了多少 token？
- 一次回答平均多久？失败率多少？
- 哪个模型贵、哪个工具调用最多？

所以把「一次 ``stream_chat`` 运行」的汇总单独落一行。与 ``AgentApproval``
同口径（都挂 session + user），审批率 / 超时率可以直接 join 统计。

## 为什么取消与出错也要落

只记成功路径等于把「最贵的失败」藏起来：用户按停止时模型可能已经跑了
大半 token；LLM 网关超时重试三次也是真金白银。``status`` 区分三态，
成本字段尽力而为（拿不到就是 0，不编造）。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .session import AgentSession


class AgentRun(models.Model):
    """一轮对话的运行记录。"""

    class Status(models.TextChoices):
        OK = "ok", "正常完成"
        ERROR = "error", "出错"
        CANCELLED = "cancelled", "用户中止"

    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_runs",
        null=True,
        blank=True,
        verbose_name="发起人",
    )
    #: 平台名（``LLMProvider.name``）：成本归属的一维。历史行留空 = 「未知」。
    provider = models.CharField(max_length=50, blank=True, default="", verbose_name="平台")
    model = models.CharField(max_length=100, blank=True, default="", verbose_name="模型")
    #: 本条运行记录是**哪个 agent 后端**跑的（``pi`` / ``dsh`` / ``openai-agents``）。
    #:
    #: ## 为什么必须记在运行上，而不是靠会话字段
    #:
    #: ``AgentSession.agent_kind`` 是「这个会话默认用谁」，多答一轮会同时落 N 条
    #: 记录（三个 agent 各一条，模型可能各不相同）。没有本字段时，账上只能看到
    #: 「这一轮花了多少钱」，却回答不了「**哪个 agent** 花的」——两个 agent 用同一个
    #: 模型时更彻底无解，只能按模型名反猜。
    #:
    #: ## 为什么空串而不是默认 ``pi``
    #:
    #: 空串 = 引入本字段之前的旧数据。填 ``pi`` 会把「不知道」伪装成事实（那时
    #: 只有 pi 在跑，但这是**推断**出来的，不是记下来的）；查询侧按「空串归 pi」
    #: 处理即可，与 ``AgentMessage.agent_kind`` 同口径。
    #: 本轮轮次号（与助手消息的 ``turn_no`` 同值）：多答一轮 N 条记录靠它聚合成
    #: 「这一轮三栏一共花了多少」，不再靠 created_at 时间窗猜。
    turn_no = models.IntegerField(default=0, db_index=True, verbose_name="轮次号")
    agent_kind = models.CharField(max_length=32, blank=True, default="", verbose_name="agent 后端")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OK,
        verbose_name="结果",
    )
    input_tokens = models.IntegerField(default=0, verbose_name="输入 token")
    output_tokens = models.IntegerField(default=0, verbose_name="输出 token")
    #: 缓存读取 token（pi 的 ``usage.cacheRead``）。
    #:
    #: ## 为什么必须单独记
    #:
    #: 法穿一个核心设计是「AGENTS.md 逐轮字节稳定 → 命中 provider prompt cache」
    #: （见 ``pi/memory-inject.ts``）。但改造前**没有任何指标能验证它到底生效没**，
    #: 因为 ``input_tokens`` 只装着未命中部分。cache 一失效，成本会悄悄涨好几倍
    #: 而账上看不出来。
    #:
    #: ## 为什么不能加进 input_tokens
    #:
    #: 每轮的 ``cacheRead`` 是**那次 API 调用重读的累计前缀**，逐消息累加会严重
    #: 虚高（且与 provider 计费口径不符）。所以它只能单列，命中率按
    #: ``cacheRead / (input + cacheRead + cacheWrite)`` 算。
    cache_read_tokens = models.IntegerField(default=0, verbose_name="缓存命中 token")
    #: 缓存写入 token（pi 的 ``usage.cacheWrite``）。首次建立或者前缀变了才计费。
    cache_write_tokens = models.IntegerField(default=0, verbose_name="缓存写入 token")
    #: 压缩前上下文水位（pi ``get_session_stats`` 的 ``contextUsage.tokens``）。
    #:
    #: ## 为什么 nullable 而不是 default=0
    #:
    #: 水位是事实陈述：旧 pi / provider 不上报 / 进程恰好退出时拿不到就是
    #: 拿不到，编造 0 会把「不知道」伪装成「上下文是空的」——前者要查链路，
    #: 后者说明压缩工作正常，两种运营信号的下一步动作完全不同。
    context_used_tokens = models.IntegerField(null=True, blank=True, verbose_name="压缩前上下文 token")
    #: 上下文窗口大小（``contextUsage.contextWindow``），与 used 配对算占用百分比。
    context_total_tokens = models.IntegerField(null=True, blank=True, verbose_name="上下文窗口")
    tool_calls = models.IntegerField(default=0, verbose_name="工具调用数")
    duration_ms = models.IntegerField(default=0, verbose_name="耗时（毫秒）")
    #: 出错时的分类标记（如 pi_unavailable / pi_error / unexpected / queue_timeout）。
    #: 存短码而不是异常原文：既不泄露内部细节，又够做聚合。
    error_kind = models.CharField(max_length=64, blank=True, default="", verbose_name="错误类型")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Agent 运行记录"
        verbose_name_plural = "Agent 运行记录"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="agent_run_user_idx"),
            models.Index(fields=["session", "-created_at"], name="agent_run_session_idx"),
            models.Index(fields=["status", "-created_at"], name="agent_run_status_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.status} {self.model} in={self.input_tokens} out={self.output_tokens} "
            f"cache={self.cache_read_tokens}/{self.cache_write_tokens}"
        )

    @property
    def total_tokens(self) -> int:
        """计费口径的总计输入侧 token（**不含** ``cache_read``）。

        为什么要这个口径：``cache_read`` 是重读的累计前缀，把它加进来会让
        「本月花了多少」虚高数倍。要看「缓存帮了多少」请用
        :attr:`cache_hit_rate`，两个问题分开回答。
        """
        return self.input_tokens + self.output_tokens + self.cache_write_tokens

    @property
    def cache_hit_rate(self) -> float:
        """输入侧缓存命中率（0.0 – 1.0）；无输入时不返回 0 而是 0.0。

        口径：``cacheRead / (input + cacheRead + cacheWrite)``。
        分母是「本次请求实际处理的全部输入侧 token」，分子是其中走缓存的部分。
        """
        denominator = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        if denominator <= 0:
            return 0.0
        return round(self.cache_read_tokens / denominator, 4)
