"""
Client App Schemas
提供客户模块的数据传输对象定义
"""

from datetime import datetime
from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from apps.core.schemas import SchemaMixin

from .models import Client, ClientIdentityDoc


class ClientIdentityDocOut(Schema):
    """客户证件文档输出 Schema"""

    doc_type: str
    file_path: str
    uploaded_at: datetime
    media_url: str | None = None


class IdentityDocDetailOut(Schema):
    """证件文档详情输出 Schema"""

    id: int
    client_id: int
    doc_type: str
    file_path: str
    uploaded_at: datetime
    media_url: str | None = None


class ClientOut(ModelSchema, SchemaMixin):
    """客户输出 Schema"""

    client_type_label: str
    identity_docs: list[ClientIdentityDocOut]

    class Meta:
        model = Client
        fields: ClassVar[list[str]] = [
            "id",
            "name",
            "is_our_client",
            "phone",
            "address",
            "client_type",
            "id_number",
            "legal_representative",
        ]

    @staticmethod
    def resolve_client_type_label(obj: Client) -> str:
        return SchemaMixin._get_display(obj, "client_type") or ""

    @staticmethod
    def resolve_identity_docs(obj: Client) -> list[ClientIdentityDocOut]:
        items: list[ClientIdentityDoc] = list(obj.identity_docs.all())
        return [
            ClientIdentityDocOut(
                doc_type=item.doc_type,
                file_path=item.file_path,
                uploaded_at=item.uploaded_at,
                media_url=item.media_url,
            )
            for item in items
        ]


class ClientIn(Schema):
    """客户创建输入 Schema"""

    name: str
    is_our_client: bool | None = True
    phone: str | None = None
    address: str | None = None
    client_type: str
    id_number: str | None = None
    legal_representative: str | None = None


class ClientUpdateIn(Schema):
    """客户更新输入 Schema"""

    name: str | None = None
    is_our_client: bool | None = None
    phone: str | None = None
    address: str | None = None
    client_type: str | None = None
    id_number: str | None = None
    legal_representative: str | None = None


# ==================== Enterprise Prefill Schemas ====================


class EnterpriseCompanyCandidateOut(Schema):
    """企业搜索候选项。"""

    company_id: str
    company_name: str
    legal_person: str = ""
    status: str = ""
    establish_date: str = ""
    registered_capital: str = ""
    phone: str = ""


class EnterpriseCompanySearchOut(Schema):
    """企业搜索结果。"""

    keyword: str
    provider: str
    items: list[EnterpriseCompanyCandidateOut]
    total: int


class EnterpriseDuplicateClientOut(Schema):
    """已存在的当事人信息。"""

    id: int
    name: str


class EnterpriseClientPrefillDataOut(Schema):
    """企业信息映射后的当事人预填字段。"""

    client_type: str
    name: str
    id_number: str = ""
    legal_representative: str = ""
    address: str = ""
    phone: str = ""


class EnterpriseCompanyProfileOut(Schema):
    """企业基础档案。"""

    company_id: str
    company_name: str = ""
    unified_social_credit_code: str = ""
    legal_person: str = ""
    status: str = ""
    establish_date: str = ""
    registered_capital: str = ""
    address: str = ""
    business_scope: str = ""
    phone: str = ""


class EnterpriseClientPrefillOut(Schema):
    """企业信息预填结果。"""

    provider: str
    prefill: EnterpriseClientPrefillDataOut
    profile: EnterpriseCompanyProfileOut
    existing_client: EnterpriseDuplicateClientOut | None = None


# ==================== PropertyClue Schemas ====================


class PropertyClueAttachmentOut(Schema):
    """财产线索附件输出 Schema"""

    id: int
    file_path: str
    file_name: str
    uploaded_at: datetime
    media_url: str | None = None

    @staticmethod
    def resolve_media_url(obj: Any) -> str | None:
        return obj.media_url if hasattr(obj, "media_url") else None


class PropertyClueIn(Schema):
    """财产线索创建输入 Schema"""

    clue_type: str = "bank"
    content: str | None = None


class PropertyClueUpdateIn(Schema):
    """财产线索更新输入 Schema"""

    clue_type: str | None = None
    content: str | None = None


class PropertyClueOut(Schema):
    """财产线索输出 Schema"""

    id: int
    client_id: int
    clue_type: str
    clue_type_label: str
    content: str
    attachments: list[PropertyClueAttachmentOut]
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_clue_type_label(obj: Any) -> str:
        if hasattr(obj, "get_clue_type_display"):
            return obj.get_clue_type_display()
        return str(getattr(obj, "clue_type", ""))

    @staticmethod
    def resolve_attachments(obj: Any) -> list[PropertyClueAttachmentOut]:
        if not hasattr(obj, "attachments"):
            return []
        return [
            PropertyClueAttachmentOut(
                id=item.id,
                file_path=item.file_path,
                file_name=item.file_name,
                uploaded_at=item.uploaded_at,
                media_url=item.media_url,
            )
            for item in obj.attachments.all()
        ]


class ContentTemplateOut(Schema):
    """内容模板输出 Schema"""

    clue_type: str
    template: str


class IdentityRecognizeOut(Schema):
    """证件识别输出 Schema"""

    success: bool
    doc_type: str
    extracted_data: dict[str, str | None]
    confidence: float
    error: str | None = None
