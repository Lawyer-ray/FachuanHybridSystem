"""消息来源 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from apps.core.tasking import submit_task
from apps.message_hub.models import MessageSource, SyncStatus

router = Router()

# ── Schemas ──────────────────────────────────────────────


class MessageSourceOut(Schema):
    id: int
    display_name: str
    source_type: str
    credential_account: str
    is_enabled: bool
    poll_interval_minutes: int
    sync_since: str | None
    imap_host: str
    imap_account: str
    sender_whitelist: str
    sender_blacklist: str
    last_sync_at: str | None
    last_sync_status: str
    last_sync_error: str
    created_at: str

    @staticmethod
    def resolve_credential_account(obj: MessageSource) -> str:
        return obj.credential.account if obj.credential else ""

    @staticmethod
    def resolve_sync_since(obj: MessageSource) -> str | None:
        return obj.sync_since.isoformat() if obj.sync_since else None

    @staticmethod
    def resolve_last_sync_at(obj: MessageSource) -> str | None:
        return obj.last_sync_at.isoformat() if obj.last_sync_at else None

    @staticmethod
    def resolve_last_sync_status(obj: MessageSource) -> str:
        return obj.last_sync_status or SyncStatus.PENDING

    @staticmethod
    def resolve_created_at(obj: MessageSource) -> str:
        return obj.created_at.isoformat() if obj.created_at else ""


class MessageSourceCreateIn(Schema):
    display_name: str
    source_type: str = "imap"
    credential_id: int
    is_enabled: bool = True
    poll_interval_minutes: int = 30
    sync_since: datetime | None = None
    imap_host: str = ""
    imap_account: str = ""
    sender_whitelist: str = ""
    sender_blacklist: str = ""


class MessageSourceUpdateIn(Schema):
    display_name: str | None = None
    is_enabled: bool | None = None
    poll_interval_minutes: int | None = None
    sync_since: datetime | None = None
    imap_host: str | None = None
    imap_account: str | None = None
    sender_whitelist: str | None = None
    sender_blacklist: str | None = None


# ── Endpoints ────────────────────────────────────────────


@router.get("/sources", response=list[MessageSourceOut])
def list_sources(request: Any) -> list[MessageSource]:  # pragma: no cover
    from ..services.inbox_query import list_sources as _list_sources

    return _list_sources()


@router.get("/sources/{source_id}", response=MessageSourceOut)
def get_source(request: Any, source_id: int) -> MessageSource:  # pragma: no cover
    from ..services.inbox_query import get_source_or_none

    source = get_source_or_none(source_id)
    if source is None:
        from django.http import Http404

        raise Http404("消息来源不存在")
    return source


@router.post("/sources", response={201: MessageSourceOut})
def create_source(request: Any, payload: MessageSourceCreateIn) -> tuple[int, MessageSource]:  # pragma: no cover
    from apps.organization.models import AccountCredential

    credential = get_object_or_404(AccountCredential, pk=payload.credential_id)
    kwargs: dict[str, Any] = {
        "display_name": payload.display_name,
        "source_type": payload.source_type,
        "credential": credential,
        "is_enabled": payload.is_enabled,
        "poll_interval_minutes": payload.poll_interval_minutes,
        "imap_host": payload.imap_host,
        "imap_account": payload.imap_account,
        "sender_whitelist": payload.sender_whitelist,
        "sender_blacklist": payload.sender_blacklist,
    }
    if payload.sync_since is not None:
        kwargs["sync_since"] = payload.sync_since

    from ..services.inbox_query import create_source

    source = create_source(**kwargs)
    return 201, source


@router.put("/sources/{source_id}", response=MessageSourceOut)
def update_source(request: Any, source_id: int, payload: MessageSourceUpdateIn) -> MessageSource:  # pragma: no cover
    source = get_object_or_404(MessageSource, pk=source_id)
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(source, field, value)
    source.save()
    return source


@router.delete("/sources/{source_id}", response={204: None})
def delete_source(request: Any, source_id: int) -> tuple[int, None]:  # pragma: no cover
    source = get_object_or_404(MessageSource, pk=source_id)
    source.delete()
    return 204, None


@router.post("/sources/{source_id}/sync")
def sync_source(request: Any, source_id: int) -> dict[str, Any]:  # pragma: no cover
    get_object_or_404(MessageSource, pk=source_id)
    submit_task("apps.message_hub.tasks.sync_source_by_id", source_id)
    return {"success": True, "message": "同步任务已提交"}


@router.post("/sources/sync-all")
def sync_all_sources(request: Any) -> dict[str, Any]:  # pragma: no cover
    from ..services.inbox_query import get_enabled_sources

    sources = get_enabled_sources()
    for source in sources:
        submit_task("apps.message_hub.tasks.sync_source_by_id", source.pk)
    return {"success": True, "message": f"已提交 {sources.count()} 个同步任务"}
