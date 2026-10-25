"""客户上传链接端到端 API 测试。

覆盖：律师创建/列表/作废/换发（JWT）→ 客户免登录取信息/上传/已传名录
（X-Upload-Token 头）→ 无效/过期/作废/超额 token 的关闭路径 →
上传产生的材料包按创建律师归属汇入材料预处理桌面（source_type 多值过滤）。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.message_hub.models import ClientUploadLink, InboxMessage, SourceType
from apps.message_hub.services.base import resolve_media_attachment_path
from apps.organization.models import LawFirm, Lawyer

pytestmark = pytest.mark.django_db

PUBLIC_INFO = "/api/v1/public/material-link"
PUBLIC_FILES = "/api/v1/public/material-link/files"


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    """限流计数走 Django cache：清缓存隔离用例，避免 429 串扰（仓库测试教训）。"""
    cache.clear()
    yield
    cache.clear()


def _make_lawyer(username: str, *, is_admin: bool = False, firm: LawFirm | None = None) -> Lawyer:
    if firm is None:
        firm = LawFirm.objects.create(name=f"律所-{username}")
    return Lawyer.objects.create_user(
        username=username,
        password="testpass123",  # pragma: allowlist secret
        is_admin=is_admin,
        law_firm=firm,
    )


def _create_link(client, **overrides) -> tuple[dict, str]:
    payload = {
        "title": "张三·买卖合同纠纷·证据材料",
        "note": "请上传合同原件与往来记录",
        "client_name": "张三",
        "expires_days": 30,
    }
    payload.update(overrides)
    resp = client.post(
        "/api/v1/inbox/upload-links",
        data=__import__("json").dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    token = body.pop("token")
    assert token  # 明文 token 只在创建响应出现
    return body, token


def _upload(token: str, client, files, remark: str = ""):
    return client.post(
        PUBLIC_FILES,
        data={"files": files, "remark": remark},
        headers={"X-Upload-Token": token},
    )


def _cleanup_files() -> None:
    for msg in InboxMessage.objects.filter(source__source_type=SourceType.CLIENT_UPLOAD):
        for att in msg.attachments_meta or []:
            path = resolve_media_attachment_path(str(att.get("local_path", "")))
            if path is not None and path.exists():
                path.unlink()
        msg.delete()


# ── 律师端 ──────────────────────────────────────────────────


def test_create_and_list_links(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    creator = Lawyer.objects.get(username="testuser")
    body, token = _create_link(authenticated_client, contract_id=None)

    assert body["title"] == "张三·买卖合同纠纷·证据材料"
    assert body["state"] == "open"
    assert body["status"] == "active"
    assert body["pack_count"] == 0
    assert body["used_bytes"] == 0
    assert body["contract_id"] is None

    listed = authenticated_client.get("/api/v1/inbox/upload-links").json()
    row = next(r for r in listed if r["id"] == body["id"])
    assert row["state"] == "open"
    assert "token" not in row  # 列表行不含 token 明文

    link = ClientUploadLink.objects.get(pk=body["id"])
    assert link.created_by == creator
    # 库里只有哈希，明文不可反推
    import hashlib

    assert link.token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_create_link_with_contract_binding(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.contracts.models import Contract

    contract = Contract.objects.create(name="2026 民五 HT-001 委托合同", case_type="civil")
    body, _token = _create_link(authenticated_client, contract_id=contract.pk)
    assert body["contract_id"] == contract.pk
    assert body["contract_name"] == "2026 民五 HT-001 委托合同"


def test_create_link_validates_input(authenticated_client, law_firm):
    resp = authenticated_client.post(
        "/api/v1/inbox/upload-links",
        data=__import__("json").dumps({"title": "  ", "expires_days": 30}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    resp = authenticated_client.post(
        "/api/v1/inbox/upload-links",
        data=__import__("json").dumps({"title": "x", "expires_days": 3}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_link_ownership_scoped_to_creator(db, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from django.test import Client

    firm = LawFirm.objects.create(name="归属律所")
    owner = _make_lawyer("link_owner", firm=firm)
    other = _make_lawyer("link_other", firm=firm)

    owner_client = Client()
    owner_client.force_login(owner)
    other_client = Client()
    other_client.force_login(other)

    body, _token = _create_link(owner_client)

    # 他人列表看不到、也操作不了（不存在与无权同形 404）
    listed = other_client.get("/api/v1/inbox/upload-links").json()
    assert all(r["id"] != body["id"] for r in listed)
    resp = other_client.post(f"/api/v1/inbox/upload-links/{body['id']}/revoke")
    assert resp.status_code == 404


def test_revoke_and_rotate(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    body, token = _create_link(authenticated_client)

    revoked = authenticated_client.post(f"/api/v1/inbox/upload-links/{body['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    # 已作废的链接仍能取到信息（客户页显示「已作废」），但状态不再是 open
    resp = authenticated_client.get(PUBLIC_INFO, headers={"X-Upload-Token": token})
    assert resp.status_code == 200
    assert resp.json()["state"] == "revoked"

    # 已作废链接不能 rotate（须重新创建）
    resp = authenticated_client.post(f"/api/v1/inbox/upload-links/{body['id']}/rotate")
    assert resp.status_code == 400


def test_rotate_invalidates_old_token(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    body, old_token = _create_link(authenticated_client)

    resp = authenticated_client.post(f"/api/v1/inbox/upload-links/{body['id']}/rotate")
    assert resp.status_code == 200
    new_token = resp.json()["token"]
    assert new_token and new_token != old_token

    old = authenticated_client.get(PUBLIC_INFO, headers={"X-Upload-Token": old_token})
    assert old.status_code == 404
    new = authenticated_client.get(PUBLIC_INFO, headers={"X-Upload-Token": new_token})
    assert new.status_code == 200


# ── 公开端点 ────────────────────────────────────────────────


def test_public_info_and_upload_flow(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    try:
        creator = Lawyer.objects.get(username="testuser")
        _body, token = _create_link(authenticated_client, contract_id=None)

        info = authenticated_client.get(PUBLIC_INFO, headers={"X-Upload-Token": token})
        assert info.status_code == 200
        payload = info.json()
        assert payload["state"] == "open"
        assert payload["title"] == "张三·买卖合同纠纷·证据材料"
        assert payload["contract_name"] == ""
        assert payload["remaining_bytes"] > 0

        f1 = SimpleUploadedFile("起诉状.pdf", b"%PDF-1.4 complaint", content_type="application/pdf")
        f2 = SimpleUploadedFile("微信记录.png", b"\x89PNG\r\n\x1a\nchat", content_type="image/png")
        up = _upload(token, authenticated_client, [f1, f2], remark="第一批材料")
        assert up.status_code == 201, up.content
        assert [f["filename"] for f in up.json()["files"]] == ["起诉状.pdf", "微信记录.png"]

        # 材料包归属创建律师、挂链接、来源 client_upload
        msg = InboxMessage.objects.get(source__source_type=SourceType.CLIENT_UPLOAD)
        assert msg.uploaded_by == creator
        assert msg.upload_link_id == _body["id"]
        assert msg.body_text == "第一批材料"
        assert msg.sender == "张三"

        # 已传名录（仅文件名+大小）
        listing = authenticated_client.get(PUBLIC_FILES, headers={"X-Upload-Token": token})
        assert listing.status_code == 200
        names = [f["filename"] for f in listing.json()]
        assert names == ["起诉状.pdf", "微信记录.png"]

        # 桌面列表：多值过滤收得到，单值 manual_upload 收不到
        both = authenticated_client.get("/api/v1/inbox/messages", {"source_type": "manual_upload,client_upload"}).json()
        assert msg.pk in [m["id"] for m in both]
        row = next(m for m in both if m["id"] == msg.pk)
        assert row["upload_link_id"] == _body["id"]
        assert row["upload_link_title"] == "张三·买卖合同纠纷·证据材料"

        only_manual = authenticated_client.get("/api/v1/inbox/messages", {"source_type": "manual_upload"}).json()
        assert msg.pk not in [m["id"] for m in only_manual]
    finally:
        _cleanup_files()


def test_invalid_token_uniform_404(authenticated_client, db):
    for bad in ("", "not-a-token", "x" * 64):
        resp = authenticated_client.get(PUBLIC_INFO, headers={"X-Upload-Token": bad})
        assert resp.status_code == 404
    resp = authenticated_client.get(PUBLIC_INFO)
    assert resp.status_code == 404


def test_expired_link_rejects_upload(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    body, token = _create_link(authenticated_client)
    ClientUploadLink.objects.filter(pk=body["id"]).update(expires_at=timezone.now() - timedelta(days=1))

    info = authenticated_client.get(PUBLIC_INFO, headers={"X-Upload-Token": token})
    assert info.status_code == 200
    assert info.json()["state"] == "expired"

    f = SimpleUploadedFile("过期.pdf", b"%PDF-1.4 expired", content_type="application/pdf")
    up = _upload(token, authenticated_client, [f])
    assert up.status_code == 403


def test_quota_exceeded_rejects_upload(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    try:
        body, token = _create_link(authenticated_client)
        # 配额压到 10 字节：上传必然超出
        ClientUploadLink.objects.filter(pk=body["id"]).update(quota_total_bytes=10)

        f = SimpleUploadedFile("大文件.pdf", b"%PDF-1.4 " + b"x" * 100, content_type="application/pdf")
        up = _upload(token, authenticated_client, [f])
        assert up.status_code == 400
        assert not InboxMessage.objects.filter(source__source_type=SourceType.CLIENT_UPLOAD).exists()
    finally:
        _cleanup_files()


def test_upload_rejects_disallowed_type(authenticated_client, law_firm, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    _body, token = _create_link(authenticated_client)
    f = SimpleUploadedFile("可疑脚本.exe", b"MZ...", content_type="application/octet-stream")
    up = _upload(token, authenticated_client, [f])
    assert up.status_code == 400
