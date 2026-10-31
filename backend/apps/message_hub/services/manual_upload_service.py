"""前端手动上传：把预处理上传的文件收进收件箱，并维护拆分草稿。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.core.services.storage_service import delete_media_file
from apps.message_hub.models import InboxMessage, MessageSource, SourceType
from apps.message_hub.services.archive_extract_service import expand_upload_files
from apps.message_hub.services.attachment_page_service import fill_page_counts
from apps.message_hub.services.base import MessageFetcher, resolve_media_attachment_path
from apps.message_hub.services.upload_policy import (
    MANUAL_UPLOAD_ALLOWED_EXTENSIONS,
    MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES,
    MANUAL_UPLOAD_MAX_SIZE_BYTES,
    is_archive_filename,
    is_multipart_filename,
    validate_manual_upload_file,
)

# 白名单、大小上限与 validate_manual_upload_file 定义在 upload_policy（与压缩包
# 展开服务共用，避开 import 环）；此处 re-export 保持历史导入路径可用。
__all__ = [
    "MANUAL_SOURCE_DISPLAY_NAME",
    "MANUAL_UPLOAD_ALLOWED_EXTENSIONS",
    "MANUAL_UPLOAD_ARCHIVE_MAX_SIZE_BYTES",
    "MANUAL_UPLOAD_MAX_SIZE_BYTES",
    "ManualUploadFetcher",
    "append_manual_attachments",
    "create_manual_message",
    "delete_manual_message",
    "get_or_create_manual_source",
    "is_archive_filename",
    "is_multipart_filename",
    "rename_manual_message",
    "save_draft",
    "save_upload_files_as_metas",
    "validate_manual_upload_file",
]

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


def save_upload_files_as_metas(
    files: list[Any],
    *,
    rel_dir: str,
    start_index: int = 0,
) -> list[dict[str, Any]]:
    """把 UploadedFile 列表按收件箱暂存协议落盘，返回 attachments_meta 条目。

    收件箱两类上传（律师手动 / 客户链接）共用同一存储协议：显示名保留相对
    路径（压缩包展开的「子目录/文件.pdf」），落盘仅取 basename——part_index
    前缀已保证唯一，目录结构不进存储树。start_index 供追加场景接着现有
    part_index 排。
    """
    metas: list[dict[str, Any]] = []
    for offset, uploaded in enumerate(files):
        part_index = start_index + offset
        display_name = str(uploaded.name) or f"attachment_{part_index}"
        storage_name = Path(display_name).name
        rel_path = f"{rel_dir}/{part_index}_{storage_name}"
        # 兼容中文 / 回车文件名，default_storage.save 会再做一次安全清洗
        saved = default_storage.save(rel_path, uploaded)
        meta: dict[str, Any] = {
            "filename": display_name,
            "original_filename": display_name,
            "custom_filename": "",
            "content_type": getattr(uploaded, "content_type", None) or "application/octet-stream",
            "size": uploaded.size,
            "part_index": part_index,
            "local_path": saved,
        }
        expanded_from = str(getattr(uploaded, "expanded_from", "") or "")
        if expanded_from:
            meta["expanded_from"] = expanded_from
        metas.append(meta)
        uploaded.seek(0)
    return metas


def create_manual_message(files: list[Any], subject: str = "", uploaded_by: Any = None) -> InboxMessage:
    """把前端上传的文件落盘为一条收件箱消息，返回消息实例。

    files 为 UploadedFile 列表；附件落到 message_hub/manual/ 暂存路径，
    元数据记录相对 MEDIA_ROOT 的 local_path，与 IMAP 附件同一存储协议。
    uploaded_by 为当前登录律师，记录上传人。

    zip/rar/7z 压缩包在这里展开为包内文件（与逐个直传等价，白名单/限额
    同口径；嵌套压缩包不递归）；展开后一个文件都没有视为空包拒绝。
    """
    # 先整批校验再落盘：中途失败不产生半落盘的孤儿附件
    for uploaded in files:
        validate_manual_upload_file(uploaded)
    files = expand_upload_files(files)
    if not files:
        raise ValidationException(
            "压缩包是空的（或内容全部被过滤）",
            code="ARCHIVE_EMPTY",
            errors={"files": "压缩包内没有可用的文件"},
        )
    source = get_or_create_manual_source()
    ts = timezone.localtime().strftime("%Y%m%d%H%M%S")
    attachment_metas = save_upload_files_as_metas(files, rel_dir=f"message_hub/manual/{source.pk}/{ts}")
    # 上传即算好 PDF 页数，前端打开材料包无需下载整包数页数
    fill_page_counts(attachment_metas)

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


def append_manual_attachments(message: InboxMessage, files: list[Any]) -> InboxMessage:
    """往现有材料包（manual_upload 消息）追加附件。

    新附件沿用与 create_manual_message 相同的落盘协议，part_index 接着现有最大值排，
    不触碰拆分草稿（新素材由前端拉详情后并入 draft_state）。
    """
    # 先整批校验再落盘：中途失败不产生半落盘的孤儿附件
    for uploaded in files:
        validate_manual_upload_file(uploaded)
    # 追加同样支持压缩包展开（与首次上传同口径）
    files = expand_upload_files(files)
    if not files:
        raise ValidationException(
            "压缩包是空的（或内容全部被过滤）",
            code="ARCHIVE_EMPTY",
            errors={"files": "压缩包内没有可用的文件"},
        )
    with transaction.atomic():
        # 行锁重取消息行：attachments_meta 是 JSONField 读-改-写，并发追加
        # 会互相覆盖且 part_index 重复，锁行串行化后再基于最新 meta 追加。
        locked = InboxMessage.objects.select_for_update().get(pk=message.pk)
        metas = list(locked.attachments_meta or [])
        last_pi = max((int(a.get("part_index", -1)) for a in metas), default=-1)
        ts = timezone.localtime().strftime("%Y%m%d%H%M%S")
        new_metas = save_upload_files_as_metas(
            files,
            rel_dir=f"message_hub/manual/{locked.source_id}/{ts}",
            start_index=last_pi + 1,
        )
        metas.extend(new_metas)
        fill_page_counts(metas)
        locked.attachments_meta = metas
        locked.has_attachments = bool(metas)
        locked.save(update_fields=["attachments_meta", "has_attachments"])
        # 同步回调用方持有的实例，保持对象与库内一致
        message.attachments_meta = metas
        message.has_attachments = locked.has_attachments
        logger.info("材料包 %s 追加附件 %d 份", locked.pk, len(files))
    return message


def _strip_nul(value: Any) -> Any:
    """递归去掉字符串里的 NUL（\u0000）。

    ═══ 为什么必须清 ═══
    PostgreSQL 的 text / jsonb 都**不接受 NUL 字符**，写入直接抛
    `UntranslatableCharacter: unsupported Unicode escape sequence`，
    接口回 500「系统错误」。而 NUL 的来源很常见：
      · OCR 引擎对扫描件空白区域输出的填充字符
      · 某些 PDF 提取库对断行的处理
      · 用户从别的系统粘贴的文本
    草稿里存的是 OCR 识别出的页面文字，一旦带进 NUL，整个材料包的拆分结果
    **永远存不下来** —— 前端每次自动保存都 500，用户看到「保存失败，请检查
    后端连接」，其实后端好好的，只是这一个字符写不进库。

    在写库前统一清掉，比在每个 OCR 出口拦一遍可靠：入口只有一个。
    """
    if isinstance(value, str):
        # 只删 NUL，其余控制字符（\n \t 等）保留 —— 它们对展示有意义
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_nul(v) for k, v in value.items()}
    return value


def save_draft(message_id: int, draft: dict[str, Any]) -> InboxMessage:
    """保存拆分草稿到收件箱消息。

    写入前清掉 NUL 字符（原因见 _strip_nul 的说明）——不清会让整个草稿
    保存 500，用户看到的是「保存失败，请检查后端连接」。
    """
    message = InboxMessage.objects.get(pk=message_id)
    message.draft_state = _strip_nul(draft) or {}
    message.save(update_fields=["draft_state"])
    return message


def rename_manual_message(message: InboxMessage, subject: str) -> InboxMessage:
    """重命名材料包（收件箱消息标题）。subject 去首尾空白后必须非空。"""
    name = subject.strip()
    if not name:
        raise ValidationError("材料包名称不能为空")
    if len(name) > 512:
        name = name[:512]
    message.subject = name
    message.save(update_fields=["subject"])
    logger.info("材料包 %s 重命名为 %s", message.pk, name)
    return message


def delete_manual_message(message: InboxMessage) -> int:
    """硬删一条收件箱消息，并清理其附件物理文件。返回清理的附件数。

    附件落在 message_hub/manual/ 暂存目录，不走 Material 体系，
    删除 DB 记录前须先按 local_path 用 delete_media_file() 清掉物理文件，避免留垃圾。
    """
    metas = message.attachments_meta or []
    deleted = 0
    for att in metas:
        local_path = str(att.get("local_path", "") or "")
        if local_path and delete_media_file(local_path):
            deleted += 1
    pk = message.pk
    message.delete()
    logger.info("删除收件箱消息 id=%s，清理附件 %d 份", pk, deleted)
    return deleted
