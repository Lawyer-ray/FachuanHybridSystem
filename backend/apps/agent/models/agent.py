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
from django.core.files.storage import default_storage
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


class AgentSession(models.Model):
    """一次 agent 对话会话。"""

    class Status(models.TextChoices):
        ACTIVE = "active", "进行中"
        ARCHIVED = "archived", "已归档"

    class TaskState(models.TextChoices):
        """任务式（后台）运行的状态。

        只对 ``origin=task`` 的会话有意义；对话式会话用的是 ``status``。
        分开的原因：对话是「有人盯着、随时可插话」，任务式是「挂后台、回来收」，
        前者关心「是否进行中」，后者关心「跑完没有 / 结果在哪」。
        """

        QUEUED = "queued", "排队中"
        RUNNING = "running", "运行中"
        SUCCEEDED = "succeeded", "已完成"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"

    class Origin(models.TextChoices):
        """会话从哪个入口发起。

        同一套运行时服务三种入口，落库时要能区分：对话页要「我的全部会话」，
        案件页要「这个案件的 AI 记录」，任务式要「我挂后台跑完的那几件」。
        不记录来源的话，这三件事都做不了。
        """

        CHAT = "chat", "对话"
        CASE = "case", "案件内"
        CONTRACT = "contract", "合同内"
        TASK = "task", "任务式（后台）"
        #: 子 agent 会话：主会话派出的只读调研任务。单独标一个 origin
        #: 而不是复用 task，因为它们的可见性完全不同——子会话不该出现在
        #: 律师的会话列表里（否则一次调研能刷出三条无头会话）。
        SUBTASK = "subtask", "子任务（子 agent）"

    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="会话标识",
    )
    title = models.CharField(max_length=200, blank=True, default="", verbose_name="标题")
    #: 业务范围名透传属性（列表接口 annotate_scope_names 批量注水，非库字段；
    #: 类级默认让未注水的单会话读取安全返回空串）
    scope_name: str = ""
    origin = models.CharField(
        max_length=16,
        choices=Origin.choices,
        default=Origin.CHAT,
        verbose_name="来源入口",
    )
    #: 案件 / 合同 id。**不加外键**：agent 不该因业务表被删而级联丢审计记录，
    #: 也不希望这里引入跨 app 的迁移依赖。归属校验仍以 user 为准，
    #: 案件维度只用来「列出本案相关会话」。
    case_id = models.BigIntegerField(null=True, blank=True, verbose_name="关联案件")
    contract_id = models.BigIntegerField(null=True, blank=True, verbose_name="关联合同")
    #: 任务式运行的进度（非 task 会话留空）
    task_state = models.CharField(
        max_length=16,
        choices=TaskState.choices,
        blank=True,
        default="",
        verbose_name="任务状态",
    )
    #: 后台任务的对外句柄（django-q task id），用于查询 / 取消
    task_id = models.CharField(max_length=64, blank=True, default="", verbose_name="后台任务标识")
    #: 完成/失败时间；用户据此判断「要不要现在去看」
    task_finished_at = models.DateTimeField(null=True, blank=True, verbose_name="任务完成时间")
    #: 失败原因（人话，不含堆栈）
    task_error = models.CharField(max_length=255, blank=True, default="", verbose_name="任务失败原因")
    #: 是否已向用户投递完成通知（避免重复打扰）
    notified = models.BooleanField(default=False, verbose_name="已通知")
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
            models.Index(fields=["case_id", "-updated_at"], name="agent_session_case_idx"),
            models.Index(fields=["origin", "-updated_at"], name="agent_session_origin_idx"),
            models.Index(fields=["origin", "task_state", "-updated_at"], name="agent_session_task_idx"),
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
        ]

    def __str__(self) -> str:
        return f"{self.tool_name} [{self.status}]"

    @property
    def is_granted(self) -> bool:
        """唯一的放行条件。"""
        return self.status == self.Status.APPROVED


class AgentRun(models.Model):
    """一轮对话的运行记录 —— 成本、耗时与结果。

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
    model = models.CharField(max_length=100, blank=True, default="", verbose_name="模型")
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


class AgentAttachment(models.Model):
    """对话附件 —— 用户拖拽/选择上传给 AI 助手的文件。

    ## 设计要点

    - **文件内容不进模型上下文**：MCP 工具 ``read_agent_attachment``
      在服务端读文件、走 /document-parsing 提取**文本**后返回——
      base64/大文件只在服务端流转，模型只看到正文。
    - **归属随会话**：挂在 session 上（删会话级联清理记录与物理文件），
      归属校验仍以 user 为准——传别人的 attachment_id 读不到任何内容。
    - **存储走全局规范**：`save_uploaded_file`（清洗/校验/限额）+
      ``DatedUUIDPath(MediaEntity.AGENT_ATTACHMENTS)`` 工厂路径，
      CharField 存路径属「工具模块附件」特例，post_delete 连带清理物理文件。
    """

    attachment_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="附件标识",
    )
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="所属会话",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_attachments",
        null=True,
        blank=True,
        verbose_name="上传人",
    )
    filename = models.CharField(max_length=255, verbose_name="原始文件名")
    storage_path = models.CharField(max_length=500, verbose_name="存储路径")
    mime = models.CharField(max_length=100, blank=True, default="", verbose_name="MIME 类型")
    size = models.IntegerField(default=0, verbose_name="大小（字节）")
    #: 引用型附件（拖拽绑定文件夹文件进来）指向绑定文件夹内的原文件：
    #: **storage_path 留空**（post_delete 物理清理只认 storage_path，绝不触碰
    #: 业务归档原文件），读取走 folder_refs 服务（ACL + 逃逸校验在解析层）。
    #: ref_owner_kind 决定 ref_owner 指向合同还是案件（存量行没有该字段值
    #: 时按 contract 处理）；合同绑定与案件绑定是两套独立的文件夹。
    ref_owner_kind = models.CharField(
        max_length=16,
        blank=True,
        default="contract",
        verbose_name="引用归属类型",
        choices=[("contract", "合同"), ("case", "案件")],
    )
    ref_contract_id = models.BigIntegerField(null=True, blank=True, verbose_name="引用归属 id（合同或案件）")
    ref_subpath = models.CharField(max_length=500, blank=True, default="", verbose_name="引用子路径")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    class Meta:
        verbose_name = "Agent 附件"
        verbose_name_plural = "Agent 附件"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="agent_attach_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.filename} ({self.size}B)"


@receiver(post_delete, sender=AgentAttachment)
def _delete_agent_attachment_file(sender: type[AgentAttachment], instance: AgentAttachment, **kwargs: object) -> None:
    """删除附件记录时连带清理物理文件（media 规范：CharField 路径特例必须配 post_delete）。"""
    if instance.storage_path:
        try:
            default_storage.delete(instance.storage_path)
        except Exception:
            # 物理文件清理失败不影响记录删除；孤儿文件可由定期巡检收拾
            import logging

            logging.getLogger(__name__).warning("agent 附件物理文件删除失败: %s", instance.storage_path, exc_info=True)


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
