"""手动上传收件箱能力测试：上传落盘、拆分草稿、按需下载、类型/大小校验。"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ValidationException
from apps.message_hub.models import InboxMessage, SourceType
from apps.message_hub.services import get_fetcher
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import (
    MANUAL_UPLOAD_MAX_SIZE_BYTES,
    create_manual_message,
    get_or_create_manual_source,
    save_draft,
)


def _cleanup(message: InboxMessage) -> None:
    for att in message.attachments_meta or []:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    message.delete()


@pytest.mark.django_db
def test_create_manual_message_lands_in_inbox() -> None:
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name="消息测试律所")
    lawyer = Lawyer.objects.create_user(username="uploader", real_name="上传律师", law_firm=firm)
    poa = SimpleUploadedFile("POA.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    id_image = SimpleUploadedFile("id_card.png", b"\x89PNG\r\n\x1a\nabc", content_type="image/png")

    msg = create_manual_message([poa, id_image], subject="张先生 民间借贷材料", uploaded_by=lawyer)

    assert msg.source.source_type == SourceType.MANUAL_UPLOAD
    assert msg.source.credential is None
    assert msg.uploaded_by_id == lawyer.pk
    assert msg.uploaded_by.real_name == "上传律师"
    assert msg.has_attachments is True
    assert len(msg.attachments_meta) == 2
    assert msg.subject == "张先生 民间借贷材料"
    # 附件已真实落盘
    for att in msg.attachments_meta:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        assert path is not None and path.exists(), att.get("local_path")
        assert att["local_path"].startswith("message_hub/manual/")
    _cleanup(msg)


@pytest.mark.django_db
def test_manual_fetcher_downloads_persisted_attachment() -> None:
    poa = SimpleUploadedFile("POA.pdf", b"%PDF-1.4 hello", content_type="application/pdf")
    msg = create_manual_message([poa])

    content, filename, content_type = get_fetcher(msg.source.source_type).download_attachment(
        msg.source, msg.message_id, 0
    )

    assert content == b"%PDF-1.4 hello"
    assert filename == "POA.pdf"
    assert content_type == "application/pdf"
    _cleanup(msg)


@pytest.mark.django_db
def test_draft_roundtrip() -> None:
    poa = SimpleUploadedFile("POA.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    msg = create_manual_message([poa])

    draft = {"attachment_part_0": {"pieces": [{"name": "借条", "pages": [1]}]}}
    save_draft(msg.pk, draft)

    msg.refresh_from_db()
    assert msg.draft_state == draft
    _cleanup(msg)


@pytest.mark.django_db
def test_download_manual_source_deduplicated() -> None:
    get_or_create_manual_source()
    get_or_create_manual_source()
    from apps.message_hub.models import MessageSource

    count = MessageSource.objects.filter(source_type=SourceType.MANUAL_UPLOAD).count()
    assert count == 1
    MessageSource.objects.filter(source_type=SourceType.MANUAL_UPLOAD).delete()


# ── 类型 / 大小校验（安全审计） ───────────────────────────────────────────────


@pytest.mark.django_db
def test_create_manual_message_rejects_html_attachment() -> None:
    evil = SimpleUploadedFile("payload.html", b"<html><script>alert(1)</script></html>", content_type="text/html")
    with pytest.raises(ValidationException, match="不支持的附件格式"):
        create_manual_message([evil])
    # 校验先于落盘：不产生半落盘附件 / 收件箱消息
    assert InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD).count() == 0


@pytest.mark.django_db
def test_create_manual_message_rejects_executable() -> None:
    exe = SimpleUploadedFile("tool.exe", b"MZfake", content_type="application/octet-stream")
    with pytest.raises(ValidationException, match="不支持的附件格式"):
        create_manual_message([exe])


@pytest.mark.django_db
def test_create_manual_message_rejects_oversized() -> None:
    big = SimpleUploadedFile("big.pdf", b"%PDF-1.4 tiny", content_type="application/pdf")
    big.size = MANUAL_UPLOAD_MAX_SIZE_BYTES + 1  # 伪造声明大小，避免真实构造 50MB 内容
    with pytest.raises(ValidationException, match="附件过大"):
        create_manual_message([big])


@pytest.mark.django_db
def test_create_manual_message_rejects_batch_with_any_bad_file() -> None:
    """整批校验：混入一个恶意文件的批次整体拒绝，合法文件也不落盘。"""
    ok = SimpleUploadedFile("ok.pdf", b"%PDF-1.4 ok", content_type="application/pdf")
    evil = SimpleUploadedFile("evil.html", b"<html/>", content_type="text/html")
    with pytest.raises(ValidationException):
        create_manual_message([ok, evil])
    assert InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD).count() == 0


@pytest.mark.django_db
def test_create_manual_message_accepts_zip_and_images() -> None:
    archive = SimpleUploadedFile("材料.zip", b"PK\x05\x06" + b"\x00" * 18, content_type="application/zip")
    image = SimpleUploadedFile("scan.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
    msg = create_manual_message([archive, image])
    try:
        assert len(msg.attachments_meta) == 2
    finally:
        _cleanup(msg)


@pytest.mark.django_db
def test_append_manual_attachments_rejects_bad_type() -> None:
    pdf = SimpleUploadedFile("POA.pdf", b"%PDF-1.4 base", content_type="application/pdf")
    msg = create_manual_message([pdf])
    try:
        before = len(msg.attachments_meta or [])
        evil = SimpleUploadedFile("evil.svg", b"<svg onload=alert(1)>", content_type="image/svg+xml")
        with pytest.raises(ValidationException, match="不支持的附件格式"):
            from apps.message_hub.services.manual_upload_service import append_manual_attachments

            append_manual_attachments(msg, [evil])
        msg.refresh_from_db()
        assert len(msg.attachments_meta or []) == before  # 追加被整体拒绝
    finally:
        _cleanup(msg)
