"""Agent 对话附件端点测试（上传 / 内容读取 / 归属校验 / 白名单）。

物理文件经 autouse fixture 落到临时 MEDIA_ROOT（与 image_rotation 单测同法）；
内容端点回 base64 供 mcp_server 转投解析，模型上下文只见文本。
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from apps.agent.models import AgentAttachment, AgentSession
from apps.organization.models import LawFirm, Lawyer

pytestmark = [pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _media_root(tmp_path: Any) -> Any:
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        yield


def _make_user(username: str) -> tuple[Any, Any]:
    firm = LawFirm.objects.create(name=f"律所-{username}")
    user = Lawyer.objects.create_user(username=username, password="x-test-12345678", law_firm=firm)
    client = Client()
    client.force_login(user)
    return user, client


def _make_session(user: Any) -> AgentSession:
    return AgentSession.objects.create(user=user, origin=AgentSession.Origin.CHAT)


def _upload(client: Any, session: AgentSession, name: str = "笔记.txt", content: bytes = b"hello") -> Any:
    f = SimpleUploadedFile(name, content, content_type="text/plain")
    return client.post(f"/api/v1/agent/sessions/{session.session_id}/attachments", {"file": f})


class TestUploadAttachment:
    def test_upload_returns_receipt_and_saves_file(self) -> None:
        user, client = _make_user("att-owner")
        session = _make_session(user)

        resp = _upload(client, session, "笔记.txt", "附件正文".encode())
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "笔记.txt"
        assert body["size"] > 0

        record = AgentAttachment.objects.get(attachment_id=body["attachment_id"])
        assert record.session_id == session.pk
        assert record.storage_path.startswith("agent_attachments/")
        assert record.storage_path.endswith(".txt")

    def test_upload_rejects_disallowed_extension(self) -> None:
        user, client = _make_user("att-bad")
        session = _make_session(user)
        resp = _upload(client, session, "恶意.exe", b"MZ")
        assert resp.status_code == 400

    def test_upload_unknown_session_404(self) -> None:
        _user, client = _make_user("att-nosession")
        f = SimpleUploadedFile("a.txt", b"x", content_type="text/plain")
        resp = client.post("/api/v1/agent/sessions/00000000-0000-0000-0000-000000000000/attachments", {"file": f})
        assert resp.status_code == 404

    def test_upload_other_users_session_404(self) -> None:
        owner, _ = _make_user("att-real-owner")
        session = _make_session(owner)
        _other, other_client = _make_user("att-attacker")
        resp = _upload(other_client, session)
        assert resp.status_code == 404


class TestAttachmentContent:
    def test_content_round_trip_base64(self) -> None:
        user, client = _make_user("att-read")
        session = _make_session(user)
        receipt = _upload(client, session, "笔记.txt", "轮到你了".encode()).json()

        resp = client.get(f"/api/v1/agent/attachments/{receipt['attachment_id']}/content")
        assert resp.status_code == 200
        body = resp.json()
        assert base64.b64decode(body["content_base64"]).decode() == "轮到你了"
        assert body["filename"] == "笔记.txt"

    def test_other_user_cannot_read_404(self) -> None:
        owner, owner_client = _make_user("att-read-owner")
        session = _make_session(owner)
        receipt = _upload(owner_client, session).json()

        _other, other_client = _make_user("att-read-other")
        resp = other_client.get(f"/api/v1/agent/attachments/{receipt['attachment_id']}/content")
        assert resp.status_code == 404

    def test_unknown_attachment_404(self) -> None:
        _user, client = _make_user("att-read-none")
        resp = client.get("/api/v1/agent/attachments/00000000-0000-0000-0000-000000000000/content")
        assert resp.status_code == 404
