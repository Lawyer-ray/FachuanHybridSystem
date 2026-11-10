"""InvoiceIntake —— 发票待认领。

## 为什么需要这张表

客户发来的发票邮件只有附件，发票号码/开票日期/价税合计/购买方只能靠识别抽取。
抽取结果必须先变成"一张待认领的发票"，再经**人工确认**才能落 ``Invoice``：
识别结果天然不可靠（重复票、错票、发错收件人），且一张发票到底归哪个项目、
平哪笔收款，只有经办人知道。

与 ``PaymentIntake``（``apps/contracts/models/payment_intake.py``）同构：
一封邮件 → 一条 intake，``dedupe_key`` 保证重复扫描幂等；系统只给
``suggested_contract`` / ``suggested_payment`` 建议，人工确认后才写
``confirmed_contract`` / ``confirmed_payment`` 并生成 ``invoice``。

设计参考：``docs/harness/backend/payment-intake-design.md``（同构）。
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class InvoiceIntakeStatus(models.TextChoices):
    """待认领发票状态。

    ``PENDING`` 等待人工裁定；``CONFIRMED`` 已绑定项目/收款并生成 ``Invoice``；
    ``REJECTED`` 是无关发票（不是本所项目该收的票，如员工报销票、他人票）。
    """

    PENDING = "pending", "待确认"
    CONFIRMED = "confirmed", "已绑定"
    REJECTED = "rejected", "无关发票"


class InvoiceIntake(models.Model):
    id: int
    inbox_message_id: int

    inbox_message = models.ForeignKey(
        "message_hub.InboxMessage",
        # PROTECT：删消息不得静默抹掉待认领/已确认的发票来源
        on_delete=models.PROTECT,
        related_name="invoice_intakes",
        verbose_name="来源邮件",
    )
    # 同一封邮件的多个附件用序号区分（一封邮件可能带多张票）
    part_index = models.PositiveIntegerField(default=0, verbose_name="附件序号")
    # 幂等键：同一封邮件同一附件重复扫描不产生第二条
    dedupe_key = models.CharField(max_length=128, unique=True, verbose_name="去重键")

    # 附件落点：相对 media 根的路径，不存绝对路径（换机/换盘后仍可解析）
    attachment_path = models.CharField(max_length=500, blank=True, default="", verbose_name="附件相对路径")
    original_filename = models.CharField(max_length=255, blank=True, default="", verbose_name="原始文件名")

    # 发票识别结果（可能为空：识别失败，此时靠人工看附件）
    invoice_number = models.CharField(max_length=32, blank=True, default="", db_index=True, verbose_name="发票号码")
    invoice_date = models.DateField(null=True, blank=True, verbose_name="开票日期")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name="价税合计")
    buyer_name = models.CharField(max_length=120, blank=True, default="", verbose_name="购买方名称")
    # 备注栏原文：律所项目号通常写在这里，是人眼复核与项目号抽取的唯一依据，不可加工
    remark = models.TextField(blank=True, default="", verbose_name="备注栏原文")
    project_code = models.CharField(max_length=32, blank=True, default="", db_index=True, verbose_name="律所项目号")

    status = models.CharField(
        max_length=16,
        choices=InvoiceIntakeStatus.choices,
        default=InvoiceIntakeStatus.PENDING,
        db_index=True,
        verbose_name="状态",
    )

    # 系统建议（可为空：没有合格候选）。只是建议，不写财务数据
    suggested_contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_invoice_intakes",
        verbose_name="系统建议项目",
    )
    suggested_payment = models.ForeignKey(
        "contracts.ContractPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggested_invoice_intakes",
        verbose_name="系统建议收款",
    )
    # 候选列表 + 分数 + 理由 + 被排除线索的快照。不可变，便于事后追责与调参
    match_snapshot = models.JSONField(default=dict, blank=True, verbose_name="匹配快照")

    # 人工裁定结果。confirmed_contract 允许与 suggested_contract 不同（人可改判）
    confirmed_contract = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_invoice_intakes",
        verbose_name="确认项目",
    )
    confirmed_payment = models.ForeignKey(
        "contracts.ContractPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_invoice_intakes",
        verbose_name="确认收款",
    )
    confirmed_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_invoice_intakes",
        verbose_name="确认人",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    # 确认后生成的发票记录。撤销确认时据此找回并清理副本
    invoice = models.ForeignKey(
        "contracts.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intake",
        verbose_name="生成的发票记录",
    )
    decision_note = models.TextField(blank=True, default="", verbose_name="人工备注")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "待认领发票"
        verbose_name_plural = "待认领发票"
        ordering: ClassVar = ["-created_at", "-id"]
        indexes: ClassVar = [
            # 首页/后台按状态取待办，再按创建时间倒序
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_number or '无号码'} {self.buyer_name or '-'} ({self.status})"
