"""以「项目文件夹里的那一份文件」为坐标的审查模型。

## 为什么不是 `ReviewTask`

旧模型是「一次上传 → 一个任务 → 一份产物 docx」。它与文件夹里那份文件**没有任何
关系**：律师在文件夹里改完它不知道，一次审查的结果挂不回文件，想审第二次必须
再上传一次。于是「AI 审查」永远活在另一个页面里。

这里的坐标直接沿用 `ContractWritePatch` / `DocSnapshot` 已经在用的三元组：

    (owner_kind, owner_id, subpath)

审查、修订、版本快照、裁决全在同一个坐标系里，不需要任何映射。
**审查不产生第二份 docx**——结论要么是修订、要么是批注，都落在原文件上。

## 三个正交维度，不要挤成一列

| 维度 | 取值 | 回答的问题 |
|---|---|---|
| `verdict` | compliant / deviation / missing / not-applicable | 这条**该不该改** |
| `severity` | high / medium / low | **不改会亏多少** |
| `kind` | risk / typo / format / manual | **这是哪一类活** |

「偏离我方标准但后果轻微」和「完全符合标准但后果严重」的正确动作完全不同
（谈 vs 改）。挤进一个 `severity` 就表达不了。

`not-applicable` 单独存在的意义：它把覆盖率从糊涂账变成可算的分数。
分母 = 适用条款数，分子 = 已满足数。没有这一档，一份只有 6 条可审条款的框架协议
会被算成「47 条标准里满足 6 条 = 12 分」。
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class RunStatus(models.TextChoices):
    QUEUED = "queued", "排队中"
    RUNNING = "running", "审查中"
    DONE = "done", "已完成"
    FAILED = "failed", "失败"
    SUPERSEDED = "superseded", "已被新一轮取代"


class Verdict(models.TextChoices):
    COMPLIANT = "compliant", "符合"
    DEVIATION = "deviation", "偏离"
    MISSING = "missing", "缺失"
    NOT_APPLICABLE = "not_applicable", "不适用"


class Severity(models.TextChoices):
    HIGH = "high", "高"
    MEDIUM = "medium", "中"
    LOW = "low", "低"


class FindingKind(models.TextChoices):
    RISK = "risk", "风险"
    TYPO = "typo", "错别字"
    FORMAT = "format", "格式"
    MANUAL = "manual", "人工痕迹"


class Delivery(models.TextChoices):
    """这条结论用哪种载体交付。"""

    REVISION = "revision", "修订痕迹"
    COMMENT = "comment", "批注"
    BOTH = "both", "修订 + 批注"
    LIST_ONLY = "list_only", "只进清单"


class FindingStatus(models.TextChoices):
    """结论的生命周期。

    `stale` / `moot` / `merged` / `unanchored` 四个态不加，必然出现：
    律师边改边审，清单里出现「建议把 X 改成 Y」而 X 早就没了 → 点「定位」跳到
    空白处 → 信任损毁只发生一次。
    """

    PROPOSED = "proposed", "待决"
    ACCEPTED = "accepted", "已采纳"
    REJECTED = "rejected", "已驳回"
    STALE = "stale", "锚点失效"
    MOOT = "moot", "已被消解"
    MERGED = "merged", "已合并"
    UNANCHORED = "unanchored", "锚不到"


class RejectReason(models.TextChoices):
    """驳回理由**必须是理由码**，不是自由文本。

    自由文本永远没法统计：误报率、同类条款降权、给客户的「评估 47 条采纳 31 条」
    全都算不出来。
    """

    COMMERCIAL = "commercial", "商业让步"
    JURISDICTION = "jurisdiction", "法域不适"
    ALREADY_COVERED = "already_covered", "已被其他条款覆盖"
    FALSE_POSITIVE = "false_positive", "误报"
    CLIENT_REFUSED = "client_refused", "客户明确拒绝"
    OTHER = "other", "其他"


class Stance(models.TextChoices):
    PARTY_A = "party_a", "代表甲方"
    PARTY_B = "party_b", "代表乙方"
    NEUTRAL = "neutral", "中立复核"


class ReviewRun(models.Model):
    """一次审查动作（不是一份文档副本）。"""

    id: int

    owner_kind: Any = models.CharField(
        "所属文件夹类型", max_length=16, choices=[("contract", "合同"), ("case", "案件")], db_index=True
    )
    owner_id: Any = models.IntegerField("所属合同/案件 ID", db_index=True)
    subpath: Any = models.CharField("文件夹内相对路径（posix）", max_length=1000)

    content_sha256: Any = models.CharField(
        "被审内容的 sha256",
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="与 DocSnapshot.sha256 对齐；不一致说明审的不是当前这一版",
    )
    base_snapshot_seq: Any = models.IntegerField("起始快照号", null=True, blank=True)

    contract_type: Any = models.CharField("合同类型（决定用哪套标准）", max_length=64, blank=True, default="")
    stance: Any = models.CharField("立场", max_length=16, choices=Stance.choices, default=Stance.NEUTRAL)
    playbook_key: Any = models.CharField("采用的标准库", max_length=120, blank=True, default="")
    playbook_version: Any = models.IntegerField("标准库版本", null=True, blank=True)
    playbook_snapshot: Any = models.JSONField(
        "标准快照",
        default=list,
        blank=True,
        help_text="本次实际用的规则快照；标准改版后仍能解释「当时为什么这么判」",
    )

    status: Any = models.CharField(
        "状态", max_length=16, choices=RunStatus.choices, default=RunStatus.QUEUED, db_index=True
    )
    parent_run: Any = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reruns",
        verbose_name="上一轮（delta 再审查时指回去）",
    )
    summary: Any = models.JSONField("汇总（覆盖率 / 条数 / Top-3）", default=dict, blank=True)
    error_message: Any = models.TextField("失败原因", blank=True, default="")

    created_by_id: Any = models.IntegerField("发起人 user id", null=True, blank=True)
    created_at: Any = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)
    finished_at: Any = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "审查轮次"
        verbose_name_plural = "审查轮次"
        ordering = ["-created_at", "-id"]
        indexes: ClassVar[list[Any]] = [models.Index(fields=["owner_kind", "owner_id", "subpath", "created_at"])]

    def __str__(self) -> str:
        return f"{self.owner_kind}/{self.owner_id}/{self.subpath} run#{self.id} {self.status}"


class Finding(models.Model):
    """一条审查结论。"""

    id: int

    run: Any = models.ForeignKey(ReviewRun, on_delete=models.CASCADE, related_name="findings", verbose_name="审查轮次")
    ordinal: Any = models.IntegerField("本轮内序号", default=0)

    verdict: Any = models.CharField("结论", max_length=16, choices=Verdict.choices, default=Verdict.DEVIATION)
    severity: Any = models.CharField("严重度", max_length=8, choices=Severity.choices, default=Severity.MEDIUM)
    kind: Any = models.CharField("类型", max_length=8, choices=FindingKind.choices, default=FindingKind.RISK)
    clause_type: Any = models.CharField("条款类型", max_length=64, blank=True, default="")

    rule_key: Any = models.CharField("违反的标准条款", max_length=120, blank=True, default="")
    legal_basis: Any = models.CharField("法律依据", max_length=255, blank=True, default="")

    quote: Any = models.TextField("被审原文", blank=True, default="")
    title: Any = models.CharField("一句话结论", max_length=200, blank=True, default="")
    reason: Any = models.TextField("理由（给律师看的）", blank=True, default="")

    suggestion_original: Any = models.TextField("要替换的原文", blank=True, default="")
    suggestion_replacement: Any = models.TextField("改写后的文本", blank=True, default="")
    suggestion_note: Any = models.TextField("批注正文（delivery 含 comment 时用）", blank=True, default="")

    delivery: Any = models.CharField("交付载体", max_length=12, choices=Delivery.choices, default=Delivery.REVISION)
    status: Any = models.CharField(
        "决策状态", max_length=12, choices=FindingStatus.choices, default=FindingStatus.PROPOSED, db_index=True
    )

    reject_reason_code: Any = models.CharField(
        "驳回理由码", max_length=24, choices=RejectReason.choices, blank=True, default=""
    )
    reject_note: Any = models.CharField("驳回补充说明", max_length=255, blank=True, default="")
    decided_by_id: Any = models.IntegerField("裁决人 user id", null=True, blank=True)
    decided_at: Any = models.DateTimeField("裁决时间", null=True, blank=True)

    docx_rev_ids: Any = models.JSONField("落笔写入的修订号", default=list, blank=True)
    comment_ids: Any = models.JSONField("落笔写入的批注号", default=list, blank=True)

    created_at: Any = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "审查结论"
        verbose_name_plural = "审查结论"
        ordering = ["run_id", "ordinal", "id"]
        indexes: ClassVar[list[Any]] = [models.Index(fields=["status", "severity"])]

    def __str__(self) -> str:
        return f"finding#{self.id} {self.verdict}/{self.severity} {self.title[:20]}"
