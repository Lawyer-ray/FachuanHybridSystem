"""发票模型。"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from .contract import Contract
from .payment import ContractPayment


class Invoice(models.Model):
    """发票文件。

    挂靠二选一：`payment`（已核销到某笔收款）或 `contract`（**先开票后付款**——
    票先到手、钱还没到，挂在合同名下等待日后关联收款）。两条 FK 都可空，
    由 CheckConstraint 保证恰好一条有值；关联收款时 `payment` 置值、`contract`
    清空，media 文件不搬动（`file_path` 只是存储位置，展示名另算）。
    """

    id: int
    payment_id: int | None
    contract_id: int | None
    payment = models.ForeignKey(
        ContractPayment,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name="收款记录",
        null=True,
        blank=True,
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name="合同（未关联收款时挂靠）",
        null=True,
        blank=True,
    )
    file_path = models.CharField(max_length=500, verbose_name="文件路径")
    original_filename = models.CharField(max_length=255, verbose_name="原始文件名")
    remark = models.TextField(blank=True, default="", verbose_name="备注")
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="内容哈希",
        help_text="SHA-256, 用于去重",
        db_index=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    # 发票识别结果字段（可选）
    invoice_code = models.CharField(max_length=20, blank=True, default="", verbose_name="发票代码")
    invoice_number = models.CharField(max_length=20, blank=True, default="", verbose_name="发票号码")
    invoice_date = models.DateField(null=True, blank=True, verbose_name="开票日期")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="金额",
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="税额",
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="价税合计",
    )
    #: 销售/购买方名（识别回填）：重命名（发票（销售方）_日期开具.pdf）与列表展示用
    seller_name = models.CharField(max_length=120, blank=True, default="", verbose_name="销售方名称")
    buyer_name = models.CharField(max_length=120, blank=True, default="", verbose_name="购买方名称")

    class Meta:
        ordering: ClassVar = ["-uploaded_at"]
        verbose_name = "发票"
        verbose_name_plural = "发票"
        indexes: ClassVar = [
            models.Index(fields=["payment", "-uploaded_at"]),
            models.Index(fields=["contract", "-uploaded_at"]),
        ]
        constraints: ClassVar = [
            # 导入路径 get_or_create(payment, file_path) 的查重键
            models.UniqueConstraint(fields=["payment", "file_path"], name="uniq_invoice_payment_file_path"),
            # 挂靠恰好一条：收款或合同（先开票后付款时挂合同，关联收款后只挂收款）
            models.CheckConstraint(
                condition=models.Q(payment__isnull=False, contract__isnull=True)
                | models.Q(payment__isnull=True, contract__isnull=False),
                name="chk_invoice_payment_xor_contract",
            ),
        ]

    def __str__(self) -> str:
        return self.original_filename or f"发票 #{self.id}"
