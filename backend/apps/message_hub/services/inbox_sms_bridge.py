"""收件箱消息 → 法院短信处理流程（CourtSMS）的桥接。

**为什么需要它**：一张网 / IMAP 送来的文书消息本来就该进短信处理链（解析 →
匹配案件 → 重命名归档 → 通知）。历史上这条入口只有 admin 里的一个按钮，
逻辑内联在视图里，手动同步与定时同步拉到的消息只能靠人一条条点。

**为什么必须复制字节而不是引用路径**：``CourtSMS.document_file_paths`` 会被
``DocumentRenamer`` **原地改名**（重命名后回写引用）。若直接把
``attachments_meta[].local_path`` 交出去，收件箱里那条消息的附件会跟着失效
（预览/下载/转材料包全 404）。所以每个附件都先 ``download_attachment`` 取字节，
再用 ``save_uploaded_file`` 落到 ``MediaEntity.AUTOMATION_UPLOADS``，只保存副本路径。

**幂等三级**（命中即返回既有记录，``created=False``）：
1. ``CourtSMS.inbox_message_id`` —— 本消息已经进过流程（含并发兜底唯一约束）；
2. ``CourtSMS.delivery_event_id == msg.message_id`` —— 跨来源同一条送达只处理一次；
3. ``delivery_event_key`` 查重 —— 兼容历史 admin 桥 / 手工提交过的同内容记录。

**案号必须抽出来写进 ``case_numbers``**：``CaseMatcher`` 只在
``sms.case_numbers`` 非空时才做案号精确匹配，抽不到就退化成当事人匹配
（一张网消息的正文里往往只有法院与文书名，当事人匹配命中率低得多）。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ValidationException
from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import save_uploaded_file, to_media_abs
from apps.core.tasking import submit_task
from apps.message_hub.models import InboxMessage, MessageSource

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.message_hub")

#: 允许提交进短信流程的来源类型（材料包类来源本身就是终点，不再回灌）。
BRIDGE_SOURCE_TYPES: frozenset[str] = frozenset({"court_inbox", "court_schedule", "imap"})

#: 自动通道单轮最多提交多少条，避免一次同步把历史存量全灌进队列。
AUTO_SUBMIT_BATCH_LIMIT = 50

#: ``CourtSMS.delivery_event_id`` 的字段宽度（超长改存摘要，见 `_delivery_event_id`）。
DELIVERY_EVENT_ID_MAX_LENGTH = 128

#: 复制落盘的白名单扩展名与单文件上限（与 `CourtSMSDocumentIntakeService` 同口径）。
ATTACHMENT_ALLOWED_EXTENSIONS: list[str] = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".bmp"]
ATTACHMENT_MAX_SIZE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class BridgeResult:
    """一次提交的结果（``created=False`` 表示命中幂等，返回的是既有记录）。"""

    sms: CourtSMS
    created: bool
    attachment_count: int
    skipped: list[dict[str, str]]


def _bridge_error_types() -> tuple[type[BaseException], ...]:
    """取附件 / 建记录可能抛的异常族（**不放宽成 Exception**，见 CLAUDE.md 红线）。

    三类来源各有一套异常：本地读盘（``OSError`` / ``ValueError``）、IMAP
    （``imaplib.IMAP4.error``）、一张网插件（``httpx.HTTPError`` /
    ``RuntimeError``），叠加本层的 ``ValidationException`` 与库层
    ``DatabaseError``（唯一约束竞态）。按需拼装，缺哪个库就少一类——可选依赖
    缺失不该让模块导入失败。
    """
    from django.db import DatabaseError

    errors: tuple[type[BaseException], ...] = (ValidationException, ValueError, OSError, RuntimeError, DatabaseError)
    try:
        import imaplib

        errors += (imaplib.IMAP4.error,)
    except ImportError:  # pragma: no cover - 标准库恒在
        pass
    try:
        import httpx

        errors += (httpx.HTTPError,)
    except ImportError:  # pragma: no cover - httpx 是硬依赖，理论上进不来
        pass
    return errors


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _attachment_display_name(att: dict[str, Any], part_index: int) -> str:
    """附件的对外名字：用户改过的名字 > 原始文件名 > 存储名 > 兜底名。"""
    for key in ("custom_filename", "original_filename", "filename"):
        name = str(att.get(key) or "").strip()
        if name:
            return name
    return f"attachment_{part_index}"


def _build_content(msg: InboxMessage) -> str:
    """短信正文：来源 + 消息正文（正文为空退回收件主题）。

    ``content`` 是归档 markdown、admin 列表与全文检索的主信息源，不能只写来源。
    """
    body = msg.body_text or msg.subject or ""
    return f"[来自收件箱][{msg.source.display_name}]\n{body}"


def _build_legacy_admin_content(msg: InboxMessage) -> str:
    """升级前 Admin 按钮（``InboxMessageAdmin._submit_to_sms_view``）用的正文口径。

    历史记录只留下这个字符串算出来的 ``delivery_event_key``（既无 ``inbox_message_id``
    也无 ``delivery_event_id``）。不拿它再查一遍，升级后对同一条消息点「提交短信流程」
    会被当成新记录，重复归档并重复通知。
    """
    return f"[来自收件箱] {msg.subject or '(无主题)'}\n发件人: {msg.sender}\n消息ID: {msg.message_id}"


def _delivery_event_id(msg: InboxMessage) -> str | None:
    """跨来源去重键：优先用原始 ``message_id``，超长时退化成定长摘要。

    ``CourtSMS.delivery_event_id`` 只有 128 字符，而 ``InboxMessage.message_id``
    （IMAP 的 Message-ID）可以到 512。直接截断会让两条不同消息撞成同一个键、
    把真消息当成重复跳过——比报错更危险。所以超长就换成摘要：仍然一消息一键，
    不与其他消息相撞。

    **用 sha256 而不是 sha1**：CodeQL 的 ``py/weak-sensitive-data-hashing`` 把任何
    喂给 SHA1/MD5 的 id 判成 high severity（``Alerts gate`` 是 required check，
    阈值 0）。这里是去重键不是密码学用途、碰撞也不是攻击面，但换成 sha256 零成本，
    没有理由为它挂一条安全告警。
    """
    raw = (msg.message_id or "").strip()
    if not raw:
        return None
    if len(raw) <= DELIVERY_EVENT_ID_MAX_LENGTH:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"sha256:{digest}"


def _extract_case_numbers(msg: InboxMessage) -> list[str]:
    """从主题与正文抽案号（规范化后去重保序；抽不到返回空列表，不抛错）。"""
    from apps.automation.utils.text_utils import TextUtils

    numbers: list[str] = []
    for text in (msg.subject or "", msg.body_text or ""):
        for raw in TextUtils.extract_case_numbers(text):
            normalized = TextUtils.normalize_case_number(raw)
            if normalized and normalized not in numbers:
                numbers.append(normalized)
    return numbers


class InboxSmsBridgeService:
    """把一条收件箱消息提交进法院短信处理流程。"""

    def submit(self, msg: InboxMessage, *, trigger: str = "manual") -> BridgeResult:
        """提交一条消息，返回短信记录与本次是否新建。

        Args:
            msg: 待提交的收件箱消息（附件字节由来源 fetcher 取回）。
            trigger: 触发通道（``manual`` / ``auto``），只用于日志区分。

        Raises:
            ValidationException: 来源不支持（``SOURCE_NOT_SUPPORTED``）/ 无附件
                （``NO_ATTACHMENTS``）/ 附件全部取不到（``ATTACHMENTS_UNAVAILABLE``）。
        """
        source_type = msg.source.source_type
        if source_type not in BRIDGE_SOURCE_TYPES:
            raise ValidationException(
                "该来源的消息不能提交到短信流程",
                code="SOURCE_NOT_SUPPORTED",
                errors={"source_type": source_type},
            )

        attachments = [att for att in (msg.attachments_meta or []) if isinstance(att, dict)]
        if not msg.has_attachments or not attachments:
            raise ValidationException(
                "这条消息没有附件，无法提交到短信流程",
                code="NO_ATTACHMENTS",
                errors={"message": "没有可提交的附件"},
            )

        content = _build_content(msg)
        existing = self._find_existing(msg, content)
        if existing is not None:
            logger.info(
                "收件箱消息已在短信流程中，跳过重复提交: inbox_pk=%s trigger=%s sms_id=%s",
                msg.pk,
                trigger,
                existing.pk,
            )
            return BridgeResult(
                sms=existing,
                created=False,
                attachment_count=len(existing.document_file_paths or []),
                skipped=[],
            )

        abs_paths, skipped = self._copy_attachments(msg, attachments)
        if not abs_paths:
            raise ValidationException(
                "这条消息的附件都取不到，无法提交到短信流程",
                code="ATTACHMENTS_UNAVAILABLE",
                errors={"attachments": "、".join(f"{s['name']}({s['reason']})" for s in skipped)},
            )

        sms = self._create_sms(
            msg,
            content=content,
            abs_paths=abs_paths,
            case_numbers=_extract_case_numbers(msg),
        )
        submit_task(
            "apps.automation.workers.court_sms_tasks.process_sms_from_matching",
            sms.id,
            task_name=f"court_sms_from_inbox_{msg.pk}",
        )
        logger.info(
            "收件箱消息已提交短信流程: inbox_pk=%s trigger=%s sms_id=%s attachments=%d skipped=%d",
            msg.pk,
            trigger,
            sms.id,
            len(abs_paths),
            len(skipped),
        )
        return BridgeResult(sms=sms, created=True, attachment_count=len(abs_paths), skipped=skipped)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _find_existing(self, msg: InboxMessage, content: str) -> CourtSMS | None:
        """三级幂等查重：收件箱消息 ID → 来源消息 ID → 内容去重键（含历史 Admin 口径）。"""
        from apps.automation.models import CourtSMS
        from apps.automation.services.sms.court_sms_delivery_dedup import build_lookup_keys

        by_inbox = CourtSMS.objects.filter(inbox_message_id=msg.pk).first()
        if by_inbox is not None:
            return by_inbox

        event_id = _delivery_event_id(msg)
        if event_id is not None:
            by_delivery = CourtSMS.objects.filter(delivery_event_id=event_id).first()
            if by_delivery is not None:
                return by_delivery

        lookup_keys = [
            *build_lookup_keys(content, msg.received_at),
            *build_lookup_keys(_build_legacy_admin_content(msg), msg.received_at),
        ]
        return CourtSMS.objects.filter(delivery_event_key__in=lookup_keys).order_by("id").first()

    def _copy_attachments(
        self, msg: InboxMessage, attachments: list[dict[str, Any]]
    ) -> tuple[list[str], list[dict[str, str]]]:
        """逐个附件取字节并复制到 automation 上传目录。

        返回 ``(media 绝对路径列表, 跳过明细)``。单附件失败只记 skipped，
        全部失败由调用方转成 ``ATTACHMENTS_UNAVAILABLE``。
        """
        from apps.message_hub.services import get_fetcher

        fetcher = get_fetcher(msg.source.source_type)
        error_types = _bridge_error_types()
        abs_paths: list[str] = []
        skipped: list[dict[str, str]] = []

        for att in attachments:
            part_index = _safe_int(att.get("part_index", -1))
            display_name = _attachment_display_name(att, part_index)
            try:
                content, served_name, content_type = fetcher.download_attachment(msg.source, msg.message_id, part_index)
                uploaded = SimpleUploadedFile(
                    display_name or served_name,
                    content,
                    content_type=content_type or "application/octet-stream",
                )
                rel_path, _saved_name = save_uploaded_file(
                    uploaded_file=uploaded,
                    rel_dir=MediaEntity.AUTOMATION_UPLOADS,
                    allowed_extensions=ATTACHMENT_ALLOWED_EXTENSIONS,
                    max_size_bytes=ATTACHMENT_MAX_SIZE_BYTES,
                )
                abs_paths.append(str(to_media_abs(rel_path)))
            except error_types as exc:
                logger.warning(
                    "收件箱附件复制失败: inbox_pk=%s part_index=%s name=%s error=%s",
                    msg.pk,
                    part_index,
                    display_name,
                    exc,
                )
                skipped.append({"name": display_name, "reason": str(exc)})

        return abs_paths, skipped

    def _create_sms(
        self,
        msg: InboxMessage,
        *,
        content: str,
        abs_paths: list[str],
        case_numbers: list[str],
    ) -> CourtSMS:
        """建短信记录并进入匹配阶段（``delivery_event_id`` 复活为跨来源去重键）。"""
        from apps.automation.models import CourtSMS, CourtSMSStatus
        from apps.automation.services.sms.court_sms_delivery_dedup import build_delivery_event_key

        return CourtSMS.objects.create(
            content=content,
            received_at=msg.received_at,
            status=CourtSMSStatus.MATCHING,
            document_file_paths=abs_paths,
            case_numbers=case_numbers,
            delivery_event_id=_delivery_event_id(msg),
            inbox_message_id=msg.pk,
            delivery_event_key=build_delivery_event_key(content, msg.received_at),
        )


def auto_submit_for_source(source: MessageSource) -> dict[str, int]:
    """把一个来源新到的消息自动提交进短信流程（同步任务尾部调用）。

    ``auto_sms_since`` 为空即「不自动」，一次查询都不做。否则取该时刻之后、
    有附件、还没进过流程的消息，按收到时间升序最多 ``AUTO_SUBMIT_BATCH_LIMIT`` 条，
    逐条提交；单条失败只记 warning 计入 ``skipped``，不影响其余条与已提交的记录。
    """
    stats = {"examined": 0, "submitted": 0, "skipped": 0}
    if source.auto_sms_since is None:
        return stats

    from apps.automation.models import CourtSMS

    submitted_ids = CourtSMS.objects.filter(inbox_message_id__isnull=False).values("inbox_message_id")
    candidates = (
        InboxMessage.objects.filter(
            source=source,
            has_attachments=True,
            received_at__gte=source.auto_sms_since,
        )
        .exclude(pk__in=submitted_ids)
        .order_by("received_at")[:AUTO_SUBMIT_BATCH_LIMIT]
    )

    service = InboxSmsBridgeService()
    error_types = _bridge_error_types()
    for msg in candidates:
        stats["examined"] += 1
        try:
            service.submit(msg, trigger="auto")
        except error_types as exc:
            stats["skipped"] += 1
            logger.warning(
                "收件箱自动提交短信流程失败（已跳过）: source=%s inbox_pk=%s error=%s",
                source.display_name,
                msg.pk,
                exc,
            )
            continue
        stats["submitted"] += 1

    if stats["examined"]:
        logger.info("收件箱自动提交短信流程: source=%s %s", source.display_name, stats)
    return stats


__all__ = [
    "ATTACHMENT_ALLOWED_EXTENSIONS",
    "ATTACHMENT_MAX_SIZE_BYTES",
    "AUTO_SUBMIT_BATCH_LIMIT",
    "BRIDGE_SOURCE_TYPES",
    "BridgeResult",
    "InboxSmsBridgeService",
    "auto_submit_for_source",
]
