"""收件箱 API 端点。"""

from __future__ import annotations

import io
import logging
from typing import Any

from django.db import transaction
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from ninja import Form, Query, Router, Schema

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.http.download import content_disposition
from apps.message_hub.models import InboxMessage
from apps.message_hub.schemas import (
    ContractMatchOut,
    InboxMessageDetailOut,
    InboxMessageOut,
    InboxMessageSlimOut,
    MessageAckOut,
    MessageRenameOut,
    SubmitToSmsOut,
)
from apps.message_hub.services.inbox_access import can_view_message

logger = logging.getLogger("apps.message_hub")
router = Router()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_base_queryset(request: HttpRequest) -> Any:
    """按当前用户收敛的收件箱消息 QuerySet（安全审计 IDOR：见 inbox_access）。"""
    from apps.message_hub.services.inbox_access import visible_messages_qs

    return visible_messages_qs(request.user)


def _get_message_or_404(request: HttpRequest, pk: int) -> InboxMessage:
    """按 ID 取消息并校验归属；不存在或无权访问均返回 404（不泄露存在性）。"""
    from apps.message_hub.services.inbox_query import get_message_or_none

    msg = get_message_or_none(pk)
    if msg is None:
        raise NotFoundError(f"消息 {pk} 不存在")
    if not can_view_message(request.user, msg):
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
    unread_only: bool = False,
    search: str | None = None,
    limit: int = 500,
    offset: int = 0,
    slim: bool = False,
) -> Any:
    """收件箱消息列表（limit 截取前 N 条；收件箱持续增长，服务端兜底默认 500，
    需要更大结果集的消费方显式传 limit——不传即全量的旧行为会让「打开收件箱」
    随表增长恶化为全站最重请求，每行还要跑 7 个 draft_state resolver）。

    安全审计（2026Q4 M-6）：``limit<=0`` 时原先不做切片 → 全表序列化
    （含 N+1 的 draft_state resolver），用户上传大量材料包后可自我放大为 DoS。
    此处把 limit 收敛到 [1, 1000]。offset（默认 0）供 MCP 信封续取。

    ``slim=true``：按 ``InboxMessageSlimOut`` 只回行级摘要（剔除收件箱行不
    消费的 15 个字段，实测全量 492 行 481.1 KB → 325.3 KB，-32.4%）。响应体仍是裸数组，
    不带 ``slim`` 时**逐字节不变**（仍由 ``response=list[InboxMessageOut]``
    序列化整个 QuerySet）。正文本来就不在本接口：详情正文走 ``GET /messages/{id}``。
    """
    limit = max(1, min(limit, 1000))
    bounded_offset = max(0, offset)
    qs = _get_base_queryset(request)

    if source_id is not None:
        qs = qs.filter(source_id=source_id)
    if source_type is not None:
        # 逗号分隔多值（如 "manual_upload,client_upload"）：材料预处理桌面
        # 同时收律师手动包与客户链接包；单值用法完全兼容
        types = [s.strip() for s in source_type.split(",") if s.strip()]
        qs = qs.filter(source__source_type__in=types)
    if has_attachments is not None:
        qs = qs.filter(has_attachments=has_attachments)
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    if search:
        from django.db.models import Q

        qs = qs.filter(Q(subject__icontains=search) | Q(sender__icontains=search) | Q(body_text__icontains=search))

    if limit > 0:
        qs = qs[bounded_offset : bounded_offset + limit]

    if slim:
        # 走 JsonResponse 而不是改 response schema：声明式的 response 是编译期固定
        # 的，而「是否紧凑」是请求期参数；用 Union 会让默认路径也过一遍 pydantic
        # 联合判定，默认响应就有被选成窄形状的风险（红线：不带 slim 逐字节不变）。
        return JsonResponse(
            [InboxMessageSlimOut.from_orm(obj).model_dump() for obj in qs],
            safe=False,
            # 与站点渲染器 UTF8JSONRenderer（apiSystem/apiSystem/api.py:41）同参：
            # 中文不转义。不写这两项就会回退到 Django 默认的 \uXXXX 转义，
            # 中文字段反而比默认路径胖两成。
            json_dumps_params={"ensure_ascii": False, "default": str},
        )

    return qs


