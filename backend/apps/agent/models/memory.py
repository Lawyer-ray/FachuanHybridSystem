"""Agent 记忆模型 —— 个人 / 团队 / 律所三级。

## 为什么需要这张表

pi 的 session 只提供**会话内**记忆（`--session-id` + compaction）。换会话即清零，
compaction 还会主动丢弃旧细节——这是遗忘机制，不是记忆机制。律师反复强调的
偏好（「文书先给结论再给理由」）、团队惯例（「法院函件控制在 800 字内」）、
所内规范（「刑事阅卷笔录按三栏式」）每次都要重讲一遍。

本表把这类跨会话知识持久化到 Django 侧，经 MCP 工具面读写，由
``services/memory/`` 包做检索与注入渲染。

## 为什么不用 pi-memory 那类文件方案

``pi-memory``（npm）把记忆写成 ``~/.pi/agent/memory/*.md``。它的前提假设是
「一个开发者一台机器一个 HOME」，放进本系统有六个硬冲突：

1. **单目录 = 单人**：全局 ``~/.pi`` 下没有用户/团队/律所维度，所有律师共用
   一份记忆——法律行业里这是保密义务违规，不是体验问题；
2. **明文落盘**：记忆内容含客户情况、案件偏好，违反「不落盘明文」纪律；
3. **多进程并发写**：``pool.acquire()`` 每请求起一个 pi 进程，多个进程
   ``writeFileSync`` 同一个文件且无锁，读-改-写互相覆盖；
4. **``session_shutdown`` 不一定触发**：本系统「用完关闭」，取消路径走
   ``abort_running=True``，抽取时机不可靠；
5. **依赖 qmd/bun**：为一个检索引入 Bun 二进制，而我们已有
   ``LLMProvider.embedding_model`` 与 ``apps/litigation_ai`` 的 JSON 向量先例；
6. **无法治理**：注入的是模型自己写的自由文本，无法审批、无法按人过滤、
   无法审计「这条记忆哪来的」。

借它的**架构**（三层语义、快照式注入、软删可恢复），不借它的**存储**。

## 三层不是「合并」，是「提升」

团队/律所记忆**禁止自动聚合**个人记忆。原因：

- 律师 A「这个客户同意分期」+ B「这个客户拒绝分期」→ 聚合后模型看到矛盾；
- A 的个人风格进团队层 = 强加给全所；
- A 记住了某案保密和解金额 → 团队可见即泄密。

所以只有 ``promote_memory()``（管理员挑选 + 强制改写 + PII 闸门）这一个入口，
且每条都留 ``promoted_from`` 指针可溯源。个人层自动、团队/律所层人工，这个
边界不模糊。

## 为什么 embedding 用 JSONField 而不是 pgvector

规模自证：一名律师几百条、一个律所几千条记忆。``apps/litigation_ai`` 的
``EvidenceChunk.embedding`` 已用 JSONField + Python 余弦跑通同量级检索。
为这个数据量引入 pgvector 扩展、索引维护与部署依赖不成正比。

## 项目锚点：A 律师的判断怎么让 B 律师用上

同一个团队里 2-3 人办同一个案件是常态，而 pi session 是**按会话、按人**的，
A 跟 AI 捋清楚的判断 B 完全看不到，只能重问一遍。所以给记忆加 ``contract_id``
/ ``case_id`` 两个锚点字段：写入时挂到项目/案件上，注入时按当前会话的锚点
取回来——**跨会话共享的是「判断」，不是「谈话记录」**（把 A 的 pi session
挂给 B 会让 B 继承 A 的试错与偏见，且破坏 prompt cache 前缀稳定性）。

为什么共享单元是**项目（合同）**而不是案件：非诉没有案件，只有合同；而案件
本身挂在合同下（``Case.contract``，合同指派还会同步成案件指派）。
为什么可见性是**同律师团队**而不是“项目成员”：两者在此系统里等价（
``org_access["lawyers"]`` 就是团队成员全集），项目成员不存在独立身份。

写入走 ``write.create_note()``（三个人都能写，append-only），确认走
``write.confirm_note()``（点一下才升为“项目事实”，可再改写）。
"""

from __future__ import annotations

import hashlib
import uuid
from typing import ClassVar

from django.db import models
from django.db.models import Q


