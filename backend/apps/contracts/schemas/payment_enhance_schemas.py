"""收款记账增强 Schemas：到账短信识别草稿 / 发票上传结果。"""

from __future__ import annotations

from ninja import Schema

__all__: list[str] = [
    "ContractPaymentParseIn",
    "ContractPaymentParseOut",
    "InvoiceOut",
    "InvoiceUploadOut",
    "InvoiceUploadFailure",
]


class ContractPaymentParseIn(Schema):
    """粘贴的到账短信 / 转账截图文字。"""

    text: str


class ContractPaymentParseOut(Schema):
    """解析草稿。**识别不出的字段一律为空**，前端展示「未识别，请手填」。"""

    amount: str | None = None
    #: ISO 日期（yyyy-mm-dd）；None = 没识别出来
    received_at: str | None = None
    payer: str = ""
    note: str = ""
    #: 识别依据（如「金额 9,000.00」「付款人 伍振川」），前端原样展示
    hints: list[str] = []


class InvoiceOut(Schema):
    """一张发票（收款详情展示 + 上传后返回）。"""

    id: int
    payment_id: int
    original_filename: str
    #: 归一化展示名（日期_销售方_金额），与合同文件夹里的文件名一致
    display_filename: str
    #: media 相对路径（前端换下载票据后预览/下载）
    file_url: str
    invoice_code: str = ""
    invoice_number: str = ""
    invoice_date: str | None = None
    amount: str | None = None
    tax_amount: str | None = None
    total_amount: str | None = None
    seller_name: str = ""
    buyer_name: str = ""
    uploaded_at: str = ""


class InvoiceUploadFailure(Schema):
    filename: str
    reason: str


class InvoiceUploadOut(Schema):
    """批量上传结果：成功的逐张返回，失败的逐张说明原因（一张坏文件不拖垮整批）。"""

    saved: list[InvoiceOut] = []
    failed: list[InvoiceUploadFailure] = []
    #: 落库后该收款的最新开票状态与金额（前端据此就地刷新收款行，不必重拉整个合同）
    invoice_status: str = ""
    invoice_status_label: str = ""
    invoiced_amount: str = ""
    #: 有发票被判定为重复（同号已存在）：前端提示「这张可能已经录过了」
    duplicated_count: int = 0
