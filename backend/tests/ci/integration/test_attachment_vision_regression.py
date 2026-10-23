"""附件视觉链路回归保护（验收 3/4/5/6/7）—— 全部走真实 HTTP 端点。

## 这份测试守的是什么

2026 年的 ``chars:0`` 故障由三层断点叠加造成，任何一层复发都会让「附件显示
已发送、模型什么也没看到」。本文件按层各守一条，不重复 T1/T2/T4 的单元测试：

- **第 1 层（验收 7，回归最贵的一条）**：带文字层的 PDF/docx/txt 必须走**文本**
  路径，``pages_returned`` 里 **image 块数必须为 0**。
  只断言「文本还在」不够——真正的退化形态恰恰是「文本还在，但每页白烧一张
  1568px 的图」。故这里查的是 ``GET /pages`` 返回的页图条数，而不是文本是否非空。
- **第 2 层（验收 3）**：100 页 PDF 只请求第 7 页 → 只回 1 页、字节在限额内。
  这条防的是「按页取」退化成「整份渲染」。
- **第 3 层（验收 6）**：8000px 宽 PNG → 长边缩到 ≤1568px，且**非白像素 >1%**。
  后者专防「渲染失败但仍然回一张全白图冒充成功」这一最隐蔽的失败形态。
- **验收 5**：他人 attachment_id → **404**（与 /content 同口径，服务端不区分
  「不存在」与「不属于你」，防校验式枚举）。**严禁为通过而放宽权限检查。**
- **验收 4**：真加密 PDF → ``error="encrypted"``，不是 ``content=""``。

## 为什么一律打 HTTP 而不是直接调 service

直接调 ``render_attachment_pages`` 会绕过端点契约。本次真实发生的 T1→T4 契约
漂移（``agent_api.py`` 从 ``attachment_render`` import 了不存在的
``render_attachment_pages`` → 503）正是「跳过端点就测不出来」的典型。所以：

- 端点未修好时，相关用例**必须 FAIL，不许 skip/绕过**，断言消息里写明修法；
- 只有渲染依赖（PyMuPDF / Pillow）缺失才 skip——那是环境缺件，不是代码缺陷。

## 依赖与隔离

物理文件与页图缓存都经 ``override_settings(MEDIA_ROOT=tmp_path)`` 落到临时目录：
``attachment_render.cache_root()`` 在**调用时**读 ``settings.MEDIA_ROOT``，故缓存
同样被隔离，用例之间不会命中彼此的旧图（脏命中会让验收 6 读到上一次的缩放结果）。
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
from typing import Any
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from apps.agent.models import AgentAttachment, AgentSession
from apps.organization.models import LawFirm, Lawyer

pytestmark = [pytest.mark.django_db]

logger = logging.getLogger(__name__)

pymupdf = pytest.importorskip("pymupdf", reason="附件渲染依赖 PyMuPDF")
PIL_Image = pytest.importorskip("PIL.Image", reason="尺寸缩放校验依赖 Pillow")

#: 页图长边上限（与 apps/agent/services/attachment_render.MAX_EDGE_PX 同口径）
MAX_EDGE_PX = 1568
#: 单页字节上限（与 attachment_render.MAX_PAGE_BYTES 同口径，1.5MB）
MAX_PAGE_BYTES = 1536 * 1024
#: 估算视觉 token 用的切块边长（主流多模态模型按 28×28 像素切 patch）
PATCH_PX = 28

#: 端点契约断点时的统一修法提示（T1→T4 漂移，真实发生过）
_ENDPOINT_FIX_HINT = (
    "T4 端点契约待修：agent_api.py 应 `from ..services.attachments import render_attachment_pages`，"
    "并以 attachment 对象 + format=fmt 调用（当前 import 自 attachment_render 的符号不存在 → 503）"
)


@pytest.fixture(autouse=True)
def _media_root(tmp_path: Any) -> Any:
    """附件物理文件与页图缓存都落临时 MEDIA_ROOT（详见模块 docstring）。"""
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        yield


def _make_user(username: str) -> tuple[Any, Client]:
    firm = LawFirm.objects.create(name=f"律所-{username}")
    user = Lawyer.objects.create_user(username=username, password="x-test-12345678", law_firm=firm)
    client = Client()
    client.force_login(user)
    return user, client


def _text_pdf(page_count: int) -> bytes:
    """生成**真有文字层**的 PDF（每页 82 字符 > MIN_TEXT_CHARS=50）。

    这里必须用 ASCII 正文：``china-s`` 字体在本机 PyMuPDF 下会把中文丢字
    （实测 100 字中文只提取出 46 字），一旦低于 50 字符阈值，T1 会把页面正确
    判定为「扫描页」并渲染成图——那是产品行为正确、而是 fixture 造错了对象。
    用 ASCII 正文才能稳定验证「有文字层 → 零页图」这条回归。
    页面用最小尺寸：只为造壳，不需要排版好看。
    """
    body = (
        "This contract is entered into by and between Party A and Party B for the purpose of "
        "governing the rights and obligations of both parties in the performance of this agreement."
    )
    doc = pymupdf.open()
    try:
        for index in range(page_count):
            page = doc.new_page(width=300, height=300)
            page.insert_text((10, 40), f"Page {index + 1}. {body}", fontsize=8)
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _scan_pdf(page_count: int) -> bytes:
    """生成**无文字层**的 PDF（纯图像页），用于模拟扫描件。

    每页画一个黑矩形 — 没有任何可提取文字，页面渲染出来是非空白图。
    """
    doc = pymupdf.open()
    try:
        for _ in range(page_count):
            page = doc.new_page(width=200, height=200)
            page.draw_rect(pymupdf.Rect(20, 20, 180, 120), color=None, fill=(0.1, 0.1, 0.1))
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _encrypted_pdf() -> bytes:
    """真 AES-256 加密 PDF（打开口令必填，空口令过不了）。"""
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.insert_text((10, 30), "机密正文", fontname="china-s", fontsize=10)
        return bytes(
            doc.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner-pw",
                user_pw="user-pw",
            )
        )
    finally:
        doc.close()


def _wide_png(width: int = 8000, height: int = 1200) -> bytes:
    """生成超宽 PNG：左半黑右半白条纹，缩放后仍应保留大量非白像素。"""
    image = PIL_Image.new("RGB", (width, height), (255, 255, 255))
    pixels = image.load()
    assert pixels is not None
    for y in range(0, height, 4):
        for x in range(width // 2):
            pixels[x, y] = (0, 0, 0)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _upload(client: Client, user: Any, name: str, content: bytes, mime: str) -> str:
    """经真实上传端点落一份附件，返回 attachment_id。"""
    session = AgentSession.objects.create(user=user, origin=AgentSession.Origin.CHAT)
    upload = SimpleUploadedFile(name, content, content_type=mime)
    resp = client.post(f"/api/v1/agent/sessions/{session.session_id}/attachments", {"file": upload})
    assert resp.status_code == 200, f"附件上传失败：{resp.status_code} {resp.content!r}"
    return str(resp.json()["attachment_id"])


def _pages(client: Client, attachment_id: str, **query: Any) -> dict[str, Any]:
    """调 ``GET /agent/attachments/{id}/pages``，返回 JSON。

    端点若返回非 200（含本次要防的 503），断言失败并附修法提示——端点契约
    问题必须在 CI 里红，不能靠 skip 掩盖。
    """
    url = f"/api/v1/agent/attachments/{attachment_id}/pages"
    if query:
        url = f"{url}?{'&'.join(f'{k}={v}' for k, v in query.items())}"
    resp = client.get(url)
    assert resp.status_code == 200, (
        f"/pages 应返回 200，实际 {resp.status_code}：{resp.content[:300]!r}。{_ENDPOINT_FIX_HINT}"
    )
    return dict(resp.json())


def _page_images(body: dict[str, Any]) -> list[dict[str, Any]]:
    """取回「真的带图字节」的页（空 b64 不算图块，它代表该页失败）。"""
    return [page for page in body.get("pages_returned") or [] if page.get("b64")]


def _decode_png(page: dict[str, Any]) -> Any:
    raw = base64.b64decode(page["b64"])
    return PIL_Image.open(io.BytesIO(raw))


def _non_white_ratio(image: Any) -> float:
    """非白像素占比（RGB 三通道都 ≥250 才算白）。

    逐像素扫描代价与图尺寸成正比，这里隔行隔列抽样 1/4——判定阈值是 1%，
    抽样误差远小于阈值，没必要为此逐像素走一遍 1568px 的图。
    """
    rgb = image.convert("RGB")
    pixels = rgb.load()
    assert pixels is not None
    xs = range(0, rgb.width, 2)
    ys = range(0, rgb.height, 2)
    sampled = 0
    non_white = 0
    for y in ys:
        for x in xs:
            sampled += 1
            red, green, blue = pixels[x, y][:3]
            if red < 250 or green < 250 or blue < 250:
                non_white += 1
    return non_white / sampled if sampled else 0.0


def _estimate_vision_tokens(width: int, height: int) -> int:
    """按 28×28 patch 估算视觉 token：ceil(w/28) * ceil(h/28) + 1（图像起始 token）。"""
    return math.ceil(width / PATCH_PX) * math.ceil(height / PATCH_PX) + 1


# ── 验收 7：文本路径不退化（image 块数必须为 0）──────────────────────────────


class TestTextPathDoesNotDegrade:
    """带文字层的文档**不得**产生任何页图。

    这是本文件最重要的一组：退化形态是「文本还在，但顺带渲染了 3 页大图」，
    每轮对话白烧数千视觉 token 且拖慢响应，只看「文本非空」永远发现不了。
    """

    def test_pdf_with_text_layer_returns_zero_page_images(self) -> None:
        user, client = _make_user("vision-text-pdf")
        attachment_id = _upload(client, user, "合同.pdf", _text_pdf(3), "application/pdf")

        body = _pages(client, attachment_id, pages="all", dpi=150, image_format="png")

        assert body["error"] == "", f"带文字层 PDF 走页图端点不该报错，实际 error={body['error']!r}"
        assert body["total_pages"] == 3
        # 关键断言：一张图都不许有
        assert _page_images(body) == [], (
            "带文字层 PDF 退化成渲染页图：文本路径本该零图，"
            f"实际拿到 {len(_page_images(body))} 张（strategy={body['strategy']!r}）"
        )
        assert sum(page["bytes"] for page in body["pages_returned"]) == 0, "文本路径不得产生任何图片字节"
        # 策略必须是纯文本，且每页都自报有文字层（调用方据此走文本而非 OCR）
        assert body["strategy"] == "text", f"带文字层 PDF 的 strategy 应为 text，实际 {body['strategy']!r}"
        assert body["pages_returned"], "文本路径也应给回每页的文本形态"
        assert all(page["has_text_layer"] for page in body["pages_returned"]), "带文字层的页 has_text_layer 必须为 True"

    def test_txt_attachment_never_renders_images(self) -> None:
        """txt 走纯文本链路，页图端点对它是 unsupported_mime，绝不能凭空造图。"""
        user, client = _make_user("vision-text-txt")
        attachment_id = _upload(client, user, "笔记.txt", "第一条笔记\n第二条".encode(), "text/plain")

        body = _pages(client, attachment_id, pages="1")

        assert _page_images(body) == [], "txt 附件不得返回任何页图"
        assert body["error"] == "unsupported_mime", (
            f"txt 没有页图形态，error 应为 unsupported_mime，实际 {body['error']!r}"
        )

    def test_docx_attachment_never_renders_images(self) -> None:
        """docx 同理：正文由文本解析端点负责，页图端点必须明确拒绝而不是给空白图。"""
        user, client = _make_user("vision-text-docx")
        attachment_id = _upload(
            client,
            user,
            "起诉状.docx",
            _minimal_docx("原告某某，被告某某。"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        body = _pages(client, attachment_id, pages="1")

        assert _page_images(body) == [], "docx 附件不得返回任何页图"
        assert body["error"] == "unsupported_mime", (
            f"docx 没有页图形态，error 应为 unsupported_mime，实际 {body['error']!r}"
        )


def _minimal_docx(text: str) -> bytes:
    """造一个最小合法 docx（zip + 两段 XML），只为走真实上传的 MIME 校验。"""
    import zipfile

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)
    return buf.getvalue()


# ── 验收 3：大文件按页取（100 页 PDF 只取第 7 页）───────────────────────────


class TestLargePdfPageTargeting:
    """100 页只取第 7 页 → 只回 1 页，且字节在单页限额内。

    防「按页取」退化成「整份渲染」：那会让一次工具调用返回 100 张图。
    """

    def test_hundred_page_pdf_single_page_request(self, capsys: Any) -> None:
        user, client = _make_user("vision-large-pdf")
        # 100 页、每页 82 字符文字层：这是「大文件按页取」的真实场景
        attachment_id = _upload(client, user, "卷宗.pdf", _text_pdf(100), "application/pdf")

        body = _pages(client, attachment_id, pages="7", dpi=150, image_format="png", max_pages=10)

        assert body["error"] == "", f"只取第 7 页不该报错，实际 {body['error']!r}"
        assert body["total_pages"] == 100, f"总页数应为 100，实际 {body['total_pages']}"
        returned = body["pages_returned"]
        assert len(returned) == 1, f"请求 1 页却返回 {len(returned)} 页：{[p['page'] for p in returned]}"
        assert returned[0]["page"] == 7, f"应只回第 7 页，实际 {returned[0]['page']}"
        assert body["truncated_pages"] in (False, 0), "只请求 1 页不应有截断"

        images = _page_images(body)
        total_bytes = sum(page["bytes"] for page in images)
        assert total_bytes <= MAX_PAGE_BYTES, f"页图合计 {total_bytes}B 超过单页 {MAX_PAGE_BYTES}B 上限"

        width = returned[0]["width"] or 0
        height = returned[0]["height"] or 0
        estimated = _estimate_vision_tokens(width, height) if images else 0

        # 实测数值（不是估算的「通过率」）：报告里要能直接引用
        logger.info(
            f"\n[验收3 实测] 总页数={body['total_pages']} 请求页=[7] "
            f"返回页数={len(returned)} 页面图字节={total_bytes}B "
            f"尺寸={width}x{height} 估算图像 token={estimated} strategy={body['strategy']!r}"
        )

        # 第 7 页有文字层 → 文本路径，零图、零字节、零视觉 token
        assert images == [], "有文字层的第 7 页应走文本路径，不该回页图"
        assert returned[0]["has_text_layer"] is True

    def test_hundred_page_scan_pdf_single_page_request_respects_byte_limit(self, capsys: Any) -> None:
        """100 页**扫描件**（无文字层）只取第 7 页：仍只回 1 页，且字节在限额内。

        有文字层时走文本路径，字节上限根本没被校验到；只有扫描页才真正
        验证「一张图也不会超 1.5MB、只要了一页就只给一页」。
        """
        user, client = _make_user("vision-large-scan")
        attachment_id = _upload(client, user, "扫描卷宗.pdf", _scan_pdf(100), "application/pdf")

        body = _pages(client, attachment_id, pages="7", dpi=150, image_format="png", max_pages=10)

        assert body["error"] == "", f"只取第 7 页不该报错，实际 {body['error']!r}"
        assert body["total_pages"] == 100
        returned = body["pages_returned"]
        assert len(returned) == 1, f"请求 1 页却返回 {len(returned)} 页"
        assert returned[0]["page"] == 7

        images = _page_images(body)
        assert len(images) == 1, "扫描页应回 1 张页图"
        assert images[0]["bytes"] <= MAX_PAGE_BYTES, f"页图 {images[0]['bytes']}B 超过 {MAX_PAGE_BYTES}B 上限"
        assert max(images[0]["width"], images[0]["height"]) <= MAX_EDGE_PX, "页图长边超过 1568px"

        logger.info(
            f"\n[验收3 实测·扫描页] 总页数={body['total_pages']} 请求页=[7] 返回页数={len(returned)} "
            f"页面图字节={images[0]['bytes']}B 尺寸={images[0]['width']}x{images[0]['height']} "
            f"估算图像 token={_estimate_vision_tokens(images[0]['width'], images[0]['height'])} "
            f"strategy={body['strategy']!r}"
        )


# ── 验收 6：超大图缩放（8000px → 长边 ≤1568，且非全白）──────────────────────


class TestOversizedImageDownscale:
    """8000px 宽 PNG 必须缩到长边 ≤1568，且不是空白图。

    「非白像素 >1%」是防「渲染失败仍回全白图冒充成功」的关键断言：
    空白图在字节数、尺寸、HTTP 200 上全部看起来正常，只有数像素才能识破。
    """

    def test_wide_png_downscaled_and_not_blank(self, capsys: Any) -> None:
        user, client = _make_user("vision-wide-png")
        source = _wide_png(8000, 1200)
        attachment_id = _upload(client, user, "扫描件.png", source, "image/png")

        body = _pages(client, attachment_id, pages="1", image_format="png")

        assert body["error"] == "", f"大图缩放不该报错，实际 {body['error']!r}"
        images = _page_images(body)
        assert len(images) == 1, f"图片附件应回 1 页，实际 {len(images)} 页"
        page = images[0]

        assert max(page["width"], page["height"]) <= MAX_EDGE_PX, (
            f"渲染后长边 {max(page['width'], page['height'])}px 超过 {MAX_EDGE_PX}px 上限"
        )
        assert page["bytes"] <= MAX_PAGE_BYTES, f"图片 {page['bytes']}B 超过 {MAX_PAGE_BYTES}B 上限"

        image = _decode_png(page)
        ratio = _non_white_ratio(image)
        assert ratio > 0.01, (
            f"渲染结果疑似空白图：非白像素占比 {ratio:.4%} ≤ 1%，这通常是「渲染失败却当成功返回」的形态"
        )

        logger.info(
            f"\n[验收6 实测] 原图=8000x1200({len(source)}B) "
            f"渲染后={page['width']}x{page['height']}({page['bytes']}B) "
            f"非白像素占比={ratio:.2%} 估算图像 token={_estimate_vision_tokens(page['width'], page['height'])}"
        )


# ── 验收 5：越权（他人 attachment_id → 404）─────────────────────────────────


class TestCrossUserAccess:
    """他人 attachment_id → 404，与 /content 同口径（不区分不存在，防枚举）。

    **权限检查不得为通过测试而放宽**：这里断言的是「拿不到任何内容」，
    而不是「返回某个特定错误文案」。
    """

    def test_other_users_attachment_is_404_on_pages(self) -> None:
        owner, owner_client = _make_user("vision-owner")
        attachment_id = _upload(owner_client, owner, "机密.pdf", _text_pdf(2), "application/pdf")

        _other, other_client = _make_user("vision-attacker")
        resp = other_client.get(f"/api/v1/agent/attachments/{attachment_id}/pages?pages=1")

        assert resp.status_code == 404, f"越权读他人附件应 404，实际 {resp.status_code}：{resp.content[:200]!r}"
        body = resp.json()
        # 不泄露附件存在性/归属：文案与「附件不存在」一致
        assert body.get("message") == "附件不存在", f"越权不应泄露归属信息，实际 {body!r}"
        # 且没把任何页图塞进错误响应
        assert "pages_returned" not in body

    def test_unknown_attachment_is_same_404(self) -> None:
        """不存在的 id 与越权同码同文案——否则可据差异枚举 attachment_id。"""
        _user, client = _make_user("vision-unknown")
        resp = client.get("/api/v1/agent/attachments/00000000-0000-0000-0000-000000000000/pages?pages=1")
        assert resp.status_code == 404
        assert resp.json().get("message") == "附件不存在"

    def test_superuser_does_not_bypass_ownership(self) -> None:
        """超管同样 fail-closed（get_attachment_for_user 不认 is_superuser）。"""
        owner, owner_client = _make_user("vision-su-owner")
        attachment_id = _upload(owner_client, owner, "机密.pdf", _text_pdf(1), "application/pdf")

        admin = Lawyer.objects.create_superuser(
            username="vision-su",
            password="x-test-12345678",  # pragma: allowlist secret（测试夹具占位密码）
            law_firm=LawFirm.objects.create(name="律所-su"),
        )
        admin_client = Client()
        admin_client.force_login(admin)
        resp = admin_client.get(f"/api/v1/agent/attachments/{attachment_id}/pages?pages=1")
        assert resp.status_code == 404, f"超管不该绕过附件归属校验，实际 {resp.status_code}"
        # 与「附件不存在」同文案：防枚举（get_attachment_for_user 既有口径）
        assert resp.json().get("message") == "附件不存在"


# ── 验收 4：加密 PDF → encrypted（不是空字符串）─────────────────────────────


class TestEncryptedPdf:
    """加密 PDF 必须给出 ``error="encrypted"``。

    旧行为是解析端点 ``success=True`` + 空文本，模型拿到 ``chars: 0`` 且
    无任何报错——用户完全不知道附件为什么读不到。这里断言的是**错误码**。
    """

    def test_encrypted_pdf_reports_encrypted_error(self, capsys: Any) -> None:
        user, client = _make_user("vision-encrypted")
        attachment_id = _upload(client, user, "加密合同.pdf", _encrypted_pdf(), "application/pdf")

        body = _pages(client, attachment_id, pages="1")

        assert body["error"] == "encrypted", (
            f"加密 PDF 的 error 应为 encrypted，实际 {body['error']!r}（空串/空内容冒充成功正是本次要防的退化）"
        )
        # 页条目可以保留（告诉调用方「第 1 页失败了、原因是什么」），但不许有图字节：
        # 有字节才叫「渲染成功」，空 b64 是失败陈述，不是空白图冒充。
        assert _page_images(body) == [], "加密 PDF 不得返回任何页图字节（禁止空白图冒充成功）"
        for page in body["pages_returned"]:
            assert page["b64"] == ""
            assert page["bytes"] == 0
            assert page["error"] == "encrypted", f"每页应带 encrypted 错误码，实际 {page['error']!r}"

        logger.info(
            f"\n[验收4 实测] error={body['error']!r} 页条目数={len(body['pages_returned'])} "
            f"页图字节合计={sum(p['bytes'] for p in body['pages_returned'])}"
        )

    def test_encrypted_pdf_content_endpoint_returns_bytes_not_empty(self) -> None:
        """对照：/content 仍应原样返回加密字节（让渲染层去判断加密，而不是提前判空）。

        若 /content 把加密文件当空文件返回，渲染层就只会看到 0 字节，
        错误码会退化成 parse_empty，用户拿不到「请上传解密版」的指引。
        """
        user, client = _make_user("vision-encrypted-content")
        attachment_id = _upload(client, user, "加密合同.pdf", _encrypted_pdf(), "application/pdf")

        resp = client.get(f"/api/v1/agent/attachments/{attachment_id}/content")
        assert resp.status_code == 200
        raw = base64.b64decode(resp.json()["content_base64"])
        assert raw, "/content 不得把加密 PDF 当空文件返回"
        assert raw.startswith(b"%PDF"), "加密 PDF 仍是合法 PDF 容器（%PDF 魔数）"


# ── 生产事故回归：有文字层 PDF + 解析转异步 + 默认调用 → 正文必须拿得到 ────────
#
# 2026-10 真实事故（用户上传裁定书 PDF 后 AI 助手答复「文字层为空、疑似加密」）：
#
#   /pages 端点对**文字层页**按设计不渲染图（b64=""，省视觉 token），docstring
#   写着「调用方应改走文本通道」——但端点只返回了 has_text_layer=True，
#   **没有把 page.text 带出来**。MCP 工具见到「无 b64」就跳过该页，同时
#   /document-parsing 把文件转成异步任务（task_id，轮询 not_found）也拿不到文字。
#   两条腿同时断 → parse_empty → 一份完全正常、有 1223 字文字层的裁定书被判为
#   「不可读」。
#
# 之前的用例全部漏掉它，因为各自都只覆盖了半边：
#   - TestTextPathDoesNotDegrade 走 pages="1" 显式取页，且只查「image 块数为 0」，
#     不查正文有没有被带回来；
#   - TestLargePdfPageTargeting / 扫描件用例用的是**无文字层** fixture，
#     根本走不到「文字层页不出图」这条分支；
#   - 单元测试把 client.get 全 mock 掉，mocked 响应里 b64 永远非空。
# 下面这组固定复现生产路径：真实端点 + 有文字层 + 默认调用（不给 pages）。

def _rich_text_pdf() -> bytes:
    """模拟那份裁定书：多页、有完整文字层、正文远超 50 字符阈值。

    用 ASCII 正文而非中文：``china-s`` 内置字体在本机 PyMuPDF 下会丢字
    （见 ``_text_pdf`` 的说明），丢字会让页面被判成扫描页，就不是本用例
    要覆盖的对象了。这里关心的是「文字层页的文字有没有被端点和工具传出来」，
    与字符集无关。
    """
    paragraphs = [
        "CIVIL RULING OF THE PEOPLE'S COURT. Case No. (2025) Yue 0605 Min Te 1286.",
        "Applicant A: Foshan Baojie Aluminum Co., Ltd., located in Nanhai District, Foshan.",
        "Applicant B: Foshan Wangbaiye Building Materials Co., Ltd., and Zhang Fuyu.",
        "The court examined the mediation agreement submitted by both applicants and finds it valid.",
        "The parties shall perform their obligations under the mediation agreement voluntarily.",
    ]
    doc = pymupdf.open()
    try:
        for index, paragraph in enumerate(paragraphs):
            page = doc.new_page(width=420, height=420)
            page.insert_text((12, 40), f"Page {index + 1}", fontsize=9)
            page.insert_text((12, 70), paragraph, fontsize=8)
            page.insert_text((12, 100), paragraph[::-1], fontsize=8)
        return bytes(doc.tobytes())
    finally:
        doc.close()


class TestTextLayerPageCarriesTextBack:
    """文字层页不出图时，端点与工具都必须把**正文**带回来，而不是只报「有文字层」。

    ## 为什么必须强制「解析转异步」

    本机没配 mineru/textin 平台时，``/document-parsing/extract-text`` 走**同步**
    路径，能直接把文字层读出来——这样工具根本不会走到页图回落分支，
    也就测不到本次事故。**律所生产环境配了异步解析平台**（实测返回
    ``task_id`` + ``status=pending``），那才是事故发生的真实条件。

    因此下面用 ``_force_async_parse`` 把解析端点钉成异步响应，复现生产路径：
    「解析没文字 → 回落页图 → 端点对文字层页不出图 → 只有 page.text 能救」。
    """

    @staticmethod
    def _force_async_parse() -> Any:
        """让解析端点恒返回「已转异步任务」，复现生产环境的解析行为。"""
        fake = mock.MagicMock()
        fake.upload.return_value = {
            "success": True,
            "task_id": "task-production-async",
            "status": "pending",
            "text": "",
        }
        return fake

    def test_pages_endpoint_returns_text_for_text_layer_pages(self) -> None:
        """第一道闸：端点必须回 page.text。

        只回 ``has_text_layer=True`` 而 ``text=""`` 等于让调用方知道「有字」
        却拿不到字——这正是生产事故的直接成因。
        """
        user, client = _make_user("vision-textcarry-endpoint")
        attachment_id = _upload(client, user, "裁定书.pdf", _rich_text_pdf(), "application/pdf")

        body = _pages(client, attachment_id, pages="all")

        assert not body.get("error"), f"文字层 PDF 不应报错，实际 error={body.get('error')!r}"
        entries = body.get("pages_returned") or []
        assert entries, "文字层 PDF 应至少返回一页条目（哪怕不出图）"

        carried = "".join(str(page.get("text") or "") for page in entries)
        assert carried.strip(), (
            "文字层页必须把正文带回来：/pages 对 has_text_layer=true 的页不渲染图，"
            "但必须返回 page.text，否则调用方「知道有字却拿不到字」"
            f"（当前 pages_returned={entries[:1]}）"
        )
        assert len(carried.strip()) >= 50, f"回传正文过短，疑似占位：{carried[:80]!r}"
        assert not _page_images(body), (
            f"文字层页不应渲染图（应 b64 为空），实际 {len(_page_images(body))} 页带图"
        )

    def test_default_call_with_async_parse_returns_text_body(self) -> None:
        """第二道闸（生产路径）：解析转异步 + 默认调用（不传 pages）仍必须拿到正文。

        这是用户实际触发的路径：前端发消息 → 模型调
        ``read_agent_attachment(attachment_id)``，**不会**手写 pages 参数。
        事故形态：解析转异步 → 回落页图 → 页图对文字层页返回空 b64 →
        工具整页跳过 → ``parse_empty`` → AI 助手对用户说「文件不可读」。
        """
        from mcp_server.tools.core import agent_attachments as tool

        from ._mcp_http_bridge import patch_client

        user, client = _make_user("vision-textcarry-default")
        attachment_id = _upload(client, user, "裁定书.pdf", _rich_text_pdf(), "application/pdf")

        with patch_client(client), mock.patch.object(tool, "_extract_text") as fake_extract:
            # 解析侧完全复现生产：只有 task_id，没有文字
            fake_extract.return_value = {
                "error": "parse_empty",
                "retryable": True,
                "notices": ["解析已转异步任务 task_id=task-production-async"],
            }
            blocks = tool.read_agent_attachment(attachment_id=attachment_id)

        meta = json.loads(blocks[0].text)
        assert not meta.get("error"), (
            "解析转异步时不得退化成 parse_empty：文字层页的 page.text 必须被端点带出、"
            f"并被工具并入正文。meta={meta}"
        )
        assert meta.get("strategy") in ("text", "mixed"), (
            f"有文字层的 PDF 应走文本路径，实际 strategy={meta.get('strategy')!r}"
        )
        assert int(meta.get("chars") or 0) >= 50, f"chars 过小，正文没拿到：chars={meta.get('chars')!r}"

        body_text = "".join(block.text for block in blocks if getattr(block, "type", None) == "text")
        assert "CIVIL RULING" in body_text, "正文必须真的出现在 content blocks 里（不能只有元数据块）"
        assert "Case No." in body_text, "案号等关键正文也必须在"

    def test_async_parse_text_layer_pdf_yields_zero_image_blocks(self) -> None:
        """第三道闸：修好「带文字」的同时，不能顺手把所有页都渲染成图。

        最贵的退化是「文字回来了，但每页还多烧一张 1568px 的图」。
        """
        from mcp_server.tools.core import agent_attachments as tool

        from ._mcp_http_bridge import patch_client

        user, client = _make_user("vision-textcarry-noimg")
        attachment_id = _upload(client, user, "裁定书.pdf", _rich_text_pdf(), "application/pdf")

        with patch_client(client), mock.patch.object(tool, "_extract_text") as fake_extract:
            fake_extract.return_value = {"error": "parse_empty", "retryable": True, "notices": ["转异步"]}
            blocks = tool.read_agent_attachment(attachment_id=attachment_id)

        image_blocks = [block for block in blocks if getattr(block, "type", None) == "image"]
        assert not image_blocks, (
            f"文字层 PDF 不应产生 image block（会白烧视觉 token），实际有 {len(image_blocks)} 个"
        )

    def test_scanned_pdf_with_async_parse_still_renders_images(self) -> None:
        """反向保护：无文字层的扫描件即使解析转异步，仍必须出图。

        别为「带文字」把扫描件也退化成纯文本——那是本次修复最容易引入的反向事故。
        """
        from mcp_server.tools.core import agent_attachments as tool

        from ._mcp_http_bridge import patch_client

        user, client = _make_user("vision-textcarry-scan")
        attachment_id = _upload(client, user, "扫描件.pdf", _scan_pdf(2), "application/pdf")

        with patch_client(client), mock.patch.object(tool, "_extract_text") as fake_extract:
            fake_extract.return_value = {"error": "parse_empty", "retryable": True, "notices": ["转异步"]}
            blocks = tool.read_agent_attachment(attachment_id=attachment_id)

        meta = json.loads(blocks[0].text)
        image_blocks = [block for block in blocks if getattr(block, "type", None) == "image"]
        assert image_blocks, f"扫描件必须走图像路径，实际 meta={meta}"
        assert meta.get("strategy") in ("image", "mixed"), (
            f"strategy 应为 image/mixed，实际 {meta.get('strategy')!r}"
        )
        for block in image_blocks:
            raw = base64.b64decode(block.data)
            assert raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8"), (
                "image block 的 base64 必须解码成真 PNG/JPEG，不能是伪 base64"
            )
