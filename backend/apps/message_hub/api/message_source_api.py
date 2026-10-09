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
    """消息来源列表（安全审计 IDOR：仅本人凭证的来源 + superuser/admin 全部）。"""
    from apps.message_hub.services.inbox_access import visible_sources_qs

    return list(visible_sources_qs(_request_user(request)))


@router.get("/sources/{source_id}", response=MessageSourceOut)
def get_source(request: Any, source_id: int) -> MessageSource:  # pragma: no cover
    from django.http import Http404

    from apps.message_hub.services.inbox_access import can_view_source
    from apps.message_hub.services.inbox_query import get_source_or_none

    source = get_source_or_none(source_id)
    if source is None:
        raise Http404("消息来源不存在")
    if not can_view_source(_request_user(request), source):
        raise Http404("消息来源不存在")
    return source


def _request_user(request: Any) -> Any:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        user = getattr(request, "auth", None)
    return user


def _ensure_credential_usable(request: Any, credential: Any) -> None:
    """安全审计 B-28：IMAP 来源只能绑定请求用户本人（或 superuser）的凭证。

    否则任意律师可用他人凭证 + 自建 imap_host 把他人邮箱密码发往任意服务器。
    """
    user = _request_user(request)
    if user is None:
        from apps.core.exceptions import PermissionDenied

        raise PermissionDenied(message="请先登录", code="PERMISSION_DENIED")
    if getattr(user, "is_superuser", False):
        return
    if getattr(credential, "lawyer_id", None) != getattr(user, "id", None):
        from apps.core.exceptions import PermissionDenied

        raise PermissionDenied(message="只能使用本人的账号凭证", code="PERMISSION_DENIED")


def _ensure_source_manageable(request: Any, source: Any) -> None:
    """安全审计 B-28（复审补全）：来源的改/删/同步仅限凭证属主或 superuser。

    否则任意用户可改他人来源的 imap_host 后触发 sync，将其邮箱凭证发往任意主机。
    """
    credential = getattr(source, "credential", None)
    if credential is not None:
        _ensure_credential_usable(request, credential)
        return
    # 无凭证来源（如手动上传）：superuser 或管理员可管理
    # 2026Q4 审计收紧：is_staff 仅是 Django admin 准入标志，不再视为系统管理员
    user = _request_user(request)
    if user is not None and (getattr(user, "is_superuser", False) or getattr(user, "is_admin", False)):
        return
    from apps.core.exceptions import PermissionDenied

    raise PermissionDenied(message="无权管理该消息来源", code="PERMISSION_DENIED")


@router.post("/sources", response={201: MessageSourceOut})
def create_source(request: Any, payload: MessageSourceCreateIn) -> tuple[int, MessageSource]:  # pragma: no cover
    from apps.organization.models import AccountCredential

    credential = get_object_or_404(AccountCredential, pk=payload.credential_id)
    _ensure_credential_usable(request, credential)
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

    from apps.message_hub.services.inbox_query import create_source

    source = create_source(**kwargs)
    return 201, source


@router.put("/sources/{source_id}", response=MessageSourceOut)
def update_source(request: Any, source_id: int, payload: MessageSourceUpdateIn) -> MessageSource:  # pragma: no cover
    source = get_object_or_404(MessageSource, pk=source_id)
    # 安全审计 B-28（复审补全）：改 imap_host 等于重定向凭证投递目标，须属主管理
    _ensure_source_manageable(request, source)
    updatable_fields = MessageSourceUpdateIn.model_fields.keys()
    for field, value in payload.dict(exclude_unset=True).items():
        if field in updatable_fields:
            setattr(source, field, value)
    source.save()
    return source


@router.delete("/sources/{source_id}", response={204: None})
def delete_source(request: Any, source_id: int) -> tuple[int, None]:  # pragma: no cover
    source = get_object_or_404(MessageSource, pk=source_id)
    _ensure_source_manageable(request, source)
    source.delete()
    return 204, None


@router.post("/sources/{source_id}/sync")
def sync_source(request: Any, source_id: int) -> dict[str, Any]:  # pragma: no cover
    source = get_object_or_404(MessageSource, pk=source_id)
    _ensure_source_manageable(request, source)
    submit_task("apps.message_hub.tasks.sync_source_by_id", source_id)
    return {"success": True, "message": "同步任务已提交"}


@router.post("/sources/sync-all")
def sync_all_sources(request: Any) -> dict[str, Any]:
    """同步全部来源（安全审计 IDOR：只提交当前用户可见来源的同步任务）。"""
    from apps.message_hub.services.inbox_access import visible_sources_qs

    sources = list(visible_sources_qs(_request_user(request)).filter(is_enabled=True))
    for source in sources:
        submit_task("apps.message_hub.tasks.sync_source_by_id", source.pk)
    return {"success": True, "message": f"已提交 {len(sources)} 个同步任务"}
