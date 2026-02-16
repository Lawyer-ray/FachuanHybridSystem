"""API schemas and serializers."""

from __future__ import annotations

"""
Contract Schemas - Supplementary Agreement

补充协议相关的 Schema 定义.
"""

from typing import Any, ClassVar, cast

from ninja import ModelSchema, Schema

from apps.contracts.models import PartyRole, SupplementaryAgreement, SupplementaryAgreementParty
from apps.core.schemas import SchemaMixin

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
        """解析客户名称"""
        return cast(str, obj.client.name) if obj.client else ""

    @staticmethod
    def resolve_is_our_client(obj: Any) -> bool:
        """解析是否为我方客户"""
        return cast(bool, obj.client.is_our_client) if obj.client else False

    @staticmethod
    def resolve_role_label(obj: Any) -> str:
        """解析身份标签"""
        return cast(str, cast(Any, obj).get_role_display()) if obj.role else ""


class SupplementaryAgreementOut(ModelSchema, SchemaMixin):
    """补充协议输出 Schema"""

    parties: list[SupplementaryAgreementPartyOut]

    class Meta:
        model = SupplementaryAgreement
        fields: ClassVar = ["id", "contract", "name", "created_at", "updated_at"]

    @staticmethod
    def resolve_parties(obj: Any) -> list[SupplementaryAgreementPartyOut]:
        """解析当事人列表"""
        parties = cast(Any, obj).parties
        return list(parties.select_related("client").all())

    @staticmethod
    def resolve_created_at(obj: Any) -> str:
        """解析创建时间为 ISO 格式"""
        return cast(str, SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None)))

    @staticmethod
    def resolve_updated_at(obj: Any) -> str:
        """解析更新时间为 ISO 格式"""
        return cast(str, SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None)))
