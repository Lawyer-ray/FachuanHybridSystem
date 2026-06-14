"""Client export serialization helpers shared by admin modules."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# prefetch 路径：调用方在遍历前应对此元组调用 queryset.prefetch_related()
# ---------------------------------------------------------------------------
CLIENT_EXPORT_PREFETCHES: tuple[str, ...] = (
    "identity_docs",
    "property_clues__attachments",
)


class ClientExportSerializerService:
    """Service facade for client export serialization."""

    def serialize_client_obj(self, obj: Any) -> dict[str, Any]:
        return serialize_client_obj(obj)


# 便捷别名：外部模块可直接 from ... import CLIENT_EXPORT_PREFETCHES
__all__ = ["CLIENT_EXPORT_PREFETCHES", "ClientExportSerializerService", "serialize_client_obj"]


def serialize_client_obj(obj: Any) -> dict[str, Any]:  # pragma: no cover
    """Serialize a Client-like object for export."""
    return {
        "name": obj.name,
        "client_type": obj.client_type,
        "id_number": obj.id_number,
        "phone": obj.phone,
        "address": getattr(obj, "address", None),
        "legal_representative": obj.legal_representative,
        "legal_representative_id_number": getattr(obj, "legal_representative_id_number", None),
        "is_our_client": obj.is_our_client,
        "identity_docs": [
            {"doc_type": doc.doc_type, "file_path": doc.file_path} for doc in obj.identity_docs.all() if doc.file_path
        ],
        "property_clues": [
            {
                "clue_type": clue.clue_type,
                "content": clue.content,
                "attachments": [
                    {"file_path": att.file_path, "file_name": att.file_name}
                    for att in clue.attachments.all()
                    if att.file_path
                ],
            }
            for clue in obj.property_clues.all()
        ],
    }
