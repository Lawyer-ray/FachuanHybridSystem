"""收件箱缩略图端点的 HTTP 契约。

单元测试（``tests/ci/unit/message_hub/test_attachment_thumbnail.py``）只覆盖
「怎么渲、怎么缓存」；这里补三件只有走真实请求才能证明的事：

1. 响应头对：``image/jpeg`` + ``ETag`` + ``Cache-Control: private`` + ``nosniff``；
2. 条件请求真的省流量：带 ``If-None-Match`` 回 304 且**不带 body**；
3. 权限与拒单：别人的消息 404（不泄露存在性）、不支持的类型 400。

第 2 条尤其容易假绿——只断言「第一次 200」的话，把 304 分支写成 `return None`
也照样通过。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.message_hub.models import InboxMessage
from apps.message_hub.services.attachment_thumbnail_service import purge_message_thumbnails, thumbnail_dir
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.message_hub.services.manual_upload_service import create_manual_message
from apps.organization.models import Lawyer


def _pdf_bytes() -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 96), "民事起诉状")
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def media_root(tmp_path: Path, settings: object) -> Path:
    """附件与缩略图都落临时 MEDIA_ROOT（不碰工作库的 media/）。"""
    root = tmp_path / "media"
    root.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = str(root)  # type: ignore[attr-defined]
    return root


def _cleanup(message: InboxMessage) -> None:
    for att in message.attachments_meta or []:
        path = resolve_media_attachment_path(str(att.get("local_path", "")))
        if path is not None and path.exists():
            path.unlink()
    purge_message_thumbnails(message.pk)
    message.delete()


def _manual_message(user: Lawyer, filename: str, content: bytes) -> InboxMessage:
    """按真实客户端的做法带上正确的 Content-Type。

    ``SimpleUploadedFile`` 不给 content_type 时一律 ``text/plain``，而浏览器上传
    会按扩展名给真实类型（见前端 ``uploadPack`` 的 FormData）。这里不还原的话，
    「按 content_type 判定 PDF」这条路径永远测不到。
    """
    content_type = (
        "application/pdf"
        if filename.endswith(".pdf")
        else "image/png"
        if filename.endswith(".png")
        else "application/octet-stream"
    )
    return create_manual_message([SimpleUploadedFile(filename, content, content_type=content_type)], uploaded_by=user)


@pytest.mark.django_db
def test_list_payload_carries_attachment_meta(authenticated_client: object, law_firm: object, media_root: Path) -> None:
    """列表就得带附件元信息。

    收件箱要判断「这条要不要进材料预处理」，只看 ``attachment_count`` 等于让人
    逐条点开看（扫描件的主题常常就是 `Attached Image`）。这条断言就是那个
    能力的底线：字段一旦被谁从列表 schema 挪回详情，前端会静默退化成
    「只有份数、没有文件名」，而且没有任何报错。
    """
    user = Lawyer.objects.get(username="testuser")
    msg = _manual_message(user, "起诉状.pdf", _pdf_bytes())
    try:
        resp = authenticated_client.get("/api/v1/inbox/messages")  # type: ignore[attr-defined]
        assert resp.status_code == 200
        row = next(item for item in resp.json() if item["id"] == msg.pk)
        assert row["attachment_count"] == 1
        assert row["attachments"][0]["filename"] == "起诉状.pdf"
        assert row["attachments"][0]["content_type"] == "application/pdf"
        # 内部字段不能随列表泄漏（local_path 是服务器文件路径）
        assert "local_path" not in row["attachments"][0]
    finally:
        _cleanup(msg)


@pytest.mark.django_db
def test_thumbnail_returns_jpeg_with_cache_headers(
    authenticated_client: object, law_firm: object, media_root: Path
) -> None:
    user = Lawyer.objects.get(username="testuser")
    msg = _manual_message(user, "起诉状.pdf", _pdf_bytes())
    url = f"/api/v1/inbox/messages/{msg.pk}/attachments/0/thumbnail"
    try:
        resp = authenticated_client.get(url, {"width": 200})  # type: ignore[attr-defined]
        assert resp.status_code == 200
        assert resp["Content-Type"] == "image/jpeg"
        assert resp["X-Content-Type-Options"] == "nosniff"
        assert "private" in resp["Cache-Control"]
        etag = resp["ETag"]
        assert etag.startswith('"') and etag.endswith('"')
        # JPEG 魔数：确认发的是图，不是 SVG/HTML 之类能被浏览执行的载荷
        # （FileResponse 是流式的，没有 .content，只能读 streaming_content）
        body = b"".join(resp.streaming_content)
        assert body[:2] == b"\xff\xd8"

        # 条件请求：同一 ETag 回 304，且不重发字节
        again = authenticated_client.get(url, {"width": 200}, HTTP_IF_NONE_MATCH=etag)  # type: ignore[attr-defined]
        assert again.status_code == 304
        assert again.content == b""
    finally:
        _cleanup(msg)


@pytest.mark.django_db
def test_thumbnail_of_image_attachment(authenticated_client: object, law_firm: object, media_root: Path) -> None:
    user = Lawyer.objects.get(username="testuser")
    msg = _manual_message(user, "现场照片.png", _png_bytes())
    try:
        resp = authenticated_client.get(  # type: ignore[attr-defined]
            f"/api/v1/inbox/messages/{msg.pk}/attachments/0/thumbnail"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"] == "image/jpeg"
    finally:
        _cleanup(msg)


@pytest.mark.django_db
def test_thumbnail_rejects_unsupported_attachment(
    authenticated_client: object, law_firm: object, media_root: Path
) -> None:
    user = Lawyer.objects.get(username="testuser")
    msg = _manual_message(user, "判决书.docx", b"PK\x03\x04fake-docx")
    try:
        resp = authenticated_client.get(  # type: ignore[attr-defined]
            f"/api/v1/inbox/messages/{msg.pk}/attachments/0/thumbnail"
        )
        assert resp.status_code == 400
        body = resp.json()
        # 不是「随便 400」：要能按 code 区分「类型不支持」，前端据此提示而不是报错
        assert body["success"] is False
        assert body["code"] == "INBOX_NO_THUMBNAIL"
        assert "part_index" in (body["errors"] or {})
        # 且真的没落盘（这条同时证明「取字节之前就拒了」）
        assert not thumbnail_dir(msg.pk).exists()
    finally:
        _cleanup(msg)


@pytest.mark.django_db
def test_thumbnail_of_other_users_message_is_404(
    authenticated_client: object, law_firm: object, media_root: Path
) -> None:
    """可见性红线：别人上传的材料，缩略图也必须 404（不泄露存在性）。"""
    other = Lawyer.objects.create_user(
        username="other-lawyer",
        password="otherpass123",  # pragma: allowlist secret
        law_firm=Lawyer.objects.get(username="testuser").law_firm,
    )
    msg = _manual_message(other, "他人的证据.pdf", _pdf_bytes())
    try:
        # authenticated_client 的 testuser 是 superuser（可见一切），先降级再测
        boss = Lawyer.objects.get(username="testuser")
        boss.is_superuser = False
        boss.is_admin = False
        boss.save(update_fields=["is_superuser", "is_admin"])

        resp = authenticated_client.get(  # type: ignore[attr-defined]
            f"/api/v1/inbox/messages/{msg.pk}/attachments/0/thumbnail"
        )
        assert resp.status_code == 404
        # 不泄露存在性：连「这不是你的」都不说，统一按不存在处理
        assert "不存在" in resp.json()["message"]
        # 且任何人都没为它渲过图（404 发生在取字节与渲染之前）
        assert not thumbnail_dir(msg.pk).exists()
    finally:
        boss = Lawyer.objects.get(username="testuser")
        boss.is_superuser = True
        boss.is_admin = True
        boss.save(update_fields=["is_superuser", "is_admin"])
        _cleanup(msg)
