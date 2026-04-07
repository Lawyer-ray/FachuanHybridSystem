"""IMAP 邮箱增量拉取实现。"""

from __future__ import annotations

import email
import imaplib
import logging
import socket
from datetime import datetime
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def _build_local_attachment_path(source_id: int, message_id: str, part_index: int, filename: str) -> Path:
    from django.conf import settings

    safe_name = Path(filename).name or f"attachment_{part_index}"
    save_dir = Path(settings.MEDIA_ROOT) / "message_hub" / "imap" / str(source_id) / message_id
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir / f"{part_index}_{safe_name}"


def _extract_attachments(msg: Message, source_id: int, message_id: str) -> list[dict[str, Any]]:
    """提取附件元信息，并将附件持久化到本地。"""
    attachments: list[dict[str, Any]] = []
    for idx, part in enumerate(msg.walk()):
        if part.get_content_disposition() != "attachment":
            continue

        filename = _decode_header_value(part.get_filename()) or f"attachment_{idx}"
        payload = part.get_payload(decode=True)
        content = payload if isinstance(payload, bytes) else b""
        local_path = _build_local_attachment_path(source_id, message_id, idx, filename)
        local_path.write_bytes(content)

        attachments.append(
            {
                "filename": filename,
                "original_filename": filename,
                "content_type": part.get_content_type(),
                "size": len(content),
                "part_index": idx,
                "local_path": str(local_path),
            }
        )
    return attachments


class ImapFetcher(MessageFetcher):
    def _connect(self, source: MessageSource) -> imaplib.IMAP4_SSL:
        import ssl

        cred = source.credential
        account = source.imap_account or cred.account
        hosts = _build_imap_host_candidates(source.imap_host, cred.url or cred.site_name)
        if not hosts:
            raise ValueError("IMAP 主机配置无效: (空)")

        ctx = ssl.create_default_context()
        errors: list[tuple[str, Exception]] = []

        for host in hosts:
            if not _looks_like_valid_host(host):
                continue
            try:
                m = imaplib.IMAP4_SSL(host, IMAP_PORT, ssl_context=ctx, timeout=30)
                m.login(account, cred.password)
                if host != hosts[0]:
                    logger.info("IMAP 自动回退主机成功: %s -> %s", hosts[0], host)
                return m
            except socket.gaierror as e:
                errors.append((host, e))
                continue
            except TimeoutError as e:
                errors.append((host, e))
                continue
            except OSError as e:
                errors.append((host, e))
                continue
            except imaplib.IMAP4.error as e:
                raise ValueError(f"IMAP 登录失败（账号或密码错误）: {e}") from e

        if errors:
            tried = ", ".join(host for host, _ in errors)
            if all(isinstance(err, socket.gaierror) for _, err in errors):
                raise ConnectionError(f"IMAP 主机无法解析（已尝试: {tried}）") from errors[-1][1]
            raise ConnectionError(f"IMAP 连接失败（已尝试: {tried}）: {errors[-1][1]}") from errors[-1][1]

        raise ValueError("IMAP 主机配置无效，未找到可用候选主机")

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
                attachments = _extract_attachments(msg, source.pk, str(uid))

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
        from apps.message_hub.models import InboxMessage

        inbox_msg = InboxMessage.objects.filter(source=source, message_id=message_id).only("attachments_meta").first()
        if inbox_msg and isinstance(inbox_msg.attachments_meta, list):
            for att in inbox_msg.attachments_meta:
                if int(att.get("part_index", -1)) != part_index:
                    continue
                local_path = str(att.get("local_path", "")).strip()
                if local_path and Path(local_path).exists():
                    content = Path(local_path).read_bytes()
                    filename = str(att.get("filename") or att.get("original_filename") or f"attachment_{part_index}")
                    content_type = str(att.get("content_type") or "application/octet-stream")
                    return content, filename, content_type

        m = self._connect(source)
        try:
            m.select("INBOX")
            _, msg_data = m.uid("fetch", message_id.encode(), "(RFC822)")  # type: ignore[arg-type]
            raw = msg_data[0][1]
            if not isinstance(raw, bytes):
                raise ValueError("无法获取邮件内容")

            msg = email.message_from_bytes(raw)
            for idx, part in enumerate(msg.walk()):
                if idx != part_index or part.get_content_disposition() != "attachment":
                    continue

                payload = part.get_payload(decode=True)
                if not isinstance(payload, bytes):
                    raise ValueError("附件内容为空")

                filename = _decode_header_value(part.get_filename()) or f"attachment_{idx}"
                file_path = _build_local_attachment_path(source.pk, message_id, idx, filename)
                file_path.write_bytes(payload)

                if inbox_msg and isinstance(inbox_msg.attachments_meta, list):
                    updated = False
                    for att in inbox_msg.attachments_meta:
                        if int(att.get("part_index", -1)) != idx:
                            continue
                        att["local_path"] = str(file_path)
                        att["size"] = len(payload)
                        updated = True
                        break
                    if updated:
                        inbox_msg.save(update_fields=["attachments_meta"])

                return payload, filename, part.get_content_type() or "application/octet-stream"

            raise ValueError(f"未找到 part_index={part_index} 的附件")
        finally:
            try:
                m.logout()
            except Exception:
                pass


def _extract_imap_host(url_or_name: str) -> str:
    """从 URL 或站点名称中提取 IMAP 主机名。"""
    from urllib.parse import urlparse

    raw = url_or_name.strip()
    if not raw:
        return ""

    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname
    if host:
        return host.strip().lower()

    fallback = parsed.path.split("/", 1)[0].strip().lower()
    return fallback


def _build_imap_host_candidates(config_host: str, url_or_name: str) -> list[str]:
    """构建 IMAP 主机候选列表（按优先级）。"""
    explicit = _extract_imap_host(config_host)
    inferred = _extract_imap_host(url_or_name)

    candidates: list[str] = []

    def _add(value: str) -> None:
        host = value.strip().lower()
        if host and host not in candidates and _looks_like_valid_host(host):
            candidates.append(host)

    _add(explicit)
    _add(inferred)

    seed = explicit or inferred
    if seed:
        base = seed
        if seed.startswith("mail."):
            _add(f"imap.{seed[5:]}")
            base = seed[5:]
        elif seed.startswith("imap."):
            _add(f"mail.{seed[5:]}")
            base = seed[5:]
        else:
            _add(f"imap.{seed}")
            _add(f"mail.{seed}")

        if base:
            _add(base)

    return candidates


def _looks_like_valid_host(host: str) -> bool:
    """基础 IMAP 主机名校验。"""
    candidate = host.strip().lower()
    if not candidate:
        return False
    if "://" in candidate or "/" in candidate or " " in candidate:
        return False
    if candidate.startswith(".") or candidate.endswith("."):
        return False
    return True


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
