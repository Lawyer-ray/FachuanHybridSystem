"""163 邮箱 IMAP 收取企业信用报告 PDF 附件。"""

from __future__ import annotations

import email
import imaplib
import logging
import ssl
from email.header import decode_header

logger = logging.getLogger("apps.automation")

EMAIL_CREDENTIAL_ID = 4  # AccountCredential pk for 163 邮箱


def _connect_163(user: str, password: str) -> imaplib.IMAP4_SSL:
    """连接 163 IMAP，发送 ID 命令绕过 Unsafe Login 限制。"""
    ctx = ssl.create_default_context()
    mail = imaplib.IMAP4_SSL("imap.163.com", 993, ssl_context=ctx)

    # 163 (Coremail) 要求 LOGIN 前发送 ID 命令，否则 SELECT 报 Unsafe Login
    imaplib.Commands["ID"] = ("NONAUTH",)
    tag = mail._new_tag()
    mail.send(tag + b' ID ("name" "IMAPClient" "version" "1.0.0")\r\n')
    mail.readline()

    mail.login(user, password)
    return mail


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    return "".join(
        part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part for part, enc in parts
    )


GSXT_REPORT_FOLDER = "&TwFOGk,hdShP4WBv-"  # 163 企业信用报告专用文件夹（modified UTF-7）


def _fetch_report_attachment(user: str, password: str, company_name: str) -> bytes | None:
    """
    从 163 企业信用报告文件夹中找含 company_name 的 PDF 附件，
    返回 bytes，未找到返回 None。
    """
    try:
        mail = _connect_163(user, password)
        ret, _ = mail.select(f'"{GSXT_REPORT_FOLDER}"')
        if ret != "OK":
            # 文件夹不存在，回退到 INBOX
            logger.warning("企业信用报告文件夹不存在，回退到 INBOX")
            mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        all_ids = data[0].split()
        if not all_ids:
            mail.logout()
            return None

        # 从最新的开始找，找到即返回
        for msg_id in reversed(all_ids):
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            if not isinstance(raw, bytes):
                continue
            msg = email.message_from_bytes(raw)

            for part in msg.walk():
                if part.get_content_disposition() != "attachment":
                    continue
                filename = _decode_header_value(part.get_filename())
                if filename.lower().endswith(".pdf") and company_name in filename:
                    payload = part.get_payload(decode=True)
                    if payload:
                        logger.info("找到报告附件: %s", filename)
                        mail.logout()
                        return payload

        mail.logout()
    except Exception:
        logger.exception("163 IMAP 收取报告失败")
    return None


class GsxtEmailService:
    """Class-based facade for GSXT email retrieval."""

    def fetch_report_attachment(self, user: str, password: str, company_name: str) -> bytes | None:
        return _fetch_report_attachment(user, password, company_name)
