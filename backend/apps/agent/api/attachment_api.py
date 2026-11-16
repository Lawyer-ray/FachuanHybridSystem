"""Agent 附件 API —— 上传、读正文、分页渲染，以及绑定文件夹引用。

端点前缀：``/api/v1/agent``（附件子域）。``/content`` 与 ``/pages`` 是
mcp_server 专用（用户 token 鉴权），base64 只在服务端流转，不直接进模型上下文。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

from apps.core.security import get_request_access_context
from apps.core.security.auth import JWTOrSessionAuth

from ..schemas import AttachmentOut, AttachmentPagesOut, FolderRefIn
from ..services.attachments import (
    create_attachment,
    get_attachment_for_user,
    read_attachment_content,
    render_attachment_pages,
)
from ..services.folder_refs import create_folder_ref, read_folder_file_content, render_folder_file_pages
from ..services.session_service import get_session as get_session_record
from ._helpers import _current_user, _user_id
from ._pages import _PAGES_DPI_DEFAULT, _PAGES_MAX_PAGES, _pages_out, _parse_page_params

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 附件"], auth=JWTOrSessionAuth())


@router.post("/sessions/{session_id}/attachments", response=AttachmentOut)
async def upload_attachment(request: Any, session_id: str) -> Any:
    """上传一个对话附件（multipart 字段名 ``file``；白名单/20MB 限额见 service）。

    归属：会话必须属于当前用户。上传后前端在消息里附
    「[已上传附件：name (attachment_id=…)]」，模型用 read_agent_attachment 读正文。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    uploaded = request.FILES.get("file")
    if uploaded is None:
        raise HttpError(400, "缺少 file 字段")
    # 校验类异常（超大/白名单外）由 service 抛 ValidationException，全局处理器
    # 统一翻成 400；其余异常如实走全局 5xx，不吞不降级（API 层不做 try/except）。
    attachment = await sync_to_async(create_attachment, thread_sensitive=True)(
        session=session, user_id=_user_id(request), uploaded_file=uploaded
    )
    return AttachmentOut(
        attachment_id=str(attachment.attachment_id),
        filename=attachment.filename,
        size=attachment.size,
        mime=attachment.mime,
    )


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(request: Any, attachment_id: str) -> Any:
    """读附件原始内容（base64）——**mcp_server 专用**（用户 token 鉴权）。

    返回内容只用于服务端转投 /document-parsing 提取正文，不会直接进入模型
    上下文；前端不需要也不应消费本端点。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    attachment = await sync_to_async(get_attachment_for_user, thread_sensitive=True)(
        attachment_id=attachment_id, user_id=_user_id(request)
    )
    if attachment is None:
        # 不区分「不存在」与「不属于你」，避免校验式枚举
        raise HttpError(404, "附件不存在")
    return await sync_to_async(read_attachment_content, thread_sensitive=True)(attachment)


@router.get("/attachments/{attachment_id}/pages", response=AttachmentPagesOut)
async def get_attachment_pages(
    request: Any,
    attachment_id: str,
    pages: str = "all",
    dpi: str = str(_PAGES_DPI_DEFAULT),
    #: 对外查询参数名（MCP 侧已按 format 写死）；函数内立刻重命名为 fmt，
    #: 避免与内置 format() 混淆
    format: str = "png",
    max_pages: str = str(_PAGES_MAX_PAGES),
) -> AttachmentPagesOut:
    """把附件按页渲染成图片（base64）——**mcp_server 专用**（用户 token 鉴权）。

    PDF 走 PyMuPDF 逐页渲染：扫描件的文本提取为空，但页面图里是真实内容，
    模型看图仍能读——这是「解析为空」的附件需要的另一条腿。

    三段状态严格分开，不让调用方猜：

    - 参数非法（pages 语法错 / dpi 非数字 / format 不认识）→ 400
    - 归属不符或不存在 → 404（不区分，防枚举 attachment_id）
    - 渲染失败（encrypted / too_large / unsupported_mime / page_out_of_range /
      parse_empty）→ **200 + error 错误码**：mcp_server 要把错误码翻译成模型
      看得懂的原因，500 会让它只剩「服务端错误」

    权限与 /content 端点同一口径：``get_attachment_for_user``（只认会话所有者，
    超管同样 fail-closed），这里不放宽也不跳过。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    attachment = await sync_to_async(get_attachment_for_user, thread_sensitive=True)(
        attachment_id=attachment_id, user_id=_user_id(request)
    )
    if attachment is None:
        # 与 /content 同文案：不区分「不存在」与「不属于你」，避免校验式枚举
        raise HttpError(404, "附件不存在")
    pages_spec, requested_dpi, fmt, requested_max = _parse_page_params(
        pages=pages, dpi=dpi, format=format, max_pages=max_pages
    )
    outcome = await sync_to_async(render_attachment_pages, thread_sensitive=True)(
        attachment,
        pages=pages_spec,
        dpi=requested_dpi,
        format=fmt,
        max_pages=requested_max,
        user_id=_user_id(request),
    )
    payload = _pages_out(outcome, requested_max=requested_max)
    # 审计由 T1 的 log_render 在门面内完成（who/attachment_id/pages/strategy/bytes）；
    # 这里再记一条端点级日志，带上请求参数原文——排查「为什么只给了 2 页」要看
    # 调用方当时到底要了什么，而门面只看到解析后的页码。
    logger.info(
        "附件分页端点 user=%s attachment_id=%s pages=%r dpi=%d format=%s returned=%d error=%s",
        _user_id(request),
        payload.attachment_id,
        pages_spec,
        requested_dpi,
        fmt,
        len(payload.pages_returned),
        payload.error or "-",
    )
    return payload


