"""API schemas and serializers."""

from __future__ import annotations

"""
Contract Schemas - Party

合同当事人相关的 Schema 定义.
"""

from typing import Any, ClassVar, cast

from ninja import ModelSchema, Schema

from apps.contracts.models import ContractParty, PartyRole

from .client_schemas import ClientOut


class ContractPartyIn(Schema):
    """合同当事人输入"""

    client_id: int
    role: str = PartyRole.PRINCIPAL


class ContractPartyOut(ModelSchema):
    client_detail: ClientOut
    role_label: str

    class Meta:
        model = ContractParty
        fields: ClassVar = ["id", "contract", "client", "role"]

    @staticmethod
    def resolve_client_detail(obj: ContractParty) -> ClientOut:
        return ClientOut.from_model(obj.client)

    @staticmethod
    def resolve_role_label(obj: ContractParty) -> str:
        return cast(str, cast(Any, obj).get_role_display()) if obj.role else ""


class ContractPartySourceOut(Schema):
    """合同当事人(含来源)输出 Schema

    用于 API 端点 /contracts/{contract_id}/all-parties/
    返回合同及其补充协议的所有当事人

    Requirements: 5.2, 5.4
    """

    id: int  # Client ID
    name: str  # Client 名称
    source: str  # 来源: "contract" | "supplementary"
    role: str | None = None  # 当事人角色: "PRINCIPAL" | "BENEFICIARY" | "OPPOSING"
