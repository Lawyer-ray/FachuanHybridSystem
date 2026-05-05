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
    last_sync_at: str | None
    last_sync_status: str
    created_at: str

    @staticmethod
    def resolve_credential_account(obj: MessageSource) -> str:
        return obj.credential.account if obj.credential else ""

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


class MessageSourceUpdateIn(Schema):
    display_name: str | None = None
    is_enabled: bool | None = None
    poll_interval_minutes: int | None = None
    sender_whitelist: str | None = None
    sender_blacklist: str | None = None


# ── Endpoints ────────────────────────────────────────────

@router.get("/sources", response=list[MessageSourceOut])
def list_sources(request: Any) -> list[MessageSource]:
    return list(MessageSource.objects.select_related("credential").all())


@router.get("/sources/{source_id}", response=MessageSourceOut)
def get_source(request: Any, source_id: int) -> MessageSource:
    return get_object_or_404(MessageSource.objects.select_related("credential"), pk=source_id)


@router.post("/sources", response={201: MessageSourceOut})
def create_source(request: Any, payload: MessageSourceCreateIn) -> tuple[int, MessageSource]:
    from apps.organization.models import AccountCredential

    credential = get_object_or_404(AccountCredential, pk=payload.credential_id)
    source = MessageSource.objects.create(
        display_name=payload.display_name,
        source_type=payload.source_type,
        credential=credential,
        is_enabled=payload.is_enabled,
        poll_interval_minutes=payload.poll_interval_minutes,
    )
    return 201, source


@router.put("/sources/{source_id}", response=MessageSourceOut)
def update_source(request: Any, source_id: int, payload: MessageSourceUpdateIn) -> MessageSource:
    source = get_object_or_404(MessageSource, pk=source_id)
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(source, field, value)
    source.save()
    return source


@router.delete("/sources/{source_id}", response={204: None})
def delete_source(request: Any, source_id: int) -> tuple[int, None]:
    source = get_object_or_404(MessageSource, pk=source_id)
    source.delete()
    return 204, None


@router.post("/sources/{source_id}/sync")
def sync_source(request: Any, source_id: int) -> dict[str, Any]:
    get_object_or_404(MessageSource, pk=source_id)
    submit_task("apps.message_hub.tasks.sync_source_by_id", source_id)
    return {"success": True, "message": "同步任务已提交"}


@router.post("/sources/sync-all")
def sync_all_sources(request: Any) -> dict[str, Any]:
    sources = MessageSource.objects.filter(is_enabled=True)
    for source in sources:
        submit_task("apps.message_hub.tasks.sync_source_by_id", source.pk)
    return {"success": True, "message": f"已提交 {sources.count()} 个同步任务"}
