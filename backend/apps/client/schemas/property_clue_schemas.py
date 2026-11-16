"""财产线索 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Schema


class PropertyClueAttachmentOut(Schema):
    """财产线索附件输出 Schema"""

    id: int
    file_path: str | None = None
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
            return obj.get_clue_type_display()  # type: ignore[no-any-return]
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
