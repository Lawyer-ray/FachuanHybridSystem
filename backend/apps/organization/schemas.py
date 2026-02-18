"""
Organization App Schemas
提供组织模块的数据传输对象定义
"""

from ninja import ModelSchema, Schema

from apps.core.schemas import SchemaMixin

from .models import AccountCredential, LawFirm, Lawyer, Team


class LawFirmOut(ModelSchema):
    """律所输出 Schema"""

    class Meta:
        model = LawFirm
        fields = ["id", "name", "address", "phone", "social_credit_code"]


class LawFirmIn(Schema):
    """律所创建输入 Schema"""

    name: str
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None


class LawFirmUpdateIn(Schema):
    """律所更新输入 Schema"""

    name: str | None = None
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None


class LawyerOut(ModelSchema, SchemaMixin):
    """律师输出 Schema"""

    license_pdf_url: str | None = None
    law_firm_detail: LawFirmOut | None = None

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
    def resolve_license_pdf_url(obj: Lawyer) -> str | None:
        return SchemaMixin._get_file_url(obj.license_pdf)

    @staticmethod
    def resolve_law_firm_detail(obj: Lawyer) -> LawFirmOut | None:
        return obj.law_firm if obj.law_firm else None  # type: ignore[return-value]


class LawyerCreateIn(Schema):
    """律师创建输入 Schema"""

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
    """律师更新输入 Schema"""

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
    """登录输入 Schema"""

    username: str
    password: str


class LoginOut(Schema):
    """登录输出 Schema"""

    success: bool
    user: LawyerOut | None = None


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
    def resolve_created_at(obj: AccountCredential) -> str | None:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "created_at", None))

    @staticmethod
    def resolve_updated_at(obj: AccountCredential) -> str | None:
        return SchemaMixin._resolve_datetime_iso(getattr(obj, "updated_at", None))


class AccountCredentialIn(Schema):
    """账号凭证创建输入 Schema"""

    lawyer_id: int
    site_name: str
    url: str | None = None
    account: str
    password: str


class AccountCredentialUpdateIn(Schema):
    """账号凭证更新输入 Schema"""

    site_name: str | None = None
    url: str | None = None
    account: str | None = None
    password: str | None = None