class DraftIn(Schema):
    draft: dict = {}


class RenameMessageIn(Schema):
    subject: str = ""


@router.post("/messages/upload", response={201: InboxMessageDetailOut})
def upload_messages(  # pragma: no cover
    request: HttpRequest,
    subject: str = Form(""),
) -> tuple[int, InboxMessage]:
    """前端材料预处理上传：多文件（multipart 每次一个 files 字段）收进收件箱。"""
    from apps.message_hub.services.manual_upload_service import create_manual_message

    files = request.FILES.getlist("files")
    # S42-02（2026-11-23 二轮审计）：原实现抛 django.core.exceptions.ValidationError，
    # 全局处理器只注册了项目自有 ValidationException → 落到兜底 handler 变成
    # 500「系统错误」。现在改用 ValidationException（4xx + 可按 code 区分）。
    if not files:
        raise ValidationException("没有收到文件", code="INBOX_NO_FILES")
    uploader = request.user if request.user and request.user.is_authenticated else None
    msg = create_manual_message(list(files), subject, uploaded_by=uploader)
    return 201, msg


@router.put("/messages/{message_id}/draft")
def update_draft(request: HttpRequest, message_id: int, payload: DraftIn) -> dict[str, Any]:
    """保存某条收件箱消息的拆分草稿。"""
    from apps.message_hub.services.manual_upload_service import save_draft

    msg = _get_message_or_404(request, message_id)
    save_draft(msg.pk, payload.draft)
    return {"ok": True, "message_id": msg.pk}


@router.put("/messages/{message_id}", response=MessageRenameOut)
def rename_message(request: HttpRequest, message_id: int, payload: RenameMessageIn) -> dict[str, Any]:
    """重命名材料包标题（收件箱消息 subject）。"""
    from apps.message_hub.services.manual_upload_service import rename_manual_message

    msg = _get_message_or_404(request, message_id)
    updated = rename_manual_message(msg, payload.subject)
    return {"ok": True, "message_id": updated.pk, "subject": updated.subject}


@router.get("/messages/{message_id}", response=InboxMessageDetailOut)
def get_message(request: HttpRequest, message_id: int) -> Any:  # pragma: no cover
    """收件箱消息详情。老消息缺 PDF 页数时顺手回填（前端秒开材料包依赖 page_count）。"""
    msg = _get_message_or_404(request, message_id)
    from apps.message_hub.services.attachment_page_service import ensure_page_counts

    ensure_page_counts(msg)
    return msg


@router.delete("/messages/{message_id}", response=MessageAckOut)
def delete_message(request: HttpRequest, message_id: int) -> dict[str, Any]:
    """删除收件箱消息（材料包）：硬删 DB 记录并清理附件物理文件（破坏性，前端需二次确认）。

    被财务凭证（待认领收款 / 待认领发票）引用的消息会抛 ConflictError → 409，
    且此时一个附件都不会被删（服务层先校验、后动文件）。
    """
    from apps.message_hub.services.manual_upload_service import delete_manual_message

    msg = _get_message_or_404(request, message_id)
    delete_manual_message(msg)
    return {"ok": True, "message_id": message_id}


# ---------------------------------------------------------------------------
# 已读态 / 转材料包（收件箱页）
# ---------------------------------------------------------------------------


class ReadStateIn(Schema):
    read: bool = True


class ReadStateOut(MessageAckOut):
    is_read: bool = False
    read_at: str | None = None


@router.post("/messages/{message_id}/read", response=ReadStateOut)
def set_read_state(request: HttpRequest, message_id: int, payload: ReadStateIn) -> dict[str, Any]:
    """标记已读 / 未读。幂等：重复置已读不刷新首次阅读时间。"""
    from django.utils import timezone

    from apps.core.api.schemas import SchemaMixin

    msg = _get_message_or_404(request, message_id)
    if payload.read and msg.read_at is None:
        msg.read_at = timezone.now()
        msg.save(update_fields=["read_at"])
    elif not payload.read and msg.read_at is not None:
        msg.read_at = None
        msg.save(update_fields=["read_at"])
    return {
        "ok": True,
        "message_id": msg.pk,
        "is_read": msg.read_at is not None,
        "read_at": SchemaMixin._resolve_datetime_iso(msg.read_at) if msg.read_at else None,
    }


