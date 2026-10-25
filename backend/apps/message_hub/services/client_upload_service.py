"""客户上传链接：生成 / 校验 / 消费，文件汇入收件箱材料预处理流水线。

链接即凭证（capability URL）模型：
- token 明文 ``secrets.token_urlsafe(32)``（256-bit 不可枚举），库存 SHA-256；
- 生命周期 = 状态（active/revoked）∩ 有效期 ∩ 配额，任一不满足即关闭；
- 上传产生的收件箱消息 ``uploaded_by = 链接创建律师``——可见性完全复用
  ``inbox_access`` 的既有收敛（本人 + 管理员），不新开权限面。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import PermissionDenied, ValidationException
from apps.message_hub.models import ClientUploadLink, InboxMessage, MessageSource, SourceType, UploadLinkStatus
from apps.message_hub.services.archive_extract_service import expand_upload_files
from apps.message_hub.services.attachment_page_service import fill_page_counts
from apps.message_hub.services.manual_upload_service import save_upload_files_as_metas, validate_manual_upload_file

logger = logging.getLogger("apps.message_hub")

CLIENT_SOURCE_DISPLAY_NAME = "客户链接上传"

# token 熵：token_urlsafe(32) → 43 字符 URL-safe、256-bit，枚举不可行
TOKEN_RANDOM_BYTES = 32
# 创建时可选的有效期（天）与默认值
ALLOWED_EXPIRES_DAYS = (1, 7, 30, 90)
DEFAULT_EXPIRES_DAYS = 30

LINK_STATE_OPEN = "open"
LINK_STATE_EXPIRED = "expired"
LINK_STATE_REVOKED = "revoked"
LINK_STATE_FULL = "full"


class LinkClosedError(PermissionDenied):
    """链接已关闭（过期/作废/收满），拒绝继续上传。"""

    def __init__(self, state: str) -> None:
        reason = {
            LINK_STATE_EXPIRED: "链接已过期，请联系律师重新获取",
            LINK_STATE_REVOKED: "链接已作废，请联系律师重新获取",
            LINK_STATE_FULL: "链接已收满，请联系律师处理已收材料",
        }.get(state, "链接已关闭")
        super().__init__(message=reason, code="UPLOAD_LINK_CLOSED")
        self.state = state


def hash_token(token: str) -> str:
    """token → SHA-256 hex（库存形态）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _contract_exists(contract_id: int) -> bool:
    """校验委托合同存在。经 apps registry 取模型，避免跨业务模块静态 import。"""
    from django.apps import apps

    contract_model = apps.get_model("contracts", "Contract")
    return contract_model.objects.filter(pk=contract_id).exists()


def create_upload_link(
    *,
    created_by: Any,
    title: str,
    note: str = "",
    client_name: str = "",
    contract_id: int | None = None,
    expires_days: int = DEFAULT_EXPIRES_DAYS,
) -> tuple[ClientUploadLink, str]:
    """生成一条客户上传链接，返回 (链接, token 明文)——明文只此一次。"""
    name = title.strip()
    if not name:
        raise ValidationException("链接标题不能为空", code="LINK_TITLE_REQUIRED", errors={"title": "请填写标题"})
    if len(name) > 200:
        name = name[:200]
    days = int(expires_days)
    if days not in ALLOWED_EXPIRES_DAYS:
        raise ValidationException(
            f"有效期只允许 {sorted(ALLOWED_EXPIRES_DAYS)} 天",
            code="LINK_EXPIRES_INVALID",
            errors={"expires_days": "有效期不合法"},
        )
    if contract_id is not None and not _contract_exists(int(contract_id)):
        raise ValidationError("绑定的项目不存在")

    token = secrets.token_urlsafe(TOKEN_RANDOM_BYTES)
    link = ClientUploadLink.objects.create(
        title=name,
        note=note.strip(),
        client_name=client_name.strip(),
        token_hash=hash_token(token),
        created_by=created_by,
        contract_id=contract_id,
        expires_at=timezone.now() + timedelta(days=days),
        status=UploadLinkStatus.ACTIVE,
    )
    logger.info("创建客户上传链接 id=%s title=%s contract=%s", link.pk, name, contract_id)
    return link, token


def resolve_link_by_token(token: str) -> ClientUploadLink | None:
    """按 token 哈希取链接；无效 token 与不存在同形（None）。"""
    cleaned = (token or "").strip()
    if not cleaned:
        return None
    return ClientUploadLink.objects.filter(token_hash=hash_token(cleaned)).first()


def link_state(link: ClientUploadLink) -> str:
    """链接当前状态：open 可收，其余为关闭原因。"""
    if link.status == UploadLinkStatus.REVOKED:
        return LINK_STATE_REVOKED
    if timezone.now() >= link.expires_at:
        return LINK_STATE_EXPIRED
    if link.pack_count >= link.quota_max_packs or link.used_bytes >= link.quota_total_bytes:
        return LINK_STATE_FULL
    return LINK_STATE_OPEN


