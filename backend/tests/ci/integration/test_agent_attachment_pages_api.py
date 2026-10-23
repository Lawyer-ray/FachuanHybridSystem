"""Agent 附件分页渲染端点测试（/agent/attachments/{id}/pages）。

覆盖：正常取页、越权/不存在→404、非法参数→400、dpi 与 max_pages 钳制生效、
渲染错误码以 200 + error 返回（不变成 500）。

渲染实现依赖 T1（``apps/agent/services/attachment_render.py``）。T1 未落盘时
整个模块 skip 并注明依赖；端点本身仍真实实现（模块级 ImportError 已由
agent_api 兜住，故会话/附件端点不受影响）。

fixture 用 pymupdf 现场生成小 PDF：真文件 → 真渲染，不 mock 渲染层。
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

#: 渲染服务是 T1 的产物；未落盘时跳过本文件的集成断言（不伪造通过数）
pytest.importorskip(
    "apps.agent.services.attachment_render",
    reason="依赖 T1：apps/agent/services/attachment_render.py（render_attachment_pages）尚未落盘",
)


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


#: 每页写入的正文。必须超过 T1 的文字层阈值（MIN_TEXT_CHARS=50），否则
#: 该页会被判为扫描页而走渲染——测试想验的是「有文字层」那一条分支。
_PAGE_TEXT = "This is a text-layer page for the attachment render contract test."


def _make_pdf(page_count: int) -> bytes:
    """现场生成带文字层的小 PDF（无外部依赖文件，CI 可复现）。"""
    pymupdf = pytest.importorskip("pymupdf", reason="分页渲染依赖 PyMuPDF")
    doc = pymupdf.open()
    for index in range(page_count):
        page = doc.new_page(width=595, height=842)  # A4 @72dpi
        page.insert_text((72, 72), _PAGE_TEXT, fontsize=10)
        page.insert_text((72, 120), f"page {index + 1}", fontsize=20)
    payload = doc.tobytes()
    doc.close()
    return payload


def _make_scanned_pdf() -> bytes:
    """生成**无文字层**的 PDF（模拟扫描件）：只有矢量黑块，get_text() 为空。"""
    pymupdf = pytest.importorskip("pymupdf", reason="分页渲染依赖 PyMuPDF")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for row in range(20):
        page.draw_rect(pymupdf.Rect(72, 72 + row * 12, 520, 80 + row * 12), color=(0, 0, 0), fill=(0, 0, 0))
    payload = doc.tobytes()
    doc.close()
    return payload


def _make_encrypted_pdf() -> bytes:
    """生成需要口令才能打开的 PDF（渲染须报 encrypted，而不是空白图）。"""
    pymupdf = pytest.importorskip("pymupdf", reason="分页渲染依赖 PyMuPDF")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), _PAGE_TEXT, fontsize=10)
    payload = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="user-secret")
    doc.close()
    return payload


def _upload_attachment(user: Any, client: Any, filename: str, content: bytes, mime: str) -> str:
    """经上传端点落一份附件，返回 attachment_id（走真实上传链路）。"""
    session = AgentSession.objects.create(user=user, origin=AgentSession.Origin.CHAT)
    upload = SimpleUploadedFile(filename, content, content_type=mime)
    resp = client.post(f"/api/v1/agent/sessions/{session.session_id}/attachments", {"file": upload})
    assert resp.status_code == 200, resp.content
    return str(resp.json()["attachment_id"])


def _make_attachment(user: Any, client: Any, page_count: int = 3) -> str:
    return _upload_attachment(user, client, "材料.pdf", _make_pdf(page_count), "application/pdf")


def _pages_url(attachment_id: str, **query: Any) -> str:
    base = f"/api/v1/agent/attachments/{attachment_id}/pages"
    if not query:
        return base
    pairs = "&".join(f"{key}={value}" for key, value in query.items())
    return f"{base}?{pairs}"


class TestRenderPages:
    def test_renders_requested_range(self) -> None:
        """有文字层的页走 text 策略：端点回页码与 has_text_layer，不渲染图（省视觉 token）。"""
        user, client = _make_user("pages-ok")
        attachment_id = _make_attachment(user, client, page_count=3)

        resp = client.get(_pages_url(attachment_id, pages="1-2", dpi=150, format="png"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["attachment_id"] == attachment_id
        assert body["filename"] == "材料.pdf"
        assert body["mime"] == "application/pdf"
        assert body["total_pages"] == 3
        assert body["error"] == ""
        assert body["strategy"] == "text"
        assert [page["page"] for page in body["pages_returned"]] == [1, 2]

        first = body["pages_returned"][0]
        # 有文字层：调用方据此走文本通道，不要求页图字节
        assert first["has_text_layer"] is True
        assert first["error"] == ""

    def test_scanned_page_renders_real_image(self) -> None:
        """无文字层的页必须渲染成真图：base64 可解出 PNG/JPEG 魔数，不是空串占位。"""
        user, client = _make_user("pages-scan")
        attachment_id = _upload_attachment(user, client, "扫描件.pdf", _make_scanned_pdf(), "application/pdf")

        body = client.get(_pages_url(attachment_id, pages="1", dpi=150, format="png")).json()
        assert body["error"] == ""
        assert body["strategy"] == "image"
        page = body["pages_returned"][0]
        assert page["has_text_layer"] is False
        assert page["mime"] == "image/png"
        assert page["width"] > 0 and page["height"] > 0
        raw = base64.b64decode(page["b64"])
        assert raw.startswith(b"\x89PNG\r\n\x1a\n"), "必须是真图，不能是空 base64"
        assert page["bytes"] == len(raw)

    def test_single_page_and_all(self) -> None:
        user, client = _make_user("pages-all")
        attachment_id = _make_attachment(user, client, page_count=3)

        single = client.get(_pages_url(attachment_id, pages="2")).json()
        assert [page["page"] for page in single["pages_returned"]] == [2]

        every = client.get(_pages_url(attachment_id, pages="all", max_pages=10)).json()
        assert [page["page"] for page in every["pages_returned"]] == [1, 2, 3]
        assert every["truncated_pages"] is False

    def test_jpeg_format_honoured(self) -> None:
        user, client = _make_user("pages-jpeg")
        attachment_id = _upload_attachment(user, client, "扫描件.pdf", _make_scanned_pdf(), "application/pdf")

        body = client.get(_pages_url(attachment_id, pages="1", format="jpeg")).json()
        assert body["error"] == ""
        page = body["pages_returned"][0]
        assert page["mime"] == "image/jpeg"
        raw = base64.b64decode(page["b64"])
        assert raw.startswith(b"\xff\xd8\xff")  # JPEG SOI


class TestPagesAccessControl:
    def test_other_user_gets_404(self) -> None:
        owner, owner_client = _make_user("pages-owner")
        attachment_id = _make_attachment(owner, owner_client, page_count=1)

        _other, other_client = _make_user("pages-attacker")
        resp = other_client.get(_pages_url(attachment_id, pages="1"))
        assert resp.status_code == 404
        # 与「不存在」同文案：不向试探者泄露 attachment_id 是否存在
        assert resp.json()["message"] == "附件不存在"

    def test_unknown_attachment_gets_404(self) -> None:
        _user, client = _make_user("pages-missing")
        resp = client.get(_pages_url("00000000-0000-0000-0000-000000000000", pages="1"))
        assert resp.status_code == 404
        assert resp.json()["message"] == "附件不存在"

    def test_anonymous_rejected(self) -> None:
        _user, client = _make_user("pages-anon")
        attachment_id = _make_attachment(_user, client, page_count=1)

        anon = Client()
        resp = anon.get(_pages_url(attachment_id, pages="1"))
        assert resp.status_code in (401, 403)
        # 未认证：不泄露附件存在性，也不产生任何副作用
        assert attachment_id.encode() not in resp.content
        assert AgentAttachment.objects.count() == 1

    def test_superuser_does_not_bypass_ownership(self) -> None:
        """超管同样 fail-closed（get_attachment_for_user 的既有口径，本端点不放宽）。"""
        owner, owner_client = _make_user("pages-super-owner")
        attachment_id = _make_attachment(owner, owner_client, page_count=1)

        firm = LawFirm.objects.create(name="律所-super")
        superuser = Lawyer.objects.create_superuser(username="pages-super", password="x-test-12345678", law_firm=firm)
        super_client = Client()
        super_client.force_login(superuser)

        resp = super_client.get(_pages_url(attachment_id, pages="1"))
        assert resp.status_code == 404
        assert AgentAttachment.objects.count() == 1


class TestPagesInvalidParameters:
    @pytest.mark.parametrize("bad_pages", ["abc", "0x3", "1-", "-2", "1--3", "3,,4x"])
    def test_unsyntactic_pages_400(self, bad_pages: str) -> None:
        """语法不成立 → 400（不能折成 page_out_of_range 的 200，那会误导调用方）。"""
        user, client = _make_user(f"pages-bad-{abs(hash(bad_pages))}")
        attachment_id = _make_attachment(user, client, page_count=3)

        resp = client.get(_pages_url(attachment_id, pages=bad_pages))
        assert resp.status_code == 400, resp.content
        assert resp.json()["message"], "400 必须带可读原因（MCP 侧要转给模型）"

    @pytest.mark.parametrize("bad_pages", ["3-1", "0", "99"])
    def test_out_of_range_reported_as_error_code(self, bad_pages: str) -> None:
        """语法成立但页号不成立 → page_out_of_range（200 + error，不 500）。"""
        user, client = _make_user(f"pages-oor-{abs(hash(bad_pages))}")
        attachment_id = _make_attachment(user, client, page_count=3)

        resp = client.get(_pages_url(attachment_id, pages=bad_pages))
        assert resp.status_code == 200, "越界必须以错误码返回，不能 5xx"
        body = resp.json()
        assert body["error"] == "page_out_of_range"
        assert body["pages_returned"] == []
        assert body["detail"], "错误码必须配可读原因（MCP 侧转给模型看）"

    def test_non_numeric_dpi_400(self) -> None:
        user, client = _make_user("pages-dpi-bad")
        attachment_id = _make_attachment(user, client, page_count=1)
        resp = client.get(_pages_url(attachment_id, pages="1", dpi="high"))
        assert resp.status_code == 400
        assert resp.json()["message"], "400 必须带可读原因"

    def test_unsupported_format_400(self) -> None:
        user, client = _make_user("pages-fmt-bad")
        attachment_id = _make_attachment(user, client, page_count=1)
        resp = client.get(_pages_url(attachment_id, pages="1", format="gif"))
        assert resp.status_code == 400
        assert "png" in resp.json()["message"]


class TestPagesClamping:
    def test_dpi_clamped_to_max(self) -> None:
        """dpi=600 被压到 300：像素尺寸须落在 300dpi 的量级，而不是 600dpi。"""
        user, client = _make_user("pages-dpi-high")
        attachment_id = _upload_attachment(user, client, "扫描件.pdf", _make_scanned_pdf(), "application/pdf")

        clamped = client.get(_pages_url(attachment_id, pages="1", dpi=600)).json()
        baseline = client.get(_pages_url(attachment_id, pages="1", dpi=300)).json()

        page_clamped = clamped["pages_returned"][0]
        page_base = baseline["pages_returned"][0]
        assert clamped["error"] == ""
        assert (page_clamped["width"], page_clamped["height"]) == (page_base["width"], page_base["height"])
        # A4 宽 595pt @300dpi ≈ 2479px；若没钳住会接近 5000px
        assert page_clamped["width"] < 3000

    def test_dpi_clamped_to_min(self) -> None:
        user, client = _make_user("pages-dpi-low")
        attachment_id = _upload_attachment(user, client, "扫描件.pdf", _make_scanned_pdf(), "application/pdf")

        clamped = client.get(_pages_url(attachment_id, pages="1", dpi=1)).json()
        baseline = client.get(_pages_url(attachment_id, pages="1", dpi=72)).json()

        page_clamped = clamped["pages_returned"][0]
        page_base = baseline["pages_returned"][0]
        assert (page_clamped["width"], page_clamped["height"]) == (page_base["width"], page_base["height"])

    def test_max_pages_truncates_and_notifies(self) -> None:
        """要 3 页但 max_pages=2：只给 2 页，且必须告知被截断（不静默少给）。"""
        user, client = _make_user("pages-trunc")
        attachment_id = _make_attachment(user, client, page_count=3)

        body = client.get(_pages_url(attachment_id, pages="1-3", max_pages=2)).json()
        assert body["error"] == ""
        assert [page["page"] for page in body["pages_returned"]] == [1, 2]
        assert body["truncated_pages"] is True
        assert body["notices"], "截断必须有 notices，禁止静默少给页"

    def test_max_pages_hard_capped_at_ten(self) -> None:
        """max_pages=50 被硬上限 10 压住（不能靠参数绕过上下文保护）。"""
        user, client = _make_user("pages-cap")
        attachment_id = _make_attachment(user, client, page_count=12)

        body = client.get(_pages_url(attachment_id, pages="all", max_pages=50)).json()
        assert body["total_pages"] == 12
        assert len(body["pages_returned"]) <= 10
        assert body["truncated_pages"] is True


class TestPagesRenderErrors:
    def test_non_pdf_attachment_reports_unsupported_mime(self) -> None:
        """非 PDF 附件（txt）→ unsupported_mime 错误码，页图列表为空，不伪造空白图。"""
        user, client = _make_user("pages-txt")
        attachment_id = _upload_attachment(user, client, "笔记.txt", "纯文本".encode(), "text/plain")

        resp = client.get(_pages_url(attachment_id, pages="1"))
        assert resp.status_code == 200, "格式不支持必须以错误码返回，不能 5xx"
        body = resp.json()
        assert body["error"] == "unsupported_mime"
        assert body["pages_returned"] == []

    def test_encrypted_pdf_reports_encrypted(self) -> None:
        """加密 PDF → error=="encrypted"，不返回空白图冒充成功。"""
        user, client = _make_user("pages-enc")
        attachment_id = _upload_attachment(user, client, "加密.pdf", _make_encrypted_pdf(), "application/pdf")

        resp = client.get(_pages_url(attachment_id, pages="1"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["error"] == "encrypted"
        assert "口令" in body["detail"]
        # 不返回图字节（空 base64 冒充成功是被明令禁止的）
        assert all(page["b64"] == "" and page["bytes"] == 0 for page in body["pages_returned"])
        assert all(page["error"] == "encrypted" for page in body["pages_returned"])
