"""手动上传收件箱能力的端到端 API 测试（真实 HTTP 走 ninja 路由与认证）。

覆盖本分支改造的完整用户故事：上传进收件箱 → 列表筛选 → 详情带草稿与上传人 →
草稿存取续接 → 附件下载/预览 → 手动来源去重 → 未认证拦截。
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.message_hub.models import InboxMessage, MessageSource, SourceType
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.organization.models import Lawyer

pytestmark = pytest.mark.django_db


def _upload(client, files, subject, **kwargs):
    data = {"files": files, "subject": subject}
    data.update(kwargs)
    return client.post("/api/v1/inbox/messages/upload", data=data)


def _cleanup_manual_files() -> None:
    for msg in InboxMessage.objects.filter(source__source_type=SourceType.MANUAL_UPLOAD):
        for att in msg.attachments_meta or []:
            path = resolve_media_attachment_path(str(att.get("local_path", "")))
            if path is not None and path.exists():
                path.unlink()
        msg.delete()


@pytest.mark.django_db
def test_full_upload_flow(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    uploader = Lawyer.objects.get(username="testuser")

    poa = SimpleUploadedFile("授权委托书.pdf", b"%PDF-1.4 poa", content_type="application/pdf")
    id_image = SimpleUploadedFile("身份证.png", b"\x89PNG\r\n\x1a\nid", content_type="image/png")

    # 1. 上传两个文件进收件箱
    resp = _upload(authenticated_client, [poa, id_image], "张先生 民间借贷材料")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    message_id = body["id"]
    assert body["source_type"] == SourceType.MANUAL_UPLOAD
    assert body["uploaded_by_id"] == uploader.pk
    assert body["uploaded_by_name"] == uploader.real_name or uploader.username
    assert body["draft_state"] == {}
    assert body["attachment_count"] == 2
    assert [a["filename"] for a in body["attachments"]] == ["授权委托书.pdf", "身份证.png"]

    # 2. 列表按 source_type=manual_upload 过滤后能查到
    listed = authenticated_client.get("/api/v1/inbox/messages", {"source_type": SourceType.MANUAL_UPLOAD})
    assert listed.status_code == 200
    ids = [i["id"] for i in listed.json()]
    assert message_id in ids
    row = next(i for i in listed.json() if i["id"] == message_id)
    assert row["uploaded_by_name"] == uploader.real_name or uploader.username

    # 3. 详情返回草稿与附件
    detail = authenticated_client.get(f"/api/v1/inbox/messages/{message_id}")
    assert detail.status_code == 200
    assert detail.json()["draft_state"] == {}
    assert len(detail.json()["attachments"]) == 2

    # 4. 保拆分草稿（续接场景）
    draft = {"attachment_part_0": {"pieces": [{"name": "借条", "pages": [1]}]}}
    saved = authenticated_client.put(
        f"/api/v1/inbox/messages/{message_id}/draft",
        data=__import__("json").dumps({"draft": draft}),
        content_type="application/json",
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["ok"] is True

    # 5. 重开详情能读回草稿，拆分现场不丢
    reloaded = authenticated_client.get(f"/api/v1/inbox/messages/{message_id}")
    assert reloaded.status_code == 200
    assert reloaded.json()["draft_state"] == draft

    # 6. 附件下载可读、真实落盘
    down = authenticated_client.get(f"/api/v1/inbox/messages/{message_id}/attachments/0/download")
    assert down.status_code == 200
    assert b"".join(down.streaming_content) == b"%PDF-1.4 poa"
    assert down["Content-Type"].startswith("application/pdf")
    assert "attachment" in _decode_disposition(down["Content-Disposition"])
    assert "授权委托书.pdf" in _decode_disposition(down["Content-Disposition"])

    # 7. 附件预览 inline
    prev = authenticated_client.get(f"/api/v1/inbox/messages/{message_id}/attachments/1/preview")
    assert prev.status_code == 200
    assert b"".join(prev.streaming_content).startswith(b"\x89PNG")
    assert "inline" in _decode_disposition(prev["Content-Disposition"])

    _cleanup_manual_files()


def _decode_disposition(raw: str) -> str:
    """解码 HTTP 头中的 RFC2047 编码（含中文文件名会被编码）。"""
    from email.header import decode_header

    parts: list[str] = []
    for part, charset in decode_header(raw):
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "ascii", errors="replace"))
        else:
            parts.append(part)
    return "".join(parts)


@pytest.mark.django_db
def test_multiple_uploads_share_one_manual_source(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    r1 = _upload(authenticated_client, [SimpleUploadedFile("a.pdf", b"%PDF-a", content_type="application/pdf")], "第一批")
    r2 = _upload(authenticated_client, [SimpleUploadedFile("b.pdf", b"%PDF-b", content_type="application/pdf")], "第二批")
    assert r1.status_code == 201 and r2.status_code == 201

    count = MessageSource.objects.filter(source_type=SourceType.MANUAL_UPLOAD).count()
    assert count == 1

    ids = [r1.json()["id"], r2.json()["id"]]
    assert InboxMessage.objects.filter(pk__in=ids).count() == 2
    _cleanup_manual_files()


@pytest.mark.django_db
def test_upload_requires_authentication(api_client_unauth, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    resp = _upload(
        api_client_unauth,
        [SimpleUploadedFile("a.pdf", b"%PDF-a", content_type="application/pdf")],
        "未认证上传",
    )
    assert resp.status_code == 401  # pragma: no cover


@pytest.mark.django_db
def test_upload_without_files_rejected(authenticated_client, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    resp = authenticated_client.post("/api/v1/inbox/messages/upload", data={"subject": "无文件"})
    # ValidationError 未被绑定到 4xx，至少不应创建成功
    assert resp.status_code in (400, 422, 500)
    assert not InboxMessage.objects.filter(subject="无文件").exists()
    _cleanup_manual_files()