@router.post("/sessions/{session_id}/folder-refs", response=AttachmentOut)
async def create_session_folder_ref(request: Any, session_id: str, data: FolderRefIn) -> Any:
    """拖拽引用落库：引用合同绑定文件夹内的原文件（不复制字节、storage_path 留空）。

    归属：会话必须属于当前用户；合同侧走行级 ACL（与 folder-entries 目录树
    同口径——团队共享合同，协办律师同样可引用）。文件名/MIME/大小为创建时快照。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    ctx = get_request_access_context(request)
    # 无权/未绑定/文件不存在由 service 抛 NotFoundError（全局 404，不区分防枚举），
    # subpath 非法抛 ValidationException（全局 400）；API 层不做 try/except。
    ref = await sync_to_async(create_folder_ref, thread_sensitive=True)(
        session=session,
        user_id=_user_id(request),
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
        owner_kind=data.kind,
        owner_id=data.owner_id,
        subpath=data.subpath,
    )
    return AttachmentOut(
        attachment_id=str(ref.attachment_id),
        filename=ref.filename,
        size=ref.size,
        mime=ref.mime,
        ref_owner_kind=ref.ref_owner_kind,
        ref_contract_id=ref.ref_contract_id,
        ref_subpath=ref.ref_subpath,
    )


@router.get("/folder-refs/content")
async def get_folder_ref_content(request: Any, kind: str = "contract", owner_id: int = 0, subpath: str = "") -> Any:
    """读绑定文件夹内原文件（base64）——**mcp_server 专用**（用户 token 鉴权）。

    与 /attachments/{id}/content 同构：内容只用于服务端转投 /document-parsing
    提取正文，不直接进模型上下文。权限与 folder-entries 同口径（行级 ACL）；
    kind=contract/case 决定走合同还是案件的绑定文件夹。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    if kind not in ("contract", "case") or owner_id <= 0:
        raise HttpError(400, "kind 仅支持 contract/case 且 owner_id 必须为正整数")
    ctx = get_request_access_context(request)
    return await sync_to_async(read_folder_file_content, thread_sensitive=True)(
        owner_kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/folder-refs/pages", response=AttachmentPagesOut)
async def get_folder_ref_pages(
    request: Any,
    kind: str = "contract",
    owner_id: int = 0,
    subpath: str = "",
    pages: str = "all",
    dpi: str = str(_PAGES_DPI_DEFAULT),
    format: str = "png",
    max_pages: str = str(_PAGES_MAX_PAGES),
) -> AttachmentPagesOut:
    """把绑定文件夹内文件按页渲染成图（base64）——**mcp_server 专用**。

    与 /attachments/{id}/pages 同构（三段状态：参数非法 400 / 无权或不存在
    404 / 渲染失败 200 + error 错误码）；页图缓存键含源文件 size/mtime 指纹，
    文件被替换后旧缓存自动失效。
    """
    user = _current_user(request)
    if user is None:
        raise HttpError(401, "未登录")
    if kind not in ("contract", "case") or owner_id <= 0:
        raise HttpError(400, "kind 仅支持 contract/case 且 owner_id 必须为正整数")
    pages_spec, requested_dpi, fmt, requested_max = _parse_page_params(
        pages=pages, dpi=dpi, format=format, max_pages=max_pages
    )
    ctx = get_request_access_context(request)
    outcome = await sync_to_async(render_folder_file_pages, thread_sensitive=True)(
        owner_kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
        pages=pages_spec,
        dpi=requested_dpi,
        fmt=fmt,
        max_pages=requested_max,
        user_id=_user_id(request),
    )
    payload = _pages_out(outcome, requested_max=requested_max)
    logger.info(
        "folder_refs_pages user=%s kind=%s owner_id=%s subpath=%r pages=%r dpi=%d format=%s returned=%d error=%s",
        _user_id(request),
        kind,
        owner_id,
        subpath,
        pages_spec,
        requested_dpi,
        fmt,
        len(payload.pages_returned),
        payload.error or "-",
    )
    return payload