class ConvertOut(Schema):
    ok: bool
    message_id: int
    """生成的（或已存在的）材料包消息 id，前端据此直接跳 /material-prep/:id"""
    pack_id: int


@router.post("/messages/{message_id}/convert", response=ConvertOut)
def convert_message(request: HttpRequest, message_id: int) -> dict[str, Any]:
    """把外部来源消息（一张网 / IMAP / 短信）的附件转成一个材料包。

    幂等：同一消息已有 converted_message 时直接返回那个包（不重复搬运字节）。
    """
    from apps.message_hub.services.inbox_convert_service import convert_to_material_pack

    msg = _get_message_or_404(request, message_id)
    pack = convert_to_material_pack(msg, uploaded_by=request.user)
    return {"ok": True, "message_id": msg.pk, "pack_id": pack.pk}


@router.post("/messages/{message_id}/submit-to-sms", response=SubmitToSmsOut)
def submit_message_to_sms(request: HttpRequest, message_id: int) -> dict[str, Any]:
    """把一张网 / 庭审日程 / IMAP 消息提交到法院短信处理流程。

    附件字节会被**复制**一份到 automation 上传目录（不引用原 local_path）——
    短信链路的 ``DocumentRenamer`` 原地改名，引用会把收件箱附件弄丢。
    幂等：命中既有短信记录时返回该记录且 ``created=False``。
    """
    from apps.message_hub.services.inbox_sms_bridge import InboxSmsBridgeService

    msg = _get_message_or_404(request, message_id)
    result = InboxSmsBridgeService().submit(msg)
    return {
        "success": True,
        "sms_id": result.sms.pk,
        "created": result.created,
        "attachment_count": result.attachment_count,
        "skipped": result.skipped,
    }


@router.get("/messages/{message_id}/attachments/{part_index}/download")
def download_attachment(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    part_index: int,
) -> FileResponse:
    """下载附件。"""
    msg = _get_message_or_404(request, message_id)
    return _serve_attachment(msg, part_index, inline=False)


@router.get("/messages/{message_id}/attachments/{part_index}/preview")
def preview_attachment(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    part_index: int,
) -> FileResponse:
    """预览附件（inline）。"""
    msg = _get_message_or_404(request, message_id)
    return _serve_attachment(msg, part_index, inline=True)


@router.get("/messages/{message_id}/attachments/{part_index}/thumbnail")
def attachment_thumbnail(
    request: HttpRequest,
    message_id: int,
    part_index: int,
    page: int = 1,
    width: int = 320,
) -> Any:
    """附件缩略图（PDF 第 ``page`` 页 / 位图本身），JPEG。

    收件箱列表用它在行内给一张「小样」：**服务端渲染**，不让前端为了一张小图去
    下载整份扫描件（一本 40 页 26MB，见 ``attachment_thumbnail_service`` 的模块
    文档）。列表接口不随行预取，只在用户展开附件条 / 点预览时请求。

    缓存协议：首次生成后落盘，之后恒从磁盘读；响应带 ETag（= 缓存键），浏览器
    复访带 ``If-None-Match`` 时直接 304，连字节都不发。
    """
    msg = _get_message_or_404(request, message_id)
    from apps.message_hub.services.attachment_thumbnail_service import build_attachment_thumbnail

    path, etag = build_attachment_thumbnail(msg, part_index=part_index, page=page, width=width)
    quoted = f'"{etag}"'
    if request.headers.get("If-None-Match") == quoted:
        not_modified = HttpResponse(status=304)
        not_modified["ETag"] = quoted
        return not_modified

    response = FileResponse(path.open("rb"), content_type="image/jpeg")
    response["ETag"] = quoted
    # private：缩略图就是办案材料的内容，只允许进用户自己的浏览器缓存，不进共享缓存
    # 一天而不是一周：URL 不含内容指纹，附件万一被同名替换，最坏也就旧一天
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/messages/{message_id}/attachments", response={201: InboxMessageDetailOut})
def append_attachments(  # pragma: no cover
    request: HttpRequest,
    message_id: int,
    subject: str = Form(""),
) -> tuple[int, InboxMessage]:
    """往现有材料包追加附件（multipart 每次一个 files 字段），返回更新后的详情。"""
    from apps.message_hub.services.manual_upload_service import append_manual_attachments

    files = request.FILES.getlist("files")
    # S42-02（2026-11-23 二轮审计）：同 upload_messages，Django ValidationError →
    # 项目自有 ValidationException（否则 500 而非 4xx）。
    if not files:
        raise ValidationException("没有收到文件", code="INBOX_NO_FILES")
    msg = _get_message_or_404(request, message_id)
    append_manual_attachments(msg, files)
    return 201, _get_message_or_404(request, msg.pk)


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
    # S42-02（2026-11-23 二轮审计）：同前两处，Django ValidationError → ValidationException。
    if not up:
        raise ValidationException("没有收到图片", code="INBOX_NO_IMAGE")
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
            # 单个 OCR 框坐标畸形只跳过该框（OCR 输出常有不规则结构），
            # 留 debug 便于发现上游格式变化。
            logger.debug("OCR 框坐标解析失败，跳过 index=%s", i, exc_info=True)
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
    from apps.message_hub.services.attachment_page_service import rename_attachment_in_meta

    msg = _get_message_or_404(request, message_id)
    # 行锁与 meta 读-改-写下沉 service 层（API 层禁 ORM，四层架构棘轮口径）
    original, custom = rename_attachment_in_meta(msg, part_index=part_index, custom_filename=payload.custom_filename)

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


