"""收件箱 API Schemas。"""

from __future__ import annotations

from typing import Any, cast

from ninja import Schema

from apps.core.api.schemas import SchemaMixin
from apps.message_hub.models import InboxMessage


class AttachmentMeta(Schema):
    """附件元信息。"""

    filename: str
    original_filename: str | None = None
    custom_filename: str | None = None
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
    uploaded_by_id: int | None
    uploaded_by_name: str
    created_at: str

    @staticmethod
    def resolve_source_name(obj: InboxMessage) -> str:
        return str(obj.source.display_name)

    @staticmethod
    def resolve_source_type(obj: InboxMessage) -> str:
        return str(obj.source.source_type)

    @staticmethod
    def resolve_recipient(obj: InboxMessage) -> str:
        account: str = obj.source.credential.account if obj.source.credential else ""
        return account

    @staticmethod
    def resolve_uploaded_by_id(obj: InboxMessage) -> int | None:
        return obj.uploaded_by_id if obj.uploaded_by_id else None

    @staticmethod
    def resolve_uploaded_by_name(obj: InboxMessage) -> str:
        if not obj.uploaded_by:
            return ""
        return str(obj.uploaded_by.real_name or obj.uploaded_by.username or "")

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
    draft_state: dict = {}

    @staticmethod
    def resolve_attachments(obj: InboxMessage) -> list[dict[str, Any]]:
        return obj.get_public_attachments_meta()

    @staticmethod
    def resolve_draft_state(obj: InboxMessage) -> dict[str, Any]:
        return obj.draft_state or {}
