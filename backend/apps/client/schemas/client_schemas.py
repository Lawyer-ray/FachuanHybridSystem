"""客户主体 Schema。"""

from __future__ import annotations

from typing import Any, ClassVar

from ninja import ModelSchema, Schema

from apps.core.api.schemas import SchemaMixin

from ..models import Client, ClientIdentityDoc
from .identity_doc_schemas import ClientIdentityDocOut


class PartyListOut(Schema):
    """当事人检索精简输出（仅供检索填报，不携带证件文档，规避证件序列化缺陷）"""

    id: int
    name: str
    phone: str | None = None
    is_our_client: bool = False


class ClientOut(ModelSchema, SchemaMixin):
    """客户输出 Schema

    证件号原样出参（2026-10 产品决策：本机部署、律师办案需要完整证件号填文书，
    此前安全审计加的「前 3 后 4」打码已撤除）。
    """

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
            "legal_representative_id_number",
        ]

    @staticmethod
    def resolve_client_type_label(obj: Client) -> str:
        return SchemaMixin._get_display(obj, "client_type") or ""

    @staticmethod
    def resolve_identity_docs(obj: Any) -> list[ClientIdentityDocOut]:
        # When called via DjangoGetter on a dict (model_validate re-validation)
        if isinstance(obj, dict):
            docs = obj.get("identity_docs", [])
            if docs and isinstance(docs[0], dict):
                return [ClientIdentityDocOut(**d) for d in docs]
            return docs  # type: ignore[no-any-return]  # already ClientIdentityDocOut instances
        items: list[ClientIdentityDoc] = list(obj.identity_docs.all())
        return [
            ClientIdentityDocOut(
                id=item.id,
                doc_type=item.doc_type,
                file_path=item.file_path,
                uploaded_at=item.uploaded_at,
                media_url=item.media_url,
            )
            for item in items
        ]


class OACredentialCheckOut(Schema):
    """检查 OA 凭证结果"""

    has_credential: bool


class ClientIn(Schema):
    """客户创建输入 Schema"""

    name: str
    is_our_client: bool | None = True
    # 这些列已归一为 NOT NULL（空字符串语义），默认 '' 而非 None
    phone: str | None = ""
    address: str | None = ""
    client_type: str
    # id_number 是 unique 列：未填写保持 None（PG 多 NULL 共存）
    id_number: str | None = None
    legal_representative: str | None = ""
    legal_representative_id_number: str | None = ""


class ClientUpdateIn(Schema):
    """客户更新输入 Schema"""

    name: str | None = None
    is_our_client: bool | None = None
    phone: str | None = None
    address: str | None = None
    client_type: str | None = None
    id_number: str | None = None
    legal_representative: str | None = None
    legal_representative_id_number: str | None = None


class ParseTextIn(Schema):
    """当事人文本解析请求体"""

    text: str
    parse_multiple: bool = False


class IdCardValidateIn(Schema):
    """身份证号校验请求体"""

    id_number: str


class IdCardValidateOut(Schema):
    """身份证号校验结果"""

    valid: bool
    message: str