def content_hash_of(content: str) -> str:
    """记忆内容指纹 —— 去重与「同一事实被反复抽取」的幂等锚点。

    归一化后取 sha256：自动抽取常把同一句话在措辞上微调（多一个句号、
    多一个空格），直接比对原文会重复入库。
    """
    normalized = " ".join((content or "").split()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class AgentMemory(models.Model):
    """一条跨会话记忆。

    作用域三选一由 ``scope`` 决定，对应字段恰好一个非空（数据库 CHECK 约束
    保证）。这种写法比三个子类 + 多表继承更简单：查询与注入渲染都是一条
    ``filter(scope=...)``，不需要 union。
    """

    class Scope(models.TextChoices):
        LAWYER = "lawyer", "个人"
        TEAM = "team", "团队"
        LAW_FIRM = "law_firm", "律所"

    class Kind(models.TextChoices):
        #: 具体事实（「XX 客户要求发票开增值税专用」）
        FACT = "fact", "事实"
        #: 工作偏好（「文书先给结论再给理由」）
        PREFERENCE = "preference", "偏好"
        #: 惯例 / SOP（「法院函件控制在 800 字内」）
        PROCEDURE = "procedure", "惯例"
        #: 纠正（「上次那条已过期：XX 案已调解结案」）
        CORRECTION = "correction", "纠正"
        #: 长篇操作指引。**不进快照注入**，只以索引行出现，模型按需用
        #: ``recall_memory`` 取全文。为什么单独一类：注入通道单条上限 200 字、
        #: 律所层配额 700 字，一份 36 行的「阅卷规范」塞进去会被直接跳过，
        #: 律师会以为记忆坏了。短规则走注入，长指引走按需——两条通道各尽其职。
        PLAYBOOK = "playbook", "操作指引"

    class Status(models.TextChoices):
        #: 自动抽取待律师确认。默认档位——提示注入污染过的会话能往这里写，
        #: 但确认前不进上下文。
        PENDING = "pending", "待确认"
        ACTIVE = "active", "生效"
        #: 软删。保留行以支持恢复（借 pi-memory 的 forget/restore 语义）。
        DELETED = "deleted", "已删除"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    scope = models.CharField(max_length=16, choices=Scope.choices, verbose_name="作用域")

    # 三选一，由 CHECK 约束保证恰好一个非空
    lawyer = models.ForeignKey(
        "organization.Lawyer",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_memories",
        verbose_name="所属律师",
    )
    team = models.ForeignKey(
        "organization.Team",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_memories",
        verbose_name="所属团队",
    )
    law_firm = models.ForeignKey(
        "organization.LawFirm",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="agent_memories",
        verbose_name="所属律所",
    )

    kind = models.CharField(max_length=16, choices=Kind.choices, verbose_name="类型")
    content = models.TextField(verbose_name="记忆内容")
    #: 指纹永远由内容派生（service 写入口经 ``content_hash_of`` 计算），
    #: 不接受外部传入，否则去重约束可被绕过。Model 层不做该业务计算。
    content_hash = models.CharField(max_length=64, db_index=True, verbose_name="内容指纹")

    #: 语义检索用向量。空列表表示尚未 embed（自动抽取的任务会补），
    #: 此时检索退化为关键词匹配而不是直接漏掉。
    embedding = models.JSONField(default=list, blank=True, verbose_name="向量")

    # ── 项目/案件锚点（与 scope 正交）────────────────────────────────
    #
    # ``scope`` 回答「**谁能看**」（个人/团队/律所），锚点回答「**属于哪个项目**」
    # （注入到哪个项目的会话）。两个维度正交，不能合并：
    #
    # - 一条个人记忆挂到某项目 → 同团队的人在**这个项目**的会话里能看到它；
    # - 同一条个人记忆不挂锚点 → 仍然只按原来的三层可见性走。
    #
    # 为什么不改 ``scope`` 加一个 ``project`` 档：可见性真相是「同律师团队」
    # （``OrgAccessComputationService`` 算出的 ``org_access["lawyers"]``），
    # 再加一档会引入第二套权限语义，两套迟早漂移。
    #
    # 为什么用整数不加外键：照 ``models/session.py`` 的先例——agent 不该因
    # contracts/cases 表删除而丢审计记录或级联，也不引入跨 app 迁移依赖。
    contract_id = models.BigIntegerField(null=True, blank=True, db_index=True, verbose_name="项目（合同）id")
    case_id = models.BigIntegerField(null=True, blank=True, verbose_name="案件 id")

    # ── 项目事实的确认（"必须人点一下"）────────────────────────────
    #
    # 区分「流水判断」与「项目事实」**不用再加一个 tier 枚举**：
    # ``confirmed_at`` 为空 = 模型/律师随手写的判断（可被 supersede）；
    # 非空 = 有人点过确认的项目事实（改动需再次确认）。
    #
    # 为什么不用 tier：``kind`` 已经承担「这条记忆是什么性质」（事实/偏好/
    # 惯例/纠正/指引），再叠一个同名字段，``kind=fact`` 与 ``tier=judgment``
    # 这种自相矛盾的行一定会出现。用时间戳表达「确认与否」既无枚举冲突，
    # 又白拿一份「谁在什么时候认的」审计。
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    confirmed_by = models.ForeignKey(
        "organization.Lawyer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_agent_memories",
        verbose_name="确认人",
    )

    #: 被本条推翻的旧条目。**失效不删除**：旧行留在库里，`status=DELETED`
    #: 之外只看 ``supersedes`` 链就能回答「当时是怎么认定的」（Graphiti 的
    #: 失效语义，不引图库）。``SET_NULL`` 而非 CASCADE：删掉一条旧事实
    #: 不该连带抹掉那条更正记录。
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_by",
        verbose_name="推翻的旧条目",
    )

    # ── 溯源 ──────────────────────────────────────────────────────────
    #: 这条记忆是哪次对话得出的。前端点开可看到来源，这是律师敢用的前提。
    source_session = models.ForeignKey(
        "agent.AgentSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memories",
        verbose_name="来源会话",
    )
    #: 团队/律所记忆的来源个人记忆链。个人记忆被删时可感知。
    promoted_from = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="promoted_to",
        verbose_name="提炼自",
    )
    #: 自动抽取 < 1，人工录入/策展 = 1。注入时低的排后面。
    confidence = models.FloatField(default=1.0, verbose_name="置信度")

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="状态",
    )

    #: 命中计数 —— 注入排序与「高频优先」策展候选池的依据。
    hit_count = models.IntegerField(default=0, verbose_name="命中次数")
    last_hit_at = models.DateTimeField(null=True, blank=True, verbose_name="最近命中")

    #: 衰减锚点：**最后一次被后来的证据重新证实**的时间，与「最后修改」分开。
    #:
    #: 为什么必须分开（借 pi-memory-evolution 的 reinforcedAt 设计）：如果用
    #: ``updated_at`` 做衰减，那么「仅被重新证实、内容未变」的写入也会把它推向
    #: 将来，一条陈旧但经常被命中的记忆就永远不会衰减；反过来，修正一条措辞
    #: 也会无辜地把它「续命」。命中只刷新本字段，修改才动 ``updated_at``。
    reinforced_at = models.DateTimeField(null=True, blank=True, verbose_name="最近证实时间")

    created_by = models.ForeignKey(
        "organization.Lawyer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_agent_memories",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "Agent 记忆"
        verbose_name_plural = "Agent 记忆"
        ordering = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            # 注入查询主路径：按作用域 + 状态取，再按置信度/命中排序
            models.Index(fields=["scope", "status"], name="agent_mem_scope_status_idx"),
            models.Index(fields=["lawyer", "status"], name="agent_mem_lawyer_status_idx"),
            models.Index(fields=["team", "status"], name="agent_mem_team_status_idx"),
            models.Index(fields=["law_firm", "status"], name="agent_mem_firm_status_idx"),
            # 项目注入主路径：按锚点取「本项目/本案」的条目
            models.Index(fields=["contract_id", "case_id", "status"], name="agent_mem_anchor_idx"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # scope 与归属字段必须自洽，且恰好一个非空
            models.CheckConstraint(
                condition=(
                    Q(scope="lawyer", lawyer__isnull=False, team__isnull=True, law_firm__isnull=True)
                    | Q(scope="team", lawyer__isnull=True, team__isnull=False, law_firm__isnull=True)
                    | Q(scope="law_firm", lawyer__isnull=True, team__isnull=True, law_firm__isnull=False)
                ),
                name="agent_memory_scope_owner_consistent",
            ),
            # 同一作用域内同一内容只存一次（个人按人、团队按团队、律所按所）
            models.UniqueConstraint(
                fields=["lawyer", "content_hash"],
                condition=Q(scope="lawyer", status__in=["pending", "active"]),
                name="uniq_agent_memory_lawyer_content",
            ),
            models.UniqueConstraint(
                fields=["team", "content_hash"],
                condition=Q(scope="team", status__in=["pending", "active"]),
                name="uniq_agent_memory_team_content",
            ),
            models.UniqueConstraint(
                fields=["law_firm", "content_hash"],
                condition=Q(scope="law_firm", status__in=["pending", "active"]),
                name="uniq_agent_memory_firm_content",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.get_scope_display()}/{self.get_kind_display()}] {self.content[:40]}"
