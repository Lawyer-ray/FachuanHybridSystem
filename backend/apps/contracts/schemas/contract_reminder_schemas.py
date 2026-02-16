"""
Contract Schemas - Contract Reminder

合同提醒相关的 Schema 定义.
"""

from typing import ClassVar

from ninja import ModelSchema, Schema

from apps.contracts.models import ContractReminder
from apps.core.schemas import SchemaMixin


class ContractReminderIn(Schema):
    contract_id: int
    kind: str
    content: str
    due_date: str


class ContractReminderUpdate(Schema):
    contract_id: int | None = None
    kind: str | None = None
    content: str | None = None
    due_date: str | None = None


class ContractReminderOut(ModelSchema, SchemaMixin):
    created_at: str | None

    class Meta:
        model = ContractReminder
        fields: ClassVar = [
            "id",
            "contract",
            "kind",
            "content",
            "due_date",
            "created_at",
        ]

    @staticmethod
    def resolve_created_at(obj: ContractReminder) -> str | None:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))
