"""PaymentIntake —— 到账待认领款项。

## 为什么需要这张表

银行/客户的到账通知邮件必须先变成"一笔待记账的钱"，再经**人工确认**才能落
``ContractPayment``。中间这一层是必要的，因为真实到账邮件的最强信号只有付款人
姓名 + 银行备注（几乎不含案号），无法可靠自动判定归属：

- ``#533`` 李某 2400 元是 160 号合同委托人本人存入的尾款；
- ``#547`` 张某 10000 元代付，对应项目已收清 50000 且全额开票，需**另签合同**。

机器负责"解析 + 排序 + 排除 + 解释"，人负责"认定"。设计文档见
``docs/harness/backend/payment-intake-design.md``。

## 与 InboxMessage 的关系

一封到账邮件 → 一条 intake（一期）。``dedupe_key`` 保证重复扫描幂等。
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils import timezone


class IntakeStatus(models.TextChoices):
    """待认领款项状态。

    与设计文档 §3.2 的状态机一一对应，新增状态必须同步那里的图。
    """

    PENDING = "pending", "待确认"
    # 系统找不到合格在办项目（或明确需要新建合同）。#547 即此类：
    # 对应的项目已收清，客户额外多付，业务上要另签合同来收这笔钱。
    AWAITING_CONTRACT = "awaiting_contract", "待建合同"
    CONFIRMED = "confirmed", "已确认"
    REJECTED = "rejected", "非记账事件"
    IGNORED = "ignored", "不需记账"


class PaymentIntake(models.Model):
    id: int
    inbox_message_id: int
    source_type: str

    inbox_message = models.ForeignKey(
        "message_hub.InboxMessage",
        # PROTECT：删消息不得静默抹掉待认领/已确认的财务凭证来源
        on_delete=models.PROTECT,
        related_name="payment_intakes",
        verbose_name="来源邮件",
    )
    # 幂等键：同一封邮件重复扫描不产生第二条。见设计文档 §3.4
    dedupe_key = models.CharField(max_length=128, unique=True, verbose_name="去重键")

    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="到账金额")
    received_at = models.DateField(default=timezone.localdate, verbose_name="到账日期")
    # 付款人：银行备注里的自然人/公司。可能为空（解析不出），此时靠人工看原文
    payer_name = models.CharField(max_length=128, blank=True, default="", verbose_name="付款人")
    # 「代 XXX 付」里的 XXX；空 = 本人付。代付关系是判定归属的重要线索
    on_behalf_of = models.CharField(max_length=255, blank=True, default="", verbose_name="代付方")
    # 银行备注原文。必须原样保存：这是人眼复核的唯一依据，不可加工
    bank_remark = models.TextField(blank=True, default="", verbose_name="银行备注原文")

    # 系统建议（可为空：没有合格候选）。只是建议，不写财务数据
    suggested_contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_intakes",
        verbose_name="系统建议项目",
    )
    # 候选列表 + 分数 + 理由 + 被排除线索的快照。不可变，便于事后追责与调参
    match_snapshot = models.JSONField(default=dict, blank=True, verbose_name="匹配快照")

    status = models.CharField(
        max_length=24, choices=IntakeStatus.choices, default=IntakeStatus.PENDING, verbose_name="状态"
    )

    # 人工裁定结果。confirmed_contract 允许与 suggested_contract 不同（人可改判）
    confirmed_contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_intakes",
        verbose_name="确认归属项目",
    )
    confirmed_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_payment_intakes",
        verbose_name="确认人",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    # 确认后创建的收款记录。撤销确认时要连同它一起删除
    payment = models.ForeignKey(
        "contracts.ContractPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_intakes",
        verbose_name="生成的收款记录",
    )
    decision_note = models.TextField(blank=True, default="", verbose_name="人工备注")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "到账待认领"
        verbose_name_plural = "到账待认领"
        ordering: ClassVar = ["-received_at", "-id"]
        indexes: ClassVar = [
            # 首页模块按状态 + 到账日倒序取待办
            models.Index(fields=["status", "-received_at"]),
            models.Index(fields=["status", "received_at"]),
        ]
        constraints: ClassVar = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="chk_paymentintake_amount_pos"),
            # 已确认必须有归属项目和确认人；其余状态不得有 payment
            models.CheckConstraint(
                condition=(
                    models.Q(status="confirmed", payment__isnull=False, confirmed_contract__isnull=False)
                    | ~models.Q(status="confirmed")
                ),
                name="chk_paymentintake_confirmed_has_payment",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.payer_name or '-'} ({self.status})"

    @property
    def is_open(self) -> bool:
        """是否处于待处理态（首页模块据此统计角标）。"""
        return self.status in (IntakeStatus.PENDING, IntakeStatus.AWAITING_CONTRACT)

    @property
    def display_payer(self) -> str:
        """付款人展示串：「张某（代深圳市某供应链公司…）」/「李某」/「未知付款人」。"""
        payer = self.payer_name or "未知付款人"
        if self.on_behalf_of:
            return f"{payer}（代{self.on_behalf_of}）"
        return payer

    def top_candidates(self, limit: int = 3) -> list[dict[str, Any]]:
        """快照里的前 N 个候选（首页窄栏只放得下前几个）。"""
        snapshot = self.match_snapshot or {}
        candidates = snapshot.get("candidates")
        if not isinstance(candidates, list):
            return []
        return [c for c in candidates[:limit] if isinstance(c, dict)]

    def excluded_hints(self) -> list[dict[str, Any]]:
        """被排除但值得让人知道的线索（已收满/已结案的历史项目）。

        设计文档 §3.5：既满足「收满不匹配」规则，又不丢失线索。
        """
        snapshot = self.match_snapshot or {}
        hints = snapshot.get("excluded_hints")
        if not isinstance(hints, list):
            return []
        return [h for h in hints if isinstance(h, dict)]
