"""收件箱 API 端点。"""

from __future__ import annotations

import io
import logging
from typing import Any

from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpRequest
from ninja import Form, Query, Router, Schema

from apps.core.exceptions import NotFoundError
from apps.message_hub.models import InboxMessage
from apps.message_hub.schemas import InboxMessageDetailOut, InboxMessageOut

logger = logging.getLogger("apps.message_hub")
router = Router()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_base_queryset() -> Any:
    from apps.message_hub.services.inbox_query import get_base_queryset

    return get_base_queryset()


def _get_message_or_404(pk: int) -> InboxMessage:
    from apps.message_hub.services.inbox_query import get_message_or_none

    msg = get_message_or_none(pk)
    if msg is None:
        raise NotFoundError(f"消息 {pk} 不存在")
    return msg


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/messages", response=list[InboxMessageOut])
def list_messages(  # pragma: no cover
    request: HttpRequest,
    source_id: int | None = None,
    source_type: str | None = None,
    has_attachments: bool | None = None,
    search: str | None = None,
) -> Any:
    """收件箱消息列表。"""
    qs = _get_base_queryset()

    if source_id is not None:
        qs = qs.filter(source_id=source_id)
    if source_type is not None:
        qs = qs.filter(source__source_type=source_type)
    if has_attachments is not None:
        qs = qs.filter(has_attachments=has_attachments)
    if search:
        from django.db.models import Q

        qs = qs.filter(Q(subject__icontains=search) | Q(sender__icontains=search) | Q(body_text__icontains=search))

    return qs


class DraftIn(Schema):
    draft: dict = {}


@router.post("/messages/upload", response={201: InboxMessageDetailOut})
def upload_messages(  # pragma: no cover
    request: HttpRequest,
    subject: str = Form(""),
) -> tuple[int, InboxMessage]:
    """前端材料预处理上传：多文件（multipart 每次一个 files 字段）收进收件箱。"""
    from apps.message_hub.services.manual_upload_service import create_manual_message

    files = request.FILES.getlist("files")
    if not files:
        from django.core.exceptions import ValidationError

        raise ValidationError("没有收到文件")
    uploader = request.user if request.user and request.user.is_authenticated else None
    msg = create_manual_message(list(files), subject, uploaded_by=uploader)
    return 201, msg


@router.put("/messages/{message_id}/draft")
def update_draft(request: HttpRequest, message_id: int, payload: DraftIn) -> dict[str, Any]:
    """保存某条收件箱消息的拆分草稿。"""
    from apps.message_hub.services.manual_upload_service import save_draft

    msg = _get_message_or_404(message_id)
    save_draft(msg.pk, payload.draft)
    return {"ok": True, "message_id": msg.pk}


@router.get("/messages/{message_id}", response=InboxMessageDetailOut)
def get_message(request: HttpRequest, message_id: int) -> Any:  # pragma: no cover
    """收件箱消息详情。"""
    return _get_message_or_404(message_id)


@router.delete("/messages/{message_id}")
def delete_message(request: HttpRequest, message_id: int) -> dict[str, Any]:  # pragma: no cover
    """删除收件箱消息（材料包）：先清理附件物理文件，再删 DB 记录（破坏性，前端需二次确认）。"""
    from apps.message_hub.services.manual_upload_service import delete_manual_message

    msg = _get_message_or_404(message_id)
    delete_manual_message(msg)
    return {"ok": True, "message_id": message_id}


@router.get("/messages/{message_id}/attachments/{part_index}/download")
def download_attachment(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    part_index: int,
) -> FileResponse:
    """下载附件。"""
    msg = _get_message_or_404(message_id)
    return _serve_attachment(msg, part_index, inline=False)


@router.get("/messages/{message_id}/attachments/{part_index}/preview")
def preview_attachment(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    part_index: int,
) -> FileResponse:
    """预览附件（inline）。"""
    msg = _get_message_or_404(message_id)
    return _serve_attachment(msg, part_index, inline=True)


