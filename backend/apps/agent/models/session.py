"""Agent 会话模型。

会话状态归 Django 所有：消息表是审计与回放的权威，pi 原生 session 文件
只负责会话内上下文（见 README「上下文归属」）。多入口（对话 / 案件内 /
合同内 / 任务式 / 子任务）共用同一套持久化，靠 ``origin`` 区分。
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
    #: 本会话使用哪个 agent 后端（对应 `apps.agent.backends` 注册表里的 kind）。
    #:
    #: 默认 `pi` 且历史数据全部回填为 `pi`——引入这个字段时只有一个后端在跑，
    #: 所以「空串 / 未识别」一律按 pi 处理，与引入前行为完全一致。
    #:
    #: 为什么要落到会话而不是用户偏好：同一律师可能在不同会话里用不同 agent
    #: （比如拿不准的案子开两个会话分别问），偏好级配置表达不了这种意图。
    #: 加 db_index 是因为会话列表按来源/用户筛选时，前端要显示每条的 agent 标识。
    agent_kind = models.CharField(
        max_length=32,
        blank=True,
        default="pi",
        db_index=True,
        verbose_name="Agent 后端",
    )
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
            # 项目页按 contract_id 拉会话（诉讼会话由 case→contract 回填后也会命中）；
            # 没有这条索引时是整表扫，会话越多越慢。
            models.Index(fields=["contract_id", "-updated_at"], name="agent_session_contract_idx"),
            models.Index(fields=["origin", "-updated_at"], name="agent_session_origin_idx"),
            models.Index(fields=["origin", "task_state", "-updated_at"], name="agent_session_task_idx"),
        ]

    def __str__(self) -> str:
        return self.title or str(self.session_id)
