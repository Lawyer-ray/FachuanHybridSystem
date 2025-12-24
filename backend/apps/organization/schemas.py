"""
Organization App Schemas
提供组织模块的数据传输对象定义
"""
from typing import Optional, List
from ninja import Schema, ModelSchema
from .models import Lawyer, LawFirm, Team, TeamType, AccountCredential
from apps.core.schemas import SchemaMixin


class LawFirmOut(ModelSchema):
    """律所输出 Schema"""
    class Meta:
        model = LawFirm
        fields = ["id", "name", "address", "phone", "social_credit_code"]


class LawFirmIn(Schema):
    """律所创建输入 Schema"""
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    social_credit_code: Optional[str] = None


class LawFirmUpdateIn(Schema):
    """律所更新输入 Schema"""
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    social_credit_code: Optional[str] = None


class LawyerOut(ModelSchema, SchemaMixin):
    """律师输出 Schema"""
    license_pdf_url: Optional[str] = None
    law_firm_detail: Optional[LawFirmOut] = None

    class Meta:
        model = Lawyer
        fields = [
            "id",
            "username",
            "real_name",
            "phone",
            "license_no",
            "id_card",
            "law_firm",
            "is_admin",
            "is_active",
        ]

    @staticmethod
    def resolve_license_pdf_url(obj: Lawyer) -> Optional[str]:
        return SchemaMixin._get_file_url(obj.license_pdf)

    @staticmethod
    def resolve_law_firm_detail(obj: Lawyer) -> Optional[LawFirmOut]:
        return obj.law_firm if obj.law_firm else None


class LawyerCreateIn(Schema):
    """律师创建输入 Schema"""
    username: str
    password: str
    real_name: Optional[str] = None
    phone: Optional[str] = None
    license_no: Optional[str] = None
    id_card: Optional[str] = None
    law_firm_id: Optional[int] = None
    is_admin: bool = False
    lawyer_team_ids: Optional[List[int]] = None
    biz_team_ids: Optional[List[int]] = None


class LawyerUpdateIn(Schema):
    """律师更新输入 Schema"""
    real_name: Optional[str] = None
    phone: Optional[str] = None
    license_no: Optional[str] = None
    id_card: Optional[str] = None
    law_firm_id: Optional[int] = None
    is_admin: Optional[bool] = None
    password: Optional[str] = None
    lawyer_team_ids: Optional[List[int]] = None
    biz_team_ids: Optional[List[int]] = None


class LoginIn(Schema):
    """登录输入 Schema"""
    username: str
    password: str


class LoginOut(Schema):
    """登录输出 Schema"""
    success: bool
    user: Optional[LawyerOut] = None


class TeamOut(ModelSchema):
    """团队输出 Schema"""
    class Meta:
        model = Team
        fields = ["id", "name", "team_type", "law_firm"]


class TeamIn(Schema):
    """团队创建输入 Schema"""
    name: str
    team_type: str
    law_firm_id: int


class AccountCredentialOut(ModelSchema, SchemaMixin):
    """账号凭证输出 Schema"""
    class Meta:
        model = AccountCredential
        fields = [
            "id",
            "lawyer",
            "site_name",
            "url",
            "account",
            "password",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def resolve_created_at(obj: AccountCredential):
        return SchemaMixin._resolve_datetime(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: AccountCredential):
        return SchemaMixin._resolve_datetime(getattr(obj, "updated_at", None))


class AccountCredentialIn(Schema):
    """账号凭证创建输入 Schema"""
    lawyer_id: int
    site_name: str
    url: Optional[str] = None
    account: str
    password: str


class AccountCredentialUpdateIn(Schema):
    """账号凭证更新输入 Schema"""
    site_name: Optional[str] = None
    url: Optional[str] = None
    account: Optional[str] = None
    password: Optional[str] = None