@router.post("/messages/{message_id}/attachments", response={201: InboxMessageDetailOut})
def append_attachments(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    subject: str = Form(""),
) -> tuple[int, InboxMessage]:
    """往现有材料包追加附件（multipart 每次一个 files 字段），返回更新后的详情。"""
    from apps.message_hub.services.manual_upload_service import append_manual_attachments

    files = request.FILES.getlist("files")
    if not files:
        raise ValidationError("没有收到文件")
    msg = _get_message_or_404(message_id)
    append_manual_attachments(msg, files)
    return 201, _get_message_or_404(msg.pk)


class OcrBlockOut(Schema):
    x: float
    y: float
    w: float
    h: float
    text: str = ""
    score: float = 0.0


class OcrResultOut(Schema):
    width: int
    height: int
    blocks: list[OcrBlockOut] = []


@router.post("/ocr", response=OcrResultOut)
def ocr_recognize(request: HttpRequest) -> OcrResultOut:  # pragma: no cover
    """前端框选取字：接收一张页面图片，RapidOCR 识别后返回归一化文字块坐标。"""
    up = request.FILES.get("file")
    if not up:
        raise ValidationError("没有收到图片")
    data = up.read()

    width = height = 0
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        width, height = img.size
    except Exception:
        width = height = 0

    try:
        from apps.core.interfaces import ServiceLocator

        service = ServiceLocator.get_ocr_service()
        result = service.recognize_raw(data)
    except Exception as e:
        logger.warning("RapidOCR 识别失败，返回空结果: %s", e)
        result = None

    return OcrResultOut(width=width, height=height, blocks=_normalize_ocr_blocks(result, width, height))


def _normalize_ocr_blocks(result: Any, width: int, height: int) -> list[OcrBlockOut]:
    """把 RapidOCR 原始结果（4 角点像素框）归一化成 0-1 相对坐标矩形。"""
    if result is None or getattr(result, "boxes", None) is None:
        return []
    if width <= 0 or height <= 0:
        return []
    try:
        boxes = result.boxes.tolist()
    except Exception:
        boxes = getattr(result, "boxes", None)
    if not boxes:
        return []
    txts = getattr(result, "txts", None) or []
    scores = getattr(result, "scores", None)
    out: list[OcrBlockOut] = []
    for i, box in enumerate(boxes):
        try:
            pts = [[float(p[0]), float(p[1])] for p in box]
        except Exception:
            continue
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        score = 0.0
        if scores is not None and i < len(scores):
            try:
                score = float(scores[i])
            except Exception:
                score = 0.0
        text = str(txts[i]) if i < len(txts) else ""
        out.append(
            OcrBlockOut(
                x=round(min(xs) / width, 4) if width else 0,
                y=round(min(ys) / height, 4) if height else 0,
                w=round((max(xs) - min(xs)) / width, 4) if width else 0,
                h=round((max(ys) - min(ys)) / height, 4) if height else 0,
                text=text.strip(),
                score=score,
            )
        )
    return out


class RenameAttachmentIn(Schema):
    custom_filename: str = ""


@router.post("/messages/{message_id}/attachments/{part_index}/rename")
def rename_attachment(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    part_index: int,
    payload: RenameAttachmentIn,
) -> dict[str, Any]:
    """重命名附件。留空 custom_filename 则恢复原始文件名。"""
    msg = _get_message_or_404(message_id)
    meta = list(msg.attachments_meta or [])
    target = None
    for att in meta:
        if int(att.get("part_index", -1)) == part_index:
            target = att
            break
    if target is None:
        raise NotFoundError(f"附件 part_index={part_index} 不存在")

    original = target.get("original_filename") or target.get("filename") or ""
    custom = payload.custom_filename.strip()

    if custom and custom != original:
        target["custom_filename"] = custom
    else:
        target.pop("custom_filename", None)
        custom = ""

    msg.attachments_meta = meta
    msg.save(update_fields=["attachments_meta"])

    effective = custom if custom else original
    return {
        "ok": True,
        "original_filename": original,
        "custom_filename": custom,
        "effective_filename": effective,
    }


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
