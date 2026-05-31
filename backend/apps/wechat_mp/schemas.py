"""公众号发布 API Schema"""

from __future__ import annotations

from typing import Any

from ninja import Schema

class WeChatAccountOut(Schema):
    id: int
    name: str
    mp_url: str
    is_active: bool
    created_at: Any

class PublishTaskCreate(Schema):
    title: str
    content_md: str
    account_id: int
    save_as_draft: bool = True
    format_method: str = "rule"

class PublishTaskOut(Schema):
    id: int
    account_id: int
    title: str
    status: str
    save_as_draft: bool
    format_method: str
    result_data: dict
    error_message: str
    created_at: Any
    started_at: Any | None
    finished_at: Any | None
