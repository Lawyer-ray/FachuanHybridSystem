"""
Contract Schemas - Supplementary Agreement

补充协议相关的 Schema 定义.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from apps.contracts.models import PartyRole, SupplementaryAgreement, SupplementaryAgreementParty
from apps.core.api.schemas import SchemaMixin

from .client_schemas import ClientOut


class SupplementaryAgreementPartyInput(Schema):
    """补充协议当事人输入(用于嵌套)"""

    client_id: int
    role: str = "PRINCIPAL"


class SupplementaryAgreementInput(Schema):
    """补充协议输入(用于嵌套在合同创建/更新中)"""

    name: str | None = None
    party_ids: list[int] | None = None  # 兼容旧接口
    parties: list[SupplementaryAgreementPartyInput] | None = None  # 新接口(含身份)


class SupplementaryAgreementIn(Schema):
    """补充协议创建输入 Schema"""

    contract_id: int
    name: str | None = None
    party_ids: list[int] | None = None  # 兼容旧接口
    parties: list[SupplementaryAgreementPartyInput] | None = None  # 新接口(含身份)


class SupplementaryAgreementUpdate(Schema):
    """补充协议更新输入 Schema"""

    name: str | None = None
    party_ids: list[int] | None = None  # 兼容旧接口
    parties: list[SupplementaryAgreementPartyInput] | None = None  # 新接口(含身份)


class SupplementaryAgreementPartyIn(Schema):
    """补充协议当事人输入"""

    client_id: int
    role: str = PartyRole.PRINCIPAL


class SupplementaryAgreementPartyOut(ModelSchema):
    """补充协议当事人输出 Schema"""

    client_detail: ClientOut
    client_name: str
    is_our_client: bool
    role_label: str

    class Meta:
        model = SupplementaryAgreementParty
        fields: ClassVar = ["id", "client", "role"]

    @staticmethod
    def resolve_client_detail(obj: Any) -> ClientOut | None:
        """解析完整的客户信息"""
        return ClientOut.from_model(obj.client) if obj.client else None

    @staticmethod
    def resolve_client_name(obj: Any) -> str:
        return obj.client.name if obj.client else ""

    @staticmethod
    def resolve_is_our_client(obj: Any) -> bool:
        return bool(obj.client.is_our_client) if obj.client else False

    @staticmethod
    def resolve_role_label(obj: Any) -> str:
        return obj.get_role_display() if obj.role else ""  # type: ignore[no-any-return, attr-defined]


class SupplementaryAgreementOut(ModelSchema, SchemaMixin):
    """补充协议输出 Schema"""

    parties: list[SupplementaryAgreementPartyOut]

    class Meta:
        model = SupplementaryAgreement
        fields: ClassVar = ["id", "contract", "name", "created_at", "updated_at"]

    @staticmethod
    def resolve_parties(obj: Any) -> list[SupplementaryAgreementPartyOut]:
        parties = obj.parties  # type: ignore[attr-defined]
        return list(parties.select_related("client").all())

    @staticmethod
    def resolve_created_at(obj: Any) -> str:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))  # type: ignore[return-value]

    @staticmethod
    def resolve_updated_at(obj: Any) -> str:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None))  # type: ignore[return-value]
