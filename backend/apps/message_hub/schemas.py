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
    status: str = "todo"
    segs: int = 0
    named: int = 0
    pages: int = 0
    mats: int = 0
    types: list[str] = []
    compose: str = ""

    @staticmethod
    def resolve_status(obj: InboxMessage) -> str:
        ds = obj.draft_state or {}
        status = str(ds.get("status") or "todo")
        return status if status in {"todo", "done", "filed"} else "todo"

    @staticmethod
    def resolve_segs(obj: InboxMessage) -> int:
        return len((obj.draft_state or {}).get("segs") or [])

    @staticmethod
    def resolve_named(obj: InboxMessage) -> int:
        segs = (obj.draft_state or {}).get("segs") or []
        return sum(1 for s in segs if str(s.get("t") or "").strip())

    @staticmethod
    def resolve_pages(obj: InboxMessage) -> int:
        mats = (obj.draft_state or {}).get("mats") or []
        return sum(int(m.get("pages") or 0) for m in mats)

    @staticmethod
    def resolve_mats(obj: InboxMessage) -> int:
        draft_mats = (obj.draft_state or {}).get("mats") or []
        if draft_mats:
            return len(draft_mats)
        return len(obj.attachments_meta or [])

    @staticmethod
    def resolve_types(obj: InboxMessage) -> list[str]:
        segs = (obj.draft_state or {}).get("segs") or []
        seen: list[str] = []
        for s in segs:
            t = str(s.get("t") or "").strip()
            if t and t not in seen:
                seen.append(t)
            if len(seen) >= 3:
                break
        return seen

    @staticmethod
    def _kind_label(content_type: str | None) -> str:
        ct = (content_type or "").lower()
        if ct.startswith("image/"):
            return "图片"
        if "pdf" in ct:
            return "文档"
        # Word/Excel 等统一归到"文档"
        return "文档"

    @staticmethod
    def resolve_compose(obj: InboxMessage) -> str:
        mats = (obj.draft_state or {}).get("mats") or []
        if not mats:
            group: dict[str, int] = {}
            for att in obj.attachments_meta or []:
                label = InboxMessageOut._kind_label(att.get("content_type"))
                group[label] = group.get(label, 0) + 1
            return "、".join(f"{n} 个{v}" for v, n in group.items()) if group else ""
        group: dict[str, int] = {}
        for m in mats:
            k = str(m.get("k") or "office")
            label = "图片" if k == "photo" else "文档"
            group[label] = group.get(label, 0) + 1
        bits = [f"{n} 个{v}" for v, n in group.items()]
        return " · ".join(bits) if bits else "尚未拆分"

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
