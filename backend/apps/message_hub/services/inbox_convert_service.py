"""收件箱消息 → 材料包（manual_upload）的转换链路。

**为什么需要它**：收件箱里 338 条消息绝大多数来自一张网（court_inbox）与 IMAP，
它们的附件是「外部拉取」的原始形态——数据源一侧随时可能变化、正文可能只是通知。
材料预处理工作台只认 manual_upload（附件落在 message_hub/manual 暂存目录、有
draft_state 拆分草稿语义）。没有这条链路，法院送达的 PDF 只能看不能拆，
「点开收件箱 → 进材料预处理」就走不通。

**为什么不原地改 source_type**：来源是外部数据源的归属凭据，改它会让 IMAP 增量
同步（last_synced_uid / message_id 去重）把同一条消息再拉一遍；而且一条法院消息
的附件可能被拆成多个材料包处理。所以转换 = 在 manual_upload 下**新建**一条消息，
把字节拷进暂存目录，原消息用 converted_message 指过去。

**幂等**：同一条消息重复点「转材料包」不再生成第二个包，直接返回首次生成的那个
（并发下靠原消息行锁串行化，见 convert_to_material_pack）。
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ValidationException
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.manual_upload_service import save_upload_files_as_metas

logger = logging.getLogger("apps.message_hub")

# 转换只搬运文件，不搬运 draft_state：拆分草稿是拆包会话的一部分，
# 新包应从「未拆」开始（draft_state={} 即 isEmptyDraft）。
CONVERTIBLE_SOURCE_TYPES = frozenset({"imap", "court_inbox", "court_sms", "court_schedule"})


def _download_source_attachment(msg: InboxMessage, part_index: int, filename: str) -> ContentFile:
    """按来源 fetcher 取附件字节，包成 ContentFile（default_storage.save 只认它）。

    不要自己写一个只有名字的假 UploadedFile：FileSystemStorage._save 是按
    分块 while 循环 read() 写入的，read() 不推进游标就永远不会 EOF（现场
    表现为整个转换卡死，不是报错）。ContentFile 自带游标与 name 属性，直接对得上。
    """
    from apps.message_hub.services import get_fetcher

    fetcher = get_fetcher(msg.source.source_type)
    content, served_name, _content_type = fetcher.download_attachment(msg.source, msg.message_id, part_index)
    return ContentFile(content, name=served_name or filename or f"attachment_{part_index}")


def convert_to_material_pack(msg: InboxMessage, *, uploaded_by: Any = None) -> InboxMessage:
    """把一条外部来源消息转成材料包，返回 manual_upload 消息（幂等）。

    已有 converted_message 且该包仍存在 → 直接返回（重复点击不复制第二份字节）。
    没有附件 → 明确报 VALIDATION_ERROR，让前端提示「先下载附件再拆分」，
    而不是生成一个空材料包（空包在桌面上是纯噪音）。
    """
    if not msg.has_attachments or not msg.attachments_meta:
        raise ValidationException(
            "这条消息没有附件，无法转为材料包",
            code="NO_ATTACHMENTS",
            errors={"message": "没有可搬运的附件"},
        )
    if msg.source.source_type not in CONVERTIBLE_SOURCE_TYPES:
        raise ValidationException(
            "该来源的消息本身就是材料包，无需转换",
            code="ALREADY_MATERIAL_PACK",
            errors={"message": "manual_upload / client_upload 消息已是材料包"},
        )

    with transaction.atomic():
        # 行锁重取：并发两次「转材料包」若不加锁会各建一个包（幂等只在单线程成立）
        locked = InboxMessage.objects.select_for_update().select_related("source").get(pk=msg.pk)
        if locked.converted_message_id:
            existing = InboxMessage.objects.filter(pk=locked.converted_message_id).first()
            if existing is not None:
                logger.info("收件箱消息 %s 已转过材料包 %s，直接复用", locked.pk, existing.pk)
                return existing

        # 逐附件下载 → 落盘。单个附件失败不应让整次转换白忙：跳过并计数，
        # 全部失败才抛（现场常见：一张网历史附件已过期，重新下载会 404）。
        uploads: list[ContentFile] = []
        skipped: list[str] = []
        for att in locked.attachments_meta or []:
            part_index = int(att.get("part_index", -1))
            filename = str(att.get("custom_filename") or att.get("original_filename") or att.get("filename") or "")
            try:
                uploads.append(_download_source_attachment(locked, part_index, filename))
            except Exception as exc:
                logger.warning(
                    "转材料包跳过附件: message=%s part_index=%s error=%s",
                    locked.pk,
                    part_index,
                    exc,
                )
                skipped.append(filename or f"attachment_{part_index}")

        if not uploads:
            raise ValidationException(
                "附件全部取回失败，无法转为材料包",
                code="ATTACHMENTS_UNAVAILABLE",
                errors={"message": f"取回失败：{', '.join(skipped)}"},
            )

        manual = _create_manual_message_from_uploads(uploads, locked=locked, uploaded_by=uploaded_by)
        locked.converted_message = manual
        locked.save(update_fields=["converted_message"])
        logger.info(
            "收件箱消息 %s 转为材料包 %s（搬运 %d 份附件，跳过 %d 份）",
            locked.pk,
            manual.pk,
            len(uploads),
            len(skipped),
        )
        return manual


def _create_manual_message_from_uploads(
    uploads: list[ContentFile],
    *,
    locked: InboxMessage,
    uploaded_by: Any,
) -> InboxMessage:
    """在 manual_upload 来源下建消息（复用上传口的落盘协议与页数回填）。

    刻意不复用 create_manual_message：那条路径会先跑 validate_manual_upload_file
    的类型白名单并展开压缩包——转换的字节是**已入库的外部附件**，用户没有机会
    改格式，被白名单挡住只会让历史 .wps / .ofd 永久转不了。压缩包也不在此展开：
    展开会凭空多出文件，与「原样搬过去」的预期不符。
    """
    from apps.message_hub.services.attachment_page_service import fill_page_counts
    from apps.message_hub.services.manual_upload_service import get_or_create_manual_source

    source = get_or_create_manual_source()
    ts = timezone.localtime().strftime("%Y%m%d%H%M%S")
    from uuid import uuid4

    attachment_metas = save_upload_files_as_metas(
        uploads,
        rel_dir=f"message_hub/manual/{source.pk}/{ts}-conv{locked.pk}",
    )
    fill_page_counts(attachment_metas)
    # 标题沿用原消息主题（案号 + 文书名本身就带着拆分线索），空则兜底来源名
    subject = (locked.subject or "").strip() or f"{locked.source.display_name}材料"
    return InboxMessage.objects.create(
        source=source,
        message_id=f"manual-conv-{locked.pk}-{ts}-{uuid4().hex[:8]}",
        subject=subject[:512],
        sender=locked.sender,
        received_at=timezone.now(),
        body_text="",
        body_html="",
        has_attachments=bool(attachment_metas),
        attachments_meta=attachment_metas,
        draft_state={},
        uploaded_by=uploaded_by if getattr(uploaded_by, "is_authenticated", False) else None,
    )
