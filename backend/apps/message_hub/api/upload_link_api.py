"""客户上传链接 API（律师端，JWT 鉴权由收件箱父 Router 统一挂）。"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.core.exceptions import NotFoundError
from apps.core.security.admin_access import is_admin_user
from apps.message_hub.models import ClientUploadLink, UploadLinkStatus
from apps.message_hub.schemas import UploadLinkCreatedOut, UploadLinkCreateIn, UploadLinkOut

logger = logging.getLogger("apps.message_hub")
router = Router()


def _get_owned_link(request: HttpRequest, link_id: int) -> ClientUploadLink:
    """取链接并校验归属：仅创建人与管理员可操作（不存在/无权统一 404）。"""
    link = ClientUploadLink.objects.select_related("created_by", "contract").filter(pk=link_id).first()
    if link is None:
        raise NotFoundError(f"上传链接 {link_id} 不存在")
    if link.created_by_id != getattr(request.user, "id", None) and not is_admin_user(request.user):
        raise NotFoundError(f"上传链接 {link_id} 不存在")
    return link


@router.post("/upload-links", response={201: UploadLinkCreatedOut})
def create_link(request: HttpRequest, payload: UploadLinkCreateIn) -> tuple[int, ClientUploadLink]:
    """生成客户上传链接，响应附带 token 明文（仅此一次，前端即时组装 /u/{token}）。"""
    from apps.message_hub.services.client_upload_service import create_upload_link

    link, token = create_upload_link(
        created_by=request.user,
        title=payload.title,
        note=payload.note,
        client_name=payload.client_name,
        contract_id=payload.contract_id,
        expires_days=payload.expires_days,
    )
    # token 明文经瞬态属性随本次响应出现一次（列表 Schema 不含 token 字段）
    link.token = token  # type: ignore[attr-defined]
    return 201, link


@router.get("/upload-links", response=list[UploadLinkOut])
def list_links(request: HttpRequest) -> Any:
    """我的客户上传链接列表（管理员全量），含已收包数/字节与实时状态。"""
    from apps.message_hub.services.client_upload_service import list_links_for_user

    return list_links_for_user(request.user)


@router.post("/upload-links/{link_id}/revoke", response=UploadLinkOut)
def revoke_link(request: HttpRequest, link_id: int) -> ClientUploadLink:
    """作废链接（客户手里的旧 URL 立即失效）。"""
    from apps.message_hub.services.client_upload_service import revoke_upload_link

    link = _get_owned_link(request, link_id)
    return revoke_upload_link(link)


@router.post("/upload-links/{link_id}/rotate", response=UploadLinkCreatedOut)
def rotate_link(request: HttpRequest, link_id: int) -> ClientUploadLink:
    """换发新 token（旧 URL 立即失效）；仅生效中的链接可换，已作废请重新创建。"""
    from apps.core.exceptions import ValidationException
    from apps.message_hub.services.client_upload_service import rotate_upload_link

    link = _get_owned_link(request, link_id)
    if link.status != UploadLinkStatus.ACTIVE:
        raise ValidationException("链接已作废，请删除后重新创建", code="LINK_NOT_ACTIVE")
    link.token = rotate_upload_link(link)  # type: ignore[attr-defined]
    return link
