"""前端手动上传：把预处理上传的文件收进收件箱，并维护拆分草稿。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.core.files.storage import default_storage
from django.utils import timezone

from apps.message_hub.models import InboxMessage, MessageSource, SourceType
from apps.message_hub.services.base import MessageFetcher, resolve_media_attachment_path

logger = logging.getLogger("apps.message_hub")

MANUAL_SOURCE_DISPLAY_NAME = "前端材料预处理上传"


class ManualUploadFetcher(MessageFetcher):
    """手动上传来源不对外拉取，附件已本地落盘，按需读取即可。"""

    def fetch_new_messages(self, source: MessageSource) -> int:  # pragma: no cover
        return 0

    def download_attachment(  # pragma: no cover
        self, source: MessageSource, message_id: str, part_index: int
    ) -> tuple[bytes, str, str]:
        msg = InboxMessage.objects.filter(source=source, message_id=message_id).only("attachments_meta").first()
        if msg and isinstance(msg.attachments_meta, list):
            for att in msg.attachments_meta:
                if int(att.get("part_index", -1)) != part_index:
                    continue
                resolved = resolve_media_attachment_path(str(att.get("local_path", "")))
                if resolved is not None and resolved.exists():
                    filename = str(att.get("filename") or att.get("original_filename") or f"attachment_{part_index}")
                    content_type = str(att.get("content_type") or "application/octet-stream")
                    return resolved.read_bytes(), filename, content_type
        raise ValueError(f"附件不存在: source={source.pk}, message={message_id}, part={part_index}")


def get_or_create_manual_source() -> MessageSource:
    """获取或创建手动上传来源（无外部账号，credential 为空）。"""
    source, _ = MessageSource.objects.get_or_create(
        source_type=SourceType.MANUAL_UPLOAD,
        defaults={
            "display_name": MANUAL_SOURCE_DISPLAY_NAME,
            "credential": None,
            "is_enabled": True,
            "sync_since": timezone.now(),
            "poll_interval_minutes": 0,
        },
    )
    return source


def create_manual_message(files: list[Any], subject: str = "", uploaded_by: Any = None) -> InboxMessage:
    """把前端上传的文件落盘为一条收件箱消息，返回消息实例。

    files 为 UploadedFile 列表；附件落到 message_hub/manual/ 暂存路径，
    元数据记录相对 MEDIA_ROOT 的 local_path，与 IMAP 附件同一存储协议。
    uploaded_by 为当前登录律师，记录上传人。
    """
    source = get_or_create_manual_source()
    attachment_metas: list[dict[str, Any]] = []
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    for part_index, uploaded in enumerate(files):
        safe_name = Path(uploaded.name).name or f"attachment_{part_index}"
        rel_path = f"message_hub/manual/{source.pk}/{ts}/{part_index}_{safe_name}"
        # 兼容中文 / 回车文件名，default_storage.save 会再做一次安全清洗
        saved = default_storage.save(rel_path, uploaded)
        attachment_metas.append(
            {
                "filename": safe_name,
                "original_filename": safe_name,
                "custom_filename": "",
                "content_type": uploaded.content_type or "application/octet-stream",
                "size": uploaded.size,
                "part_index": part_index,
                "local_path": saved,
            }
        )
        uploaded.seek(0)

    effective_subject = subject.strip() or f"{MANUAL_SOURCE_DISPLAY_NAME}材料"
    message = InboxMessage.objects.create(
        source=source,
        message_id=f"manual-{ts}-{uuid4().hex[:8]}",
        subject=effective_subject,
        sender="",
        received_at=timezone.now(),
        body_text="",
        body_html="",
        has_attachments=bool(attachment_metas),
        attachments_meta=attachment_metas,
        draft_state={},
        uploaded_by=uploaded_by,
    )
    logger.info("手动上传生成收件箱消息 id=%s，附件 %d 份", message.pk, len(attachment_metas))
    return message


def save_draft(message_id: int, draft: dict[str, Any]) -> InboxMessage:
    """保存拆分草稿到收件箱消息。"""
    message = InboxMessage.objects.get(pk=message_id)
    message.draft_state = draft or {}
    message.save(update_fields=["draft_state"])
    return message
