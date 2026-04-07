"""收件箱 API 端点。"""

from __future__ import annotations

import logging
from typing import Any

from django.http import FileResponse, HttpRequest
from ninja import Query, Router

from apps.core.exceptions import NotFoundError
from apps.message_hub.models import InboxMessage
from apps.message_hub.schemas import InboxMessageDetailOut, InboxMessageOut

logger = logging.getLogger("apps.message_hub")
router = Router()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_base_queryset() -> Any:
    return InboxMessage.objects.select_related("source", "source__credential").order_by("-received_at")


def _get_message_or_404(pk: int) -> InboxMessage:
    try:
        return _get_base_queryset().get(pk=pk)
    except InboxMessage.DoesNotExist:
        raise NotFoundError(f"消息 {pk} 不存在")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/messages", response=list[InboxMessageOut])
def list_messages(
    request: HttpRequest,
    source_id: int | None = None,
    has_attachments: bool | None = None,
    search: str | None = None,
) -> Any:
    """收件箱消息列表。"""
    qs = _get_base_queryset()

    if source_id is not None:
        qs = qs.filter(source_id=source_id)
    if has_attachments is not None:
        qs = qs.filter(has_attachments=has_attachments)
    if search:
        from django.db.models import Q

        qs = qs.filter(Q(subject__icontains=search) | Q(sender__icontains=search) | Q(body_text__icontains=search))

    return qs


@router.get("/messages/{message_id}", response=InboxMessageDetailOut)
def get_message(request: HttpRequest, message_id: int) -> Any:
    """收件箱消息详情。"""
    return _get_message_or_404(message_id)


@router.get("/messages/{message_id}/attachments/{part_index}/download")
def download_attachment(
    request: HttpRequest,
    message_id: int,
    part_index: int,
) -> FileResponse:
    """下载附件。"""
    msg = _get_message_or_404(message_id)
    return _serve_attachment(msg, part_index, inline=False)


@router.get("/messages/{message_id}/attachments/{part_index}/preview")
def preview_attachment(
    request: HttpRequest,
    message_id: int,
    part_index: int,
) -> FileResponse:
    """预览附件（inline）。"""
    msg = _get_message_or_404(message_id)
    return _serve_attachment(msg, part_index, inline=True)


def _resolve_download_filename(msg: InboxMessage, part_index: int, fallback: str) -> str:
    for att in msg.attachments_meta or []:
        if int(att.get("part_index", -1)) != part_index:
            continue
        custom_name = str(att.get("custom_filename", "")).strip()
        if custom_name:
            return custom_name
        original_name = str(att.get("original_filename") or att.get("filename") or "").strip()
        if original_name:
            return original_name
    return fallback


def _serve_attachment(msg: InboxMessage, part_index: int, *, inline: bool) -> FileResponse:
    """通过 fetcher 按需下载并返回附件。"""
    from apps.message_hub.services import get_fetcher

    fetcher = get_fetcher(msg.source.source_type)
    content, filename, content_type = fetcher.download_attachment(
        msg.source,
        msg.message_id,
        part_index,
    )
    download_filename = _resolve_download_filename(msg, part_index, filename)
    disposition = "inline" if inline else "attachment"
    response = FileResponse(
        iter([content]),
        content_type=content_type,
        as_attachment=not inline,
        filename=download_filename,
    )
    response["Content-Disposition"] = f'{disposition}; filename="{download_filename}"'
    return response
