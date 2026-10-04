"""收件箱附件下载/预览安全测试。

覆盖 ``apps/message_hub/api/inbox_api.py::_serve_attachment``：

1. inline 预览的 Content-Type 白名单：邮件自报 text/html、image/svg+xml 的
   附件按 inline 请求时，强制 ``application/octet-stream`` + 附件下载
   （防存储型 XSS），PDF / 位图图片保持 inline；
2. Content-Disposition filename 的 RFC 5987 转义：文件名含引号 / 中文时
   百分号编码，不破坏响应头。
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.message_hub.api.inbox_api import _serve_attachment
from apps.message_hub.models import InboxMessage
from apps.message_hub.services import get_fetcher
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import create_manual_message


def _cleanup(message: InboxMessage) -> None:
    for att in message.attachments_meta or []:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    message.delete()


def _make_message_with_attachment(content_type: str, *, filename: str = "att.html") -> InboxMessage:
    """落盘一个真实附件的 manual 消息，然后把 meta 里的 content_type 改成指定值。

    手动上传白名单本身不允许 html（见 manual_upload_service 校验），此处直接
    篡改 meta 模拟「IMAP 拉取的外部邮件自报 text/html」的场景。
    """
    ext = ".pdf" if filename.lower().endswith(".pdf") else ".png"
    real_name = f"att{ext}"
    uploaded = SimpleUploadedFile(real_name, b"%PDF-1.4 payload" if ext == ".pdf" else b"\x89PNGpayload")
    msg = create_manual_message([uploaded])
    metas = list(msg.attachments_meta or [])
    for att in metas:
        if att.get("filename") == real_name:
            att["content_type"] = content_type
            att["filename"] = filename
            att["original_filename"] = filename
            att["custom_filename"] = ""
    msg.attachments_meta = metas
    msg.save(update_fields=["attachments_meta"])
    return msg


class TestInlinePreviewWhitelist:
    @pytest.mark.django_db
    def test_html_attachment_preview_forced_to_download(self) -> None:
        msg = _make_message_with_attachment("text/html")
        try:
            resp = _serve_attachment(msg, 0, inline=True)
            assert resp.status_code == 200
            assert resp.headers["Content-Type"].split(";")[0] == "application/octet-stream"
            assert resp.headers["Content-Disposition"].startswith("attachment")
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_svg_attachment_preview_forced_to_download(self) -> None:
        msg = _make_message_with_attachment("image/svg+xml", filename="att.svg")
        try:
            resp = _serve_attachment(msg, 0, inline=True)
            assert resp.headers["Content-Type"].split(";")[0] == "application/octet-stream"
            assert resp.headers["Content-Disposition"].startswith("attachment")
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_pdf_attachment_preview_stays_inline(self) -> None:
        msg = _make_message_with_attachment("application/pdf", filename="att.pdf")
        try:
            resp = _serve_attachment(msg, 0, inline=True)
            assert resp.headers["Content-Type"].split(";")[0] == "application/pdf"
            assert resp.headers["Content-Disposition"].startswith("inline")
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_jpeg_attachment_preview_stays_inline(self) -> None:
        msg = _make_message_with_attachment("image/jpeg", filename="att.jpg")
        try:
            resp = _serve_attachment(msg, 0, inline=True)
            assert resp.headers["Content-Type"].split(";")[0] == "image/jpeg"
            assert resp.headers["Content-Disposition"].startswith("inline")
        finally:
            _cleanup(msg)


class TestContentDispositionEscaping:
    @pytest.mark.django_db
    def test_download_with_quoted_filename_is_escaped(self) -> None:
        """文件名含引号 / 中文：RFC 5987 百分号编码，不产生裸引号破坏响应头。"""
        msg = _make_message_with_attachment("application/pdf", filename='坏"quote".pdf')
        try:
            metas = list(msg.attachments_meta or [])
            metas[0]["custom_filename"] = '材料"1".pdf'
            msg.attachments_meta = metas
            msg.save(update_fields=["attachments_meta"])

            resp = _serve_attachment(msg, 0, inline=False)
            disposition = resp.headers["Content-Disposition"]
            assert disposition.startswith("attachment")
            assert 'filename="' in disposition
            # 文件名整体百分号编码：整个头只剩 filename="..." 的两个定界引号，
            # 文件名内部的引号被编码为 %22，不会截断/破坏 quoted-string
            assert disposition.count('"') == 2
            assert "%22" in disposition
            # RFC 5987 形态（浏览器优先解码）
            assert "filename*=UTF-8''" in disposition
        finally:
            _cleanup(msg)

    @pytest.mark.django_db
    def test_preview_chinese_filename_escaped(self) -> None:
        msg = _make_message_with_attachment("application/pdf", filename="合同.pdf")
        try:
            metas = list(msg.attachments_meta or [])
            metas[0]["custom_filename"] = "委托合同.pdf"
            msg.attachments_meta = metas
            msg.save(update_fields=["attachments_meta"])

            resp = _serve_attachment(msg, 0, inline=True)
            disposition = resp.headers["Content-Disposition"]
            assert disposition.startswith("inline")
            # 中文整体百分号编码进 filename*=，ASCII 段同样安全
            ascii_name = disposition.split('filename="', 1)[1].split('"', 1)[0]
            assert ascii_name == ascii_name.encode("ascii", errors="strict").decode()
        finally:
            _cleanup(msg)


class TestFetcherStillServesBytes:
    @pytest.mark.django_db
    def test_manual_fetcher_roundtrip(self) -> None:
        msg = _make_message_with_attachment("application/pdf", filename="att.pdf")
        try:
            content, filename, content_type = get_fetcher(msg.source.source_type).download_attachment(
                msg.source, msg.message_id, 0
            )
            assert content == b"%PDF-1.4 payload"
            assert filename == "att.pdf"
            assert content_type == "application/pdf"
        finally:
            _cleanup(msg)