def remaining_bytes(link: ClientUploadLink) -> int:
    return max(0, link.quota_total_bytes - link.used_bytes)


def revoke_upload_link(link: ClientUploadLink) -> ClientUploadLink:
    """作废链接（持有旧 token 的页面立即失效）。"""
    link.status = UploadLinkStatus.REVOKED
    link.save(update_fields=["status", "updated_at"])
    logger.info("作废客户上传链接 id=%s", link.pk)
    return link


def rotate_upload_link(link: ClientUploadLink) -> str:
    """换发新 token（旧 token 立即失效），返回新明文——只此一次。"""
    token = secrets.token_urlsafe(TOKEN_RANDOM_BYTES)
    link.token_hash = hash_token(token)
    link.save(update_fields=["token_hash", "updated_at"])
    logger.info("轮换客户上传链接 token id=%s", link.pk)
    return token


def get_or_create_client_source() -> MessageSource:
    """获取或创建客户上传来源（与手动上传同构：无凭证、不轮询）。"""
    source, _ = MessageSource.objects.get_or_create(
        source_type=SourceType.CLIENT_UPLOAD,
        defaults={
            "display_name": CLIENT_SOURCE_DISPLAY_NAME,
            "credential": None,
            "is_enabled": True,
            "sync_since": timezone.now(),
            "poll_interval_minutes": 0,
        },
    )
    return source


def consume_link_upload(link: ClientUploadLink, files: list[Any], remark: str = "") -> InboxMessage:
    """客户经链接上传一批文件：校验→展开→落盘→建收件箱消息→扣配额。

    每批 = 一个独立材料包（并发安全，不与既有包的 draft_state 抢行锁）；
    消息 ``uploaded_by`` 归链接创建律师，desk 可见性零改动。
    """
    # 先整批校验再落盘：中途失败不产生半落盘的孤儿附件（与手动上传同口径）
    for uploaded in files:
        validate_manual_upload_file(uploaded)
    files = expand_upload_files(files)
    if not files:
        raise ValidationException(
            "压缩包是空的（或内容全部被过滤）",
            code="ARCHIVE_EMPTY",
            errors={"files": "压缩包内没有可用的文件"},
        )
    total_bytes = sum(int(getattr(f, "size", 0) or 0) for f in files)
    note = (remark or "").strip()

    with transaction.atomic():
        # 行锁重取链接：配额计数是读-改-写，并发上传须串行化后再复核额度
        locked = ClientUploadLink.objects.select_for_update().get(pk=link.pk)
        state = link_state(locked)
        if state != LINK_STATE_OPEN:
            raise LinkClosedError(state)
        if locked.used_bytes + total_bytes > locked.quota_total_bytes:
            raise ValidationException(
                "超出链接容量（剩余不足）",
                code="LINK_QUOTA_EXCEEDED",
                errors={"files": "本次上传超出链接剩余容量，请减少文件或联系律师"},
            )
        ts = timezone.localtime().strftime("%Y%m%d%H%M%S")
        metas = save_upload_files_as_metas(files, rel_dir=f"message_hub/client/{locked.pk}/{ts}")
        fill_page_counts(metas)
        message = InboxMessage.objects.create(
            source=get_or_create_client_source(),
            message_id=f"client-{ts}-{uuid4().hex[:8]}",
            subject=f"{locked.title}·客户上传",
            sender=locked.client_name or "外部客户",
            received_at=timezone.now(),
            body_text=note,
            body_html="",
            has_attachments=bool(metas),
            attachments_meta=metas,
            draft_state={},
            uploaded_by=locked.created_by,
            upload_link=locked,
        )
        locked.used_bytes += total_bytes
        locked.pack_count += 1
        locked.last_uploaded_at = timezone.now()
        locked.save(update_fields=["used_bytes", "pack_count", "last_uploaded_at", "updated_at"])
    logger.info("客户链接上传生成收件箱消息 id=%s，链接 %s，附件 %d 份", message.pk, link.pk, len(metas))
    return message


def list_link_files(link: ClientUploadLink) -> list[dict[str, Any]]:
    """链接已收文件名录（仅文件名+大小，供客户续传时核对已交内容）。"""
    out: list[dict[str, Any]] = []
    msgs = InboxMessage.objects.filter(upload_link=link).order_by("received_at")
    for msg in msgs:
        for att in msg.attachments_meta or []:
            out.append(
                {
                    "filename": str(att.get("filename") or att.get("original_filename") or ""),
                    "size": int(att.get("size", 0) or 0),
                }
            )
    return out


def list_links_for_user(user: Any) -> Any:
    """按用户收敛的链接列表：本人创建；管理员全量（与收件箱可见性同口径）。"""
    from apps.core.security.admin_access import is_admin_user

    qs = ClientUploadLink.objects.select_related("created_by", "contract").order_by("-created_at")
    if is_admin_user(user):
        return qs
    return qs.filter(created_by_id=getattr(user, "id", None))
