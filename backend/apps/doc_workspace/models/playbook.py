"""审查标准库（playbook）：可版本化、可枚举、带立场的检查项。

## 为什么不能继续用「一段写死的提示词」

旧实现把审查框架写成约 140 行硬编码散文（`contract_review/services/review/
contract_reviewer.py` 的 `_REVIEW_FRAMEWORK`），于是：

- **改一版等于全所口径漂移**：谁改的、改了什么、上个月的结论为什么和这个月不一样，
  全部无法回答；
- **无法算覆盖率**：「47 条标准」是散文里的说法，程序数不出来；
- **无法按合同类型路由**：用买卖合同标准去审劳动合同，只会产出噪音——这是过度
  审查的结构性来源。

## 四个必要属性（少一个就会腐化）

| 属性 | 为什么 |
|---|---|
| **立场**（`beneficiary` 逐条声明 + `ReviewRun.stance`） | 同一份合同代表甲/乙方，结论方向相反 |
| **版本快照**（写入 `ReviewRun.playbook_snapshot`） | 标准改版后仍能解释「当时为什么这么判」 |
| **可枚举的检查项** | 这才叫标准条款库；散文不可审计 |
| **按合同类型路由**（`contract_type`） | 见上 |
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from .review import Consequence, Jurisdiction, RuleClass, Severity, Stage, Stance


class PlaybookStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    ACTIVE = "active", "启用"
    ARCHIVED = "archived", "归档"


class Beneficiary(models.TextChoices):
    """这条标准条款**保护谁**。

    立场对齐全靠它：同一条「违约金对等」的偏离，站在受保护一方是高风险，
    站在另一方几乎没有损失。没有这个字段，立场就只是一段写进 prompt 的话，
    程序无法据此调整结论。
    """

    PARTY_A = "party_a", "甲方"
    PARTY_B = "party_b", "乙方"
    NEUTRAL = "neutral", "双向对等"


class Playbook(models.Model):
    """一套审查标准（按合同类型 + 立场）。"""

    id: int

    org_id: Any = models.IntegerField("律所 ID（多所隔离）", null=True, blank=True, db_index=True)
    jurisdiction: Any = models.CharField(
        "适用法域",
        max_length=8,
        choices=Jurisdiction.choices,
        default=Jurisdiction.CN,
        db_index=True,
        help_text="中国法与泰国法是两套强制规则（如租赁上限 20 年 vs 30 年），不能共用一套标准",
    )
    contract_type: Any = models.CharField("合同类型（如 买卖/租赁/服务/劳动）", max_length=64, blank=True, default="")
    stance: Any = models.CharField("适用立场", max_length=16, choices=Stance.choices, default=Stance.NEUTRAL)
    version: Any = models.IntegerField("版本号", default=1)
    status: Any = models.CharField("状态", max_length=12, choices=PlaybookStatus.choices, default=PlaybookStatus.ACTIVE)

    name: Any = models.CharField("名称", max_length=120)
    note: Any = models.TextField("说明", blank=True, default="")

    created_at: Any = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at: Any = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "审查标准库"
        verbose_name_plural = "审查标准库"
        ordering = ["-version", "-id"]
        constraints: ClassVar[list[Any]] = [
            models.UniqueConstraint(
                fields=["org_id", "jurisdiction", "contract_type", "stance", "version"],
                name="uniq_playbook_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}（{self.contract_type or '通用'}/{self.stance}）"


class PlaybookRule(models.Model):
    """一条检查项。"""

    id: int

    playbook: Any = models.ForeignKey(Playbook, on_delete=models.CASCADE, related_name="rules", verbose_name="标准库")
    rule_key: Any = models.CharField("规则标识（跨版本稳定，结论靠它回指）", max_length=120)
    ordinal: Any = models.IntegerField("排序", default=0)

    clause_type: Any = models.CharField("条款类型", max_length=64)
    standard_text: Any = models.TextField("标准表述")
    acceptable_range: Any = models.TextField(
        "可接受区间",
        blank=True,
        default="",
        help_text="允许的偏离范围；留空表示「必须与标准表述一致」",
    )
    legal_basis: Any = models.CharField("法律依据", max_length=255, blank=True, default="")

    beneficiary: Any = models.CharField(
        "保护哪一方", max_length=16, choices=Beneficiary.choices, default=Beneficiary.NEUTRAL
    )
    severity_if_missing: Any = models.CharField(
        "缺失时的严重度", max_length=8, choices=Severity.choices, default=Severity.MEDIUM
    )
    required: Any = models.BooleanField("是否必备条款", default=True)
    rule_class: Any = models.CharField(
        "规则类别",
        max_length=16,
        choices=RuleClass.choices,
        default=RuleClass.CONTRACTUAL,
        help_text="mandatory=违反可能无效，免疫立场降权与条数闸",
    )
    stage: Any = models.CharField("所属阶段", max_length=16, choices=Stage.choices, default=Stage.GENERAL)
    consequence: Any = models.CharField(
        "违反后果档位",
        max_length=16,
        choices=Consequence.choices,
        default=Consequence.BREACH,
        help_text="可能无效 / 不得对抗第三人 / 未生效 / 处罚 / 违约——写进一页纸，避免过度定性或漏判",
    )

    class Meta:
        verbose_name = "审查检查项"
        verbose_name_plural = "审查检查项"
        ordering = ["playbook_id", "ordinal", "id"]
        constraints: ClassVar[list[Any]] = [
            models.UniqueConstraint(fields=["playbook", "rule_key"], name="uniq_playbook_rule_key")
        ]

    def __str__(self) -> str:
        return f"{self.rule_key}（{self.clause_type}）"

    def to_snapshot(self) -> dict[str, Any]:
        """落进 `ReviewRun.playbook_snapshot` 的形态（只留判定要用到的字段）。"""
        return {
            "rule_key": self.rule_key,
            "clause_type": self.clause_type,
            "standard_text": self.standard_text,
            "acceptable_range": self.acceptable_range,
            "legal_basis": self.legal_basis,
            "beneficiary": self.beneficiary,
            "severity_if_missing": self.severity_if_missing,
            "required": self.required,
            "rule_class": self.rule_class,
            "stage": self.stage,
            "consequence": self.consequence,
        }
