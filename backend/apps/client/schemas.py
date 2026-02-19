"""
Client App Schemas
提供客户模块的数据传输对象定义
"""

from datetime import datetime

from typing import ClassVar

from ninja import ModelSchema, Schema

from apps.core.schemas import SchemaMixin

from .models import Client, ClientIdentityDoc


class ClientIdentityDocOut(Schema):
    """客户证件文档输出 Schema"""

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
                media_url=item.media_url(),
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


# ==================== PropertyClue Schemas ====================


class PropertyClueAttachmentOut(Schema):
    """财产线索附件输出 Schema"""

    id: int
    file_path: str
    file_name: str
    uploaded_at: datetime
    media_url: str | None = None


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


class ContentTemplateOut(Schema):
    """内容模板输出 Schema"""

    clue_type: str
    template: str


class IdentityRecognizeOut(Schema):
    """证件识别输出 Schema"""

    success: bool
    doc_type: str
    extracted_data: dict[str, str]
    confidence: float
    error: str | None = None