# 允许 inline 预览的 Content-Type 白名单：邮件自报的 text/html 等可执行类型
# 若按 inline 返回会在同源执行脚本（存储型 XSS），一律强制改为附件下载
_INLINE_SAFE_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)


def _build_content_disposition(disposition: str, filename: str) -> str:
    """构造转义后的 Content-Disposition（RFC 5987）。

    解耦（2026-10-19）：委托 ``core/http/download`` 的统一实现（本函数签名
    保持不变，调用方零改动）。filename 同时给 ``filename="..."``（百分号编码，
    ASCII 安全）与 ``filename*=UTF-8''...`` 两个形态，防止文件名中的引号 /
    换行破坏响应头。
    """
    return content_disposition(filename, inline=disposition == "inline")


def _serve_attachment(msg: InboxMessage, part_index: int, *, inline: bool) -> FileResponse:
    """通过 fetcher 按需下载并返回附件。

    inline 仅对白名单 Content-Type（PDF / 常见位图图片）生效，其余（含邮件
    自报的 text/html、image/svg+xml）一律 ``application/octet-stream`` + 附件下载，
    防止外部邮件以附件形式注入同源可执行脚本。
    """
    from apps.message_hub.services import get_fetcher

    fetcher = get_fetcher(msg.source.source_type)
    content, filename, content_type = fetcher.download_attachment(
        msg.source,
        msg.message_id,
        part_index,
    )
    download_filename = _resolve_download_filename(msg, part_index, filename)
    disposition = "inline" if inline else "attachment"
    if inline and str(content_type or "").split(";")[0].strip().lower() not in _INLINE_SAFE_CONTENT_TYPES:
        logger.warning(
            "拒绝危险 Content-Type 的 inline 预览，强制附件下载: message=%s part=%s content_type=%s",
            msg.pk,
            part_index,
            content_type,
        )
        content_type = "application/octet-stream"
        disposition = "attachment"
    response = FileResponse(
        iter([content]),
        content_type=content_type,
        as_attachment=disposition == "attachment",
        filename=download_filename,
    )
    response["Content-Disposition"] = _build_content_disposition(disposition, download_filename)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/messages/{message_id}/contract-match", response=ContractMatchOut)
def suggest_contract_match(request: HttpRequest, message_id: int) -> Any:  # pragma: no cover
    """给出这条邮件可能关联的在办合同候选（一期：只读，不写财务数据）。

    匹配逻辑见 services/contract_match.py 的模块文档：多信号打分 + 阈值，
    只有案号精确命中才算「确定匹配」，其余交人工。
    """
    from apps.message_hub.services.contract_match import suggest_contracts_for_message

    msg = _get_message_or_404(request, message_id)
    return suggest_contracts_for_message(
        subject=msg.subject or "",
        body_text=msg.body_text or "",
        body_html=msg.body_html or "",
    )
