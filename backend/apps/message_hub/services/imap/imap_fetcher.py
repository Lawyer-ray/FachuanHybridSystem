"""IMAP 邮箱增量拉取实现。"""

from __future__ import annotations

import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
from email.message import Message
from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.timezone import make_aware

from apps.message_hub.models import SyncStatus
from apps.message_hub.services.base import MessageFetcher

if TYPE_CHECKING:
    from apps.message_hub.models import MessageSource

logger = logging.getLogger("apps.message_hub")

IMAP_PORT = 993
BODY_TEXT_MAX = 2000  # 正文纯文本最大存储字符数


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _extract_body(msg: Message) -> tuple[str, str]:
    """提取纯文本和 HTML 正文。"""
    text, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not text:
                text = decoded[:BODY_TEXT_MAX]
            elif ct == "text/html" and not html:
                html = decoded
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html = decoded
            else:
                text = decoded[:BODY_TEXT_MAX]
    return text, html


def _extract_attachments(msg: Message) -> list[dict]:
    """提取附件元信息，不下载内容。"""
    attachments = []
    for idx, part in enumerate(msg.walk()):
        if part.get_content_disposition() != "attachment":
            continue
        filename = _decode_header_value(part.get_filename()) or f"attachment_{idx}"
        payload = part.get_payload(decode=False)
        size = len(payload) if isinstance(payload, (str, bytes)) else 0
        attachments.append(
            {
                "filename": filename,
                "content_type": part.get_content_type(),
                "size": size,
                "part_index": idx,
            }
        )
    return attachments


class ImapFetcher(MessageFetcher):
    def _connect(self, source: MessageSource) -> imaplib.IMAP4_SSL:
        import ssl

        cred = source.credential
        host = source.imap_host or _extract_imap_host(cred.url or cred.site_name)
        account = source.imap_account or cred.account
        ctx = ssl.create_default_context()
        m = imaplib.IMAP4_SSL(host, IMAP_PORT, ssl_context=ctx, timeout=30)
        m.login(account, cred.password)
        return m

    def fetch_new_messages(self, source: MessageSource) -> int:
        from apps.message_hub.models import InboxMessage

        try:
            m = self._connect(source)
        except Exception as e:
            _mark_failed(source, str(e))
            raise

        try:
            m.select("INBOX")
            # 构建搜索条件：SINCE 起始时间 + UID 大于上次同步
            since_str = source.sync_since.strftime("%d-%b-%Y")
            criteria = f"SINCE {since_str}"
            if source.last_synced_uid:
                criteria = f"UID {source.last_synced_uid + 1}:*"

            _, data = m.uid("search", None, criteria)  # type: ignore[arg-type]
            uid_list = data[0].split() if data[0] else []

            if not uid_list:
                _mark_success(source)
                return 0

            new_count = 0
            max_uid = source.last_synced_uid or 0

            for uid_bytes in uid_list:
                uid = int(uid_bytes)
                _, msg_data = m.uid("fetch", uid_bytes, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, bytes):
                    continue
                msg = email.message_from_bytes(raw)
                subject = _decode_header_value(msg.get("Subject"))
                sender = _decode_header_value(msg.get("From"))

                # 发件人过滤
                if not _sender_allowed(sender, source):
                    max_uid = max(max_uid, uid)
                    continue

                date_str = msg.get("Date", "")
                received_at = _parse_date(date_str) or timezone.now()
                body_text, body_html = _extract_body(msg)
                attachments = _extract_attachments(msg)

                _, created = InboxMessage.objects.get_or_create(
                    source=source,
                    message_id=str(uid),
                    defaults={
                        "subject": subject,
                        "sender": sender,
                        "received_at": received_at,
                        "body_text": body_text,
                        "body_html": body_html,
                        "has_attachments": bool(attachments),
                        "attachments_meta": attachments,
                    },
                )
                if created:
                    new_count += 1
                max_uid = max(max_uid, uid)

            source.last_synced_uid = max_uid
            _mark_success(source)
            return new_count

        finally:
            try:
                m.logout()
            except Exception:
                pass

    def download_attachment(self, source: MessageSource, message_id: str, part_index: int) -> tuple[bytes, str, str]:
        m = self._connect(source)
        try:
            m.select("INBOX")
            _, msg_data = m.uid("fetch", message_id.encode(), "(RFC822)")  # type: ignore[arg-type]
            raw = msg_data[0][1]
            if not isinstance(raw, bytes):
                raise ValueError("无法获取邮件内容")
            msg = email.message_from_bytes(raw)
            for idx, part in enumerate(msg.walk()):
                if idx == part_index and part.get_content_disposition() == "attachment":
                    payload = part.get_payload(decode=True)
                    if not isinstance(payload, bytes):
                        raise ValueError("附件内容为空")
                    filename = _decode_header_value(part.get_filename()) or f"attachment_{idx}"
                    return payload, filename, part.get_content_type() or "application/octet-stream"
            raise ValueError(f"未找到 part_index={part_index} 的附件")
        finally:
            try:
                m.logout()
            except Exception:
                pass


def _extract_imap_host(url_or_name: str) -> str:
    """从 URL 或站点名称中提取 IMAP 主机名。"""
    import re

    match = re.search(r"(?:https?://)?([^/]+)", url_or_name)
    return match.group(1) if match else url_or_name


def _parse_date(date_str: str) -> datetime | None:
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            return make_aware(dt)
        return dt
    except Exception:
        return None


def _mark_success(source: MessageSource) -> None:
    source.last_sync_at = timezone.now()
    source.last_sync_status = SyncStatus.SUCCESS
    source.last_sync_error = ""
    source.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_error", "last_synced_uid"])


def _mark_failed(source: MessageSource, error: str) -> None:
    source.last_sync_at = timezone.now()
    source.last_sync_status = SyncStatus.FAILED
    source.last_sync_error = error[:1000]
    source.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_error"])


def _parse_filter_lines(text: str) -> list[str]:
    """将多行文本解析为小写关键词列表，忽略空行。"""
    return [line.strip().lower() for line in text.splitlines() if line.strip()]


def _sender_allowed(sender: str, source: MessageSource) -> bool:
    """根据白名单/黑名单判断发件人是否允许同步。"""
    sender_lower = sender.lower()

    whitelist = _parse_filter_lines(source.sender_whitelist)
    if whitelist:
        return any(kw in sender_lower for kw in whitelist)

    blacklist = _parse_filter_lines(source.sender_blacklist)
    if blacklist:
        return not any(kw in sender_lower for kw in blacklist)

    return True
