"""客户上传链接公开端点（无登录，token 即凭证）。

挂载于 ``/api/v1/public``。token 经 ``X-Upload-Token`` 头传递而非 path/query：
公开页 URL ``/u/{token}`` 本身携带 token（浏览器打开页面那一次请求无法避免
进访问日志），但后续 API 调用不再让 token 重复落入 nginx/代理日志——与
OnlyOffice「签名进 query 被日志收录」的教训同源。无效 token 一律 404，
不泄露链接存在性；有效但关闭（过期/作废/收满）返回可读状态供页面提示。
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.http import HttpRequest
from ninja import Form, Router

from apps.core.api.schemas import SchemaMixin
from apps.core.exceptions import NotFoundError
from apps.core.infrastructure.throttling import rate_limit, rate_limit_from_settings
from apps.message_hub.models import ClientUploadLink
from apps.message_hub.schemas import PublicLinkInfoOut, PublicUploadFileOut, PublicUploadOut
from apps.message_hub.services.client_upload_service import (
    LINK_STATE_OPEN,
    LinkClosedError,
    consume_link_upload,
    link_state,
    list_link_files,
    remaining_bytes,
    resolve_link_by_token,
)

logger = logging.getLogger("apps.message_hub")
router = Router()


def _link_from_header(request: HttpRequest) -> ClientUploadLink:
    """从 X-Upload-Token 头解析链接；缺失/无效一律 404（同形态，不给探测面）。"""
    token = request.headers.get("X-Upload-Token", "").strip()
    link = resolve_link_by_token(token)
    if link is None:
        raise NotFoundError("上传链接不存在或已关闭")
    return link


def _lawyer_display_name(link: ClientUploadLink) -> str:
    user = link.created_by
    if user is None:
        return ""
    return str(getattr(user, "real_name", "") or user.username or "")


@router.get("/material-link", response=PublicLinkInfoOut, auth=None)
@rate_limit(requests=60, window=60)
def get_link_info(request: HttpRequest) -> PublicLinkInfoOut:
    """链接信息（标题/说明/律师/绑定项目/状态/剩余额度）。"""
    link = _link_from_header(request)
    return PublicLinkInfoOut(
        title=link.title,
        note=link.note,
        client_name=link.client_name,
        lawyer_name=_lawyer_display_name(link),
        contract_name=str(link.contract.name) if link.contract else "",
        state=link_state(link),
        expires_at=SchemaMixin._resolve_datetime_iso(link.expires_at) or "",
        remaining_bytes=remaining_bytes(link),
    )


@router.post("/material-link/files", response={201: PublicUploadOut}, auth=None)
@rate_limit_from_settings("UPLOAD")
def upload_files(request: HttpRequest, remark: str = Form("")) -> PublicUploadOut:
    """客户上传一批文件（multipart，每次一个 files 字段），生成一个材料包。

    单文件类型/大小校验与压缩包展开沿用律师手动上传同一套规则。
    """
    link = _link_from_header(request)
    files = request.FILES.getlist("files")
    if not files:
        raise ValidationError("没有收到文件")
    state = link_state(link)
    if state != LINK_STATE_OPEN:
        raise LinkClosedError(state)
    message = consume_link_upload(link, list(files), remark)
    files_out = [
        PublicUploadFileOut(
            filename=str(att.get("filename") or att.get("original_filename") or ""),
            size=int(att.get("size", 0) or 0),
        )
        for att in message.attachments_meta or []
    ]
    link.refresh_from_db(fields=["used_bytes", "quota_total_bytes"])
    return PublicUploadOut(files=files_out, remaining_bytes=remaining_bytes(link))


@router.get("/material-link/files", response=list[PublicUploadFileOut], auth=None)
@rate_limit(requests=60, window=60)
def list_uploaded_files(request: HttpRequest) -> list[dict[str, object]]:
    """该链接已收文件名录（仅文件名+大小），供客户续传时核对已交内容。"""
    link = _link_from_header(request)
    return list_link_files(link)
