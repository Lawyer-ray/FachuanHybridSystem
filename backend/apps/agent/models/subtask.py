"""子 agent —— 主会话派出的只读调研子任务。

## 为什么需要

律师问「这个案子有哪些类似判例 / 帮我查这三份合同的差异」时，主 agent 只能
自己把 `list_*` / `fetch_url` / 附件解析的**全量返回读进上下文**——一次就可能
撑爆窗口，而这些原始材料 99% 是用完即弃的中间产物。

子 agent 派出去跑，**主 agent 只收一行结论 + 结构化引用**。

## 为什么是「另起一个会话」而不是进程内 fork

法穿是「每请求一个 pi 进程」的架构（`pool.py`），审批 extension 靠进程级
env 身份（`FACHUAN_SESSION_ID`）把回调路由回本会话——同一进程无法安全服务
第二个会话。所以子任务走**独立会话 + django-q 后台跑**：

- 不占主会话的进程池槽位（主会话只是挂起等结果）
- 审批、成本、审计全部复用现有链路（子会话自己也有 AgentRun / AgentApproval）
- 崩溃可恢复（django-q 有任务状态）

## 安全边界（三条，缺一不可）

1. **只读工具白名单**：子会话只允许 `get_* / list_* / search_* / read_*`。
   研究类子任务在设计上就没有写能力，中途抓到的提示注入**没有可作用的对象**
   ——这是生态里 `pi-research` 的做法，比事后检测可靠得多。
2. **子任务不得发起高风险操作**：`approval-gate.ts` 在 `agent_depth > 0` 时
   对高危工具**直接 deny**（而非 ask），理由写清「须由主会话确认」。
3. **总预算闸**：一次主会话最多 3 个并发子任务、每个最多 8 轮、
   总 token 上限。不设的话 4 个并发请求各派 4 个子 agent = 16 路打共享 MCP，
   而 MCP 背后是**真实数据库**。

## 结论怎么回到主 agent

子会话跑完，把**最后一条 assistant 消息原文**（不是 SSE 拼接、不是屏幕抓取）
连同 token 成本一起返回。这与「`AgentMessage` 表是审计权威」的既有设计一致。
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AgentSubtask(models.Model):
    """一次子 agent 派发。"""

    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "已完成"
        FAILED = "failed", "失败"
        TIMEOUT = "timeout", "已超时"
        CANCELLED = "cancelled", "已取消"

    class Kind(models.TextChoices):
        #: 只读调研（默认，也是唯一放开的类型）
        RESEARCH = "research", "调研"

    subtask_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="子任务标识",
    )
    parent_session = models.ForeignKey(
        "agent.AgentSession",
        on_delete=models.CASCADE,
        related_name="subtasks",
        verbose_name="主会话",
    )
    #: 子会话（独立 AgentSession，有自己的 pi session 目录与消息表）
    child_session = models.ForeignKey(
        "agent.AgentSession",
        on_delete=models.SET_NULL,
        related_name="parent_subtask",
        null=True,
        blank=True,
        verbose_name="子会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_subtasks",
        null=True,
        blank=True,
        verbose_name="发起人",
    )
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.RESEARCH,
        verbose_name="类型",
    )
    #: 派给子 agent 的任务说明（主 agent 写的 prompt）
    prompt = models.TextField(verbose_name="任务说明")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        verbose_name="状态",
    )
    #: 子 agent 的最终答复原文（从 AgentMessage 读，不是 SSE 拼接）
    result = models.TextField(blank=True, default="", verbose_name="结论")
    error = models.TextField(blank=True, default="", verbose_name="错误")
    tokens = models.IntegerField(default=0, verbose_name="消耗 token")
    duration_ms = models.IntegerField(default=0, verbose_name="耗时（毫秒）")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")

    class Meta:
        verbose_name = "Agent 子任务"
        verbose_name_plural = "Agent 子任务"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["parent_session", "-created_at"], name="agent_subtask_parent_idx"),
            models.Index(fields=["status", "-created_at"], name="agent_subtask_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.status} {self.kind} {self.subtask_id}"
