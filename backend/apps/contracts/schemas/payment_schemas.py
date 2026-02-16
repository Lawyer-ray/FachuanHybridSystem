"""
Contract Schemas - Payment

支付和财务相关的 Schema 定义.
"""

from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from apps.contracts.models import ContractPayment, InvoiceStatus
from apps.core.schemas import SchemaMixin


class ContractPaymentIn(Schema):
    contract_id: int
    amount: float
    received_at: str | None = None
    invoice_status: str | None = InvoiceStatus.UNINVOICED
    invoiced_amount: float | None = 0
    note: str | None = None
    confirm: bool = False


class ContractPaymentOut(ModelSchema, SchemaMixin):
    invoice_status_label: str

    class Meta:
        model = ContractPayment
        fields: ClassVar = [
            "id",
            "contract",
            "amount",
            "received_at",
            "invoice_status",
            "invoiced_amount",
            "note",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_invoice_status_label(obj: ContractPayment) -> str:
        return SchemaMixin._get_display(obj, "invoice_status") or ""

    @staticmethod
    def resolve_created_at(obj: ContractPayment) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: ContractPayment) -> Any:
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))


class ContractPaymentUpdate(Schema):
    amount: float | None = None
    received_at: str | None = None
    invoice_status: str | None = None
    invoiced_amount: float | None = None
    note: str | None = None
    confirm: bool = False


class FinanceStatsItem(Schema):
    contract_id: int
    total_received: float
    total_invoiced: float
    unpaid_amount: float | None


class FinanceStatsOut(Schema):
    items: list[FinanceStatsItem]
    total_received_all: float
    total_invoiced_all: float
