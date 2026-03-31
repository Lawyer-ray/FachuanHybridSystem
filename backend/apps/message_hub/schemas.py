"""收件箱 API Schemas。"""

from __future__ import annotations

from typing import Any

from ninja import Schema

from apps.core.api.schemas import SchemaMixin
from apps.message_hub.models import InboxMessage


class AttachmentMeta(Schema):
    """附件元信息。"""

    filename: str
    size: int
    content_type: str
    part_index: int


class InboxMessageOut(SchemaMixin, Schema):
    """收件箱消息列表项。"""

    id: int
    source_name: str
    source_type: str
    subject: str
    sender: str
    recipient: str
    received_at: str
    has_attachments: bool
    attachment_count: int
    created_at: str

    @staticmethod
    def resolve_source_name(obj: InboxMessage) -> str:
        return obj.source.display_name

    @staticmethod
    def resolve_source_type(obj: InboxMessage) -> str:
        return obj.source.source_type

    @staticmethod
    def resolve_recipient(obj: InboxMessage) -> str:
        return obj.source.credential.account

    @staticmethod
    def resolve_received_at(obj: InboxMessage) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.received_at) or ""

    @staticmethod
    def resolve_attachment_count(obj: InboxMessage) -> int:
        return len(obj.attachments_meta) if obj.attachments_meta else 0

    @staticmethod
    def resolve_created_at(obj: InboxMessage) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.created_at) or ""


class InboxMessageDetailOut(InboxMessageOut):
    """收件箱消息详情（含正文和附件详情）。"""

    body_text: str
    body_html: str
    attachments: list[AttachmentMeta]

    @staticmethod
    def resolve_attachments(obj: InboxMessage) -> list[dict[str, Any]]:
        return obj.attachments_meta or []
