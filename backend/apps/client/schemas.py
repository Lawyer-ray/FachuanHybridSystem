"""
Client App Schemas
提供客户模块的数据传输对象定义
"""
from typing import Optional, List
from datetime import datetime
from ninja import Schema, ModelSchema
from .models import Client, ClientIdentityDoc
from apps.core.schemas import SchemaMixin


class ClientIdentityDocOut(Schema):
    """客户证件文档输出 Schema"""
    doc_type: str
    file_path: str
    uploaded_at: datetime
    media_url: Optional[str] = None


class ClientOut(ModelSchema, SchemaMixin):
    """客户输出 Schema"""
    client_type_label: str
    identity_docs: List[ClientIdentityDocOut]

    class Meta:
        model = Client
        fields = [
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
    def resolve_identity_docs(obj: Client) -> List[ClientIdentityDocOut]:
        items: List[ClientIdentityDoc] = list(obj.identity_docs.all())
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
    is_our_client: Optional[bool] = True
    phone: Optional[str] = None
    address: Optional[str] = None
    client_type: str
    id_number: Optional[str] = None
    legal_representative: Optional[str] = None


class ClientUpdateIn(Schema):
    """客户更新输入 Schema"""
    name: Optional[str] = None
    is_our_client: Optional[bool] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    client_type: Optional[str] = None
    id_number: Optional[str] = None
    legal_representative: Optional[str] = None


# ==================== PropertyClue Schemas ====================


class PropertyClueAttachmentOut(Schema):
    """财产线索附件输出 Schema"""
    id: int
    file_path: str
    file_name: str
    uploaded_at: datetime
    media_url: Optional[str] = None


class PropertyClueIn(Schema):
    """财产线索创建输入 Schema"""
    clue_type: str = "bank"
    content: Optional[str] = None


class PropertyClueUpdateIn(Schema):
    """财产线索更新输入 Schema"""
    clue_type: Optional[str] = None
    content: Optional[str] = None


class PropertyClueOut(Schema):
    """财产线索输出 Schema"""
    id: int
    client_id: int
    clue_type: str
    clue_type_label: str
    content: str
    attachments: List[PropertyClueAttachmentOut]
    created_at: datetime
    updated_at: datetime


class ContentTemplateOut(Schema):
    """内容模板输出 Schema"""
    clue_type: str
    template: str
