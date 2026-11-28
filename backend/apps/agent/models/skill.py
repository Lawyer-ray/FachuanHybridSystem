"""Agent 技能模型 —— 注册表（个人 / 团队 / 所内预留）+ 修订历史 + 用户偏好。

## 三个模型的分工

- ``AgentSkill``：统一注册表。P0 只允许 ``scope=lawyer``（个人技能），
  ``team`` / ``law_firm`` 两个归属字段与唯一约束**现在就建好**，将来加团队/所内
  技能不改表、不改主键、不改前端类型形状。
- ``AgentSkillRevision``：只增不改的版本快照（``(skill, version)`` 唯一），
  保留最近 20 版由 service 层裁剪（见 ``services/skills/user_skills.py``）。
- ``AgentSkillPreference``：用户对**技能启用面**的偏好。内置技能是随代码发布的
  目录（``pi/skills/<name>/SKILL.md``），没有数据库行，所以偏好不能挂外键——
  ``skill_key`` 是两者的公共身份：``builtin:<name>`` / ``skill:<uuid>``。

## 为什么一张表装三个作用域

与 ``AgentMemory`` 同因（见 ``models/memory.py``）：查询、解析、渲染都是一条
``filter(scope=...)``，不需要 union；将来「提升到团队」只是改 ``scope`` + 归属
字段，原地保留 id 与审计链。作用域与归属字段必须自洽且恰好一个非空——由
``CheckConstraint`` 在数据库层保证，不靠调用方自觉。

## 与记忆的一处刻意差异

记忆的团队层允许任一团队成员策展（``services/memory/scopes.py``）；技能是
**行为指令**，一次误发布会让整个团队的 AI 按错流程走且当事人难以察觉，所以
团队/所内层必须走管理员审批（见 ``services/skills/review.py``）。

## 双轨发布：``status`` 与 ``review_status`` 必须正交

共享技能（team / law_firm）在编辑后**不能**把新正文就地写进线上槽位：
那一行同时承载「线上生效版」与「工作区最新版」两个真相，任何一次原地改
都会同时破坏两件事——线上立刻换成没审过的内容，或者为保住线上而丢掉作者
刚写的东西。

所以这里把两件事拆成两个字段：

- ``status`` 只表示**线上槽位**生命周期（``draft`` / ``active`` / ``archived``），
  永远不出现「待审」这个值；
- ``review_status`` 表示**修订流**状态（``none`` / ``pending`` / ``rejected``）；
- ``published_revision`` 指向**当前线上生效的那份已审批快照**。

编辑一份生效中的共享技能 = 改工作区字段 + 写新 ``AgentSkillRevision`` +
``review_status=pending``，而 ``status`` 保持 ``active``、``published_revision``
纹丝不动。运行时交付路径（``resolve.resolve_for_user``）**只读
``published_revision``**，所以审批期间线上零中断、驳回也毫发无损。

个人技能不需要这套：``published_revision`` 恒为空，读路径直接读本体。
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q


class AgentSkill(models.Model):
    """一条技能（P0 只允许 ``scope=lawyer``；team/law_firm 字段为三级预留）。"""

    class Scope(models.TextChoices):
        LAWYER = "lawyer", "个人"
        TEAM = "team", "团队"
        LAW_FIRM = "law_firm", "所内"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "生效"
        ARCHIVED = "archived", "已下线"

    class ReviewStatus(models.TextChoices):
        """修订流状态（与 ``Status`` 正交，见模块 docstring）。

        个人技能恒为 ``none``——自己的技能自己说了算，走审批只会让个人技能
        变成没人用的摆设。
        """

        NONE = "none", "无待审"
        PENDING = "pending", "待审核"
        REJECTED = "rejected", "已驳回"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.LAWYER)
    #: 三选一，CHECK 约束保证恰好一个非空（与 AgentMemory 同构）
    lawyer = models.ForeignKey(
        "organization.Lawyer",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_skills",
        verbose_name="所属律师",
    )
    team = models.ForeignKey(
        "organization.Team",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_skills",
        verbose_name="所属团队",
    )
    law_firm = models.ForeignKey(
        "organization.LawFirm",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_skills",
        verbose_name="所属律所",
    )

    #: slug：物化目录名 / ``/skill:`` 命令名（Agent Skills 规范：小写字母/数字/连字符）
    name = models.CharField(max_length=64, verbose_name="技能名")
    title = models.CharField(max_length=64, verbose_name="显示名")
    #: 单行路由描述：会进系统提示，渲染时折叠空白
    description = models.CharField(max_length=400, verbose_name="路由描述")
    body = models.TextField(verbose_name="正文")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    enabled = models.BooleanField(default=True, verbose_name="启用")

    # ── 双轨发布（仅共享技能有意义）──────────────────────────────
    #: 修订流状态；个人技能恒 ``none``
    review_status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.NONE, verbose_name="审核状态"
    )
    #: 驳回理由：审批人要写清「哪里不行」，否则作者只能盲改
    review_note = models.TextField(blank=True, default="", verbose_name="审核备注")
    #: 当前线上生效的已审批快照（共享技能的运行时唯一正文来源）
    published_revision = models.ForeignKey(
        "AgentSkillRevision",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="线上生效版本",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="审核人",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="审核时间")
    #: 本次发布真正生效的时刻（审核时间与生效时间可能不同：审核后还要勾选确认）
    activated_at = models.DateTimeField(null=True, blank=True, verbose_name="生效时间")
    source = models.CharField(max_length=16, default="manual", verbose_name="来源")
    version = models.PositiveIntegerField(default=1, verbose_name="版本")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Agent 技能"
        verbose_name_plural = "Agent 技能"
        ordering = ["name"]
        indexes: ClassVar[list[models.Index]] = [
            # 未来团队/所内解析的主路径：按作用域 + 律所 + 状态取
            models.Index(fields=["scope", "law_firm", "status"], name="agent_skill_firm_status_idx"),
            models.Index(fields=["team", "status"], name="agent_skill_team_status_idx"),
            # 个人解析主路径：按人取启用行
            models.Index(fields=["lawyer", "enabled"], name="agent_skill_lawyer_enabled_idx"),
            # 审批面板主路径：本所/本团队的待审条目
            models.Index(fields=["status", "review_status"], name="agent_skill_review_queue_idx"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # scope 与归属字段必须自洽，且恰好一个非空
            models.CheckConstraint(
                condition=(
                    Q(scope="lawyer", lawyer__isnull=False, team__isnull=True, law_firm__isnull=True)
                    | Q(scope="team", lawyer__isnull=True, team__isnull=False, law_firm__isnull=True)
                    | Q(scope="law_firm", lawyer__isnull=True, team__isnull=True, law_firm__isnull=False)
                ),
                name="agent_skill_scope_owner_consistent",
            ),
            # 同一作用域内同名只允许一条。team / law_firm 两条现在就建：将来加约束时
            # 存量数据已有重复，补约束要停机清洗。内置名是保留字，不参与这些约束。
            models.UniqueConstraint(
                fields=["lawyer", "name"],
                condition=Q(lawyer__isnull=False),
                name="uniq_agent_skill_lawyer_name",
            ),
            models.UniqueConstraint(
                fields=["team", "name"],
                condition=Q(team__isnull=False),
                name="uniq_agent_skill_team_name",
            ),
            models.UniqueConstraint(
                fields=["law_firm", "name"],
                condition=Q(law_firm__isnull=False),
                name="uniq_agent_skill_firm_name",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.get_scope_display()}] {self.title}（{self.name}）"

    @property
    def is_shared(self) -> bool:
        """是否共享作用域（团队 / 所内）——决定走不走双轨发布与审批。"""
        return self.scope in (self.Scope.TEAM, self.Scope.LAW_FIRM)

    @property
    def has_unpublished_changes(self) -> bool:
        """工作区版本是否领先于线上生效版本（审批面板据此显示「有待审修改」）。

        个人技能恒 ``False``：它们没有线上/工作区之分。
        """
        if self.published_revision is None:
            return False
        return self.published_revision.version != self.version


class AgentSkillRevision(models.Model):
    """版本快照（只增不改）：审批与回滚靠它，不靠正文里藏历史。"""

    skill = models.ForeignKey(AgentSkill, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=64)
    description = models.CharField(max_length=400)
    body = models.TextField()
    status = models.CharField(max_length=16)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Agent 技能版本"
        verbose_name_plural = "Agent 技能版本"
        unique_together = (("skill", "version"),)
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"{self.skill_id} v{self.version}"


class AgentSkillPreference(models.Model):
    """用户技能启停偏好（只记差异行）。

    ``skill_key`` 值域 ``builtin:<name>``（随代码发布的内置技能）或
    ``skill:<uuid>``（数据库里的个人/共享技能）。偏好只影响「注入哪些技能目录
    给 pi」（见 ``services/skill_service``），不影响 mcp_server 侧按名读取技能
    内容的工具——那个是模型主动查阅，与注入无关。
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_skill_preferences",
        verbose_name="所属用户",
    )
    #: 技能身份：``builtin:<name>`` / ``skill:<uuid>``（见模块 docstring）
    skill_key = models.CharField(max_length=80, verbose_name="技能键")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "技能偏好"
        verbose_name_plural = "技能偏好"
        ordering = ["-updated_at"]
        unique_together = (("user", "skill_key"),)

    def __str__(self) -> str:
        return f"{self.user}:{self.skill_key} → {'on' if self.enabled else 'off'}"
