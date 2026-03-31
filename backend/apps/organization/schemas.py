"""
Organization App Schemas
提供组织模块的数据传输对象定义
"""

from __future__ import annotations

from typing import ClassVar

from ninja import ModelSchema, Schema

from apps.core.api.schemas import SchemaMixin

from .models import AccountCredential, LawFirm, Lawyer, Team


class LawFirmOut(ModelSchema):
    class Meta:
        model = LawFirm
        fields: ClassVar[list[str]] = ["id", "name", "address", "phone", "social_credit_code"]


class LawFirmIn(Schema):
    name: str
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None


class LawFirmUpdateIn(Schema):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None


class LawyerOut(ModelSchema, SchemaMixin):
    license_pdf_url: str | None = None
    law_firm_detail: LawFirmOut | None = None

    class Meta:
        model = Lawyer
        fields: ClassVar[list[str]] = [
            "id",
            "username",
            "real_name",
            "phone",
            "license_no",
            "is_admin",
            "is_active",
        ]

    @staticmethod
    def resolve_license_pdf_url(obj: Lawyer) -> str | None:
        return SchemaMixin._get_file_url(obj.license_pdf)

    @staticmethod
    def resolve_law_firm_detail(obj: Lawyer) -> LawFirmOut | None:
        if not obj.law_firm:
            return None
        return LawFirmOut.from_orm(obj.law_firm)


class LawyerCreateIn(Schema):
    username: str
    password: str
    real_name: str | None = None
    phone: str | None = None
    license_no: str | None = None
    id_card: str | None = None
    law_firm_id: int | None = None
    is_admin: bool = False
    lawyer_team_ids: list[int] | None = None
    biz_team_ids: list[int] | None = None


class LawyerUpdateIn(Schema):
    real_name: str | None = None
    phone: str | None = None
    license_no: str | None = None
    id_card: str | None = None
    law_firm_id: int | None = None
    is_admin: bool | None = None
    password: str | None = None
    lawyer_team_ids: list[int] | None = None
    biz_team_ids: list[int] | None = None


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    success: bool
    user: LawyerOut | None = None


class TeamOut(ModelSchema):
    class Meta:
        model = Team
        fields: ClassVar[list[str]] = ["id", "name", "team_type", "law_firm"]


class TeamIn(Schema):
    name: str
    team_type: str
    law_firm_id: int


class AccountCredentialOut(ModelSchema, SchemaMixin):
    class Meta:
        model = AccountCredential
        fields: ClassVar[list[str]] = [
            "id",
            "lawyer",
            "site_name",
            "url",
            "account",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_created_at(obj: AccountCredential) -> str | None:
        return SchemaMixin._resolve_datetime_iso(obj.created_at)

    @staticmethod
    def resolve_updated_at(obj: AccountCredential) -> str | None:
        return SchemaMixin._resolve_datetime_iso(obj.updated_at)


class AccountCredentialIn(Schema):
    lawyer_id: int
    site_name: str
    url: str | None = None
    account: str
    password: str


class AccountCredentialUpdateIn(Schema):
    site_name: str | None = None
    url: str | None = None
    account: str | None = None
    password: str | None = None


# Pydantic v2 + `from __future__ import annotations` 需要 rebuild
AccountCredentialOut.model_rebuild()
LawyerOut.model_rebuild()
LoginIn.model_rebuild()
LoginOut.model_rebuild()
