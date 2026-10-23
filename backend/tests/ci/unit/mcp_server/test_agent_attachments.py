"""read_agent_attachment 工具测试：content blocks 契约、文本/图像策略与失败处理。

工具返回 ``list[TextContent | ImageContent]``（MCP 框架据此**不生成
output_schema、不做校验**，直接把块下发给模型）。第一个块是 JSON 元数据，
其后是正文文本块或「每页说明 + ImageContent」。

附件内容经服务端流转：

- ``GET /agent/attachments/{id}/content`` → 原始字节
- ``POST /document-parsing/extract-text`` → 正文（文本路径）
- ``GET /agent/attachments/{id}/pages`` → 每页渲染图（图像路径）

用假 client 驱动这三条路径。
"""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest import mock

import pytest
from mcp.types import ImageContent, TextContent

_ATTACHMENT_ID = "11111111-1111-4111-8111-111111111111"
_PDF = "合同.pdf"
_PDF_MIME = "application/pdf"


@pytest.fixture()
def fake_client() -> Any:
    from mcp_server.tools.core import agent_attachments

    shared = mock.MagicMock()
    with mock.patch.object(agent_attachments, "client", shared):
        yield shared


def _content_entry(filename: str, mime: str, data: bytes) -> dict[str, Any]:
    return {
        "attachment_id": _ATTACHMENT_ID,
        "filename": filename,
        "mime": mime,
        "size": len(data),
        "content_base64": base64.b64encode(data).decode("ascii"),
    }


def _pages_response(
    pages: list[int],
    *,
    mime: str = "image/png",
    has_text_layer: bool = False,
    error: str = "",
) -> dict[str, Any]:
    """模拟 ``GET /agent/attachments/{id}/pages`` 的响应形状（T4 已落地）。"""
    return {
        "attachment_id": _ATTACHMENT_ID,
        "filename": _PDF,
        "mime": _PDF_MIME,
        "total_pages": max(pages) if pages else 0,
        "strategy": "image",
        "error": error,
        "detail": "",
        "notices": [],
        "truncated_pages": False,
        "pages_returned": [
            {
                "page": page,
                "mime": mime,
                "b64": base64.b64encode(f"PNG-{page}".encode()).decode("ascii"),
                "bytes": 5,
                "width": 1191,
                "height": 1684,
                "has_text_layer": has_text_layer,
                "error": "",
                "detail": "",
            }
            for page in pages
        ],
    }


def _meta(blocks: list[TextContent | ImageContent]) -> dict[str, Any]:
    """解析第一个块的元数据 JSON。"""
    assert blocks, "工具不能返回空列表"
    first = blocks[0]
    assert isinstance(first, TextContent)
    return json.loads(first.text)


def _texts(blocks: list[TextContent | ImageContent]) -> list[str]:
    return [block.text for block in blocks if isinstance(block, TextContent)]


def _images(blocks: list[TextContent | ImageContent]) -> list[ImageContent]:
    return [block for block in blocks if isinstance(block, ImageContent)]


def _pdf_with_text(text: str) -> dict[str, Any]:
    return {"success": True, "text": text, "metadata": {"page_count": 1}}


class TestTextStrategy:
    def test_text_attachment_returns_plain_text_block(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry("笔记.txt", "text/plain", "你好，附件".encode())

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["strategy"] == "text"
        assert meta["chars"] == 5
        assert meta["truncated"] is False
        assert meta["attachment_id"] == _ATTACHMENT_ID
        assert _texts(blocks)[1] == "你好，附件"
        # 文本类不走解析端点，也不取页图
        fake_client.upload.assert_not_called()
        assert [c.args[0] for c in fake_client.get.call_args_list] == [f"/agent/attachments/{_ATTACHMENT_ID}/content"]

    def test_document_attachment_parsers_via_extract_endpoint(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry(_PDF, _PDF_MIME, b"%PDF-fake")
        fake_client.upload.return_value = _pdf_with_text("合同正文……" * 20)

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        assert _meta(blocks)["strategy"] == "text"
        # 转投解析端点：multipart 文件名沿用原附件名；max_length 默认 20000
        # 且多要 1 字符作截断探针（解析端点硬截断、不回报总长）
        call = fake_client.upload.call_args
        assert call.args[0] == "/document-parsing/extract-text"
        assert call.kwargs["files"]["file"][0] == _PDF
        assert call.kwargs["data"]["max_length"] == "20001"
        # 有文字层就不必渲染页图
        assert f"/agent/attachments/{_ATTACHMENT_ID}/pages" not in [c.args[0] for c in fake_client.get.call_args_list]

    def test_truncated_probe_detects_more_content(self, fake_client: Any) -> None:
        """高危回归：解析端点按 max_length 硬截断，探针（+1 字符）必须让 truncated=true。"""

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry("判决书.pdf", _PDF_MIME, b"%PDF-fake")
        fake_client.upload.return_value = _pdf_with_text("正" * 20001)

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["truncated"] is True
        assert meta["chars"] == 20001
        assert len(_texts(blocks)[1]) == 20000

    def test_exact_length_not_truncated(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry("短文.pdf", _PDF_MIME, b"%PDF-fake")
        fake_client.upload.return_value = _pdf_with_text("全文就这些，共八字" * 10)

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        assert _meta(blocks)["truncated"] is False
        assert _texts(blocks)[1].startswith("全文就这些")

    def test_segmented_read_passes_start(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        text = "x" * 3000
        fake_client.get.return_value = _content_entry("笔记.txt", "text/plain", text.encode())

        first = read_agent_attachment(_ATTACHMENT_ID, max_length=1000)
        assert _meta(first)["truncated"] is True
        assert _texts(first)[1] == "x" * 1000
        second = read_agent_attachment(_ATTACHMENT_ID, max_length=1000, start=1000)
        assert _texts(second)[1] == "x" * 1000
        assert _meta(second)["truncated"] is True

    def test_max_length_clamped_both_directions(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import MAX_LENGTH_CEILING, MAX_LENGTH_FLOOR, read_agent_attachment

        fake_client.get.return_value = _content_entry(_PDF, _PDF_MIME, b"%PDF-fake")
        fake_client.upload.return_value = _pdf_with_text("y" * 200)

        read_agent_attachment(_ATTACHMENT_ID, max_length=10_000_000)
        assert fake_client.upload.call_args.kwargs["data"]["max_length"] == str(MAX_LENGTH_CEILING + 1)

        read_agent_attachment(_ATTACHMENT_ID, max_length=5)
        assert fake_client.upload.call_args.kwargs["data"]["max_length"] == str(MAX_LENGTH_FLOOR + 1)


class TestImageStrategy:
    def test_scanned_pdf_falls_back_to_page_images(self, fake_client: Any) -> None:
        """文字层总长 < 50 字符 → 整体走图像路径，不再返回空正文。"""

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response([1, 2, 3]),
        ]
        fake_client.upload.return_value = _pdf_with_text("第 1 页\n共 3 页")  # 只残留页眉

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["strategy"] == "image"
        assert meta["chars"] == 0
        assert [entry["page"] for entry in meta["pages_returned"]] == [1, 2, 3]
        # 每页：一条「原图，非 OCR」说明 + 一个 image block
        page_notes = [text for text in _texts(blocks) if text.startswith("第 ")]
        assert page_notes == ["第 1 页（原图，非 OCR）", "第 2 页（原图，非 OCR）", "第 3 页（原图，非 OCR）"]
        images = _images(blocks)
        assert len(images) == 3
        assert images[0].type == "image"
        assert images[0].mime_type == "image/png"
        assert base64.b64decode(images[0].data) == b"PNG-1"

    def test_page_request_sends_contract_params(self, fake_client: Any) -> None:
        """dpi 钳到 72-300、format 归一化；**不传 max_pages**（服务端会当硬截断上限）。"""

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response([1, 2]),
        ]
        fake_client.upload.return_value = _pdf_with_text("")

        read_agent_attachment(_ATTACHMENT_ID, pages=[1, 2], dpi=500, format="jpeg", max_pages=5)

        page_call = fake_client.get.call_args_list[1]
        assert page_call.args[0] == f"/agent/attachments/{_ATTACHMENT_ID}/pages"
        assert page_call.kwargs["params"] == {"pages": "1,2", "dpi": "300", "format": "jpeg"}

    def test_dpi_clamped_to_floor(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response([1]),
        ]
        fake_client.upload.return_value = _pdf_with_text("")

        read_agent_attachment(_ATTACHMENT_ID, dpi=10)

        assert fake_client.get.call_args_list[1].kwargs["params"]["dpi"] == "72"

    def test_max_pages_truncation_is_announced(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import MAX_PAGES_CEILING, read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response(list(range(1, MAX_PAGES_CEILING + 1))),
        ]
        fake_client.upload.return_value = _pdf_with_text("")

        blocks = read_agent_attachment(_ATTACHMENT_ID, pages="1-20")
        meta = _meta(blocks)
        assert len(meta["pages_returned"]) == MAX_PAGES_CEILING
        assert any("上限" in notice and "截断" in notice for notice in meta["notices"])
        # 钳制在本工具侧完成：只把前 10 页发给服务端
        assert fake_client.get.call_args_list[1].kwargs["params"]["pages"] == ",".join(
            str(page) for page in range(1, MAX_PAGES_CEILING + 1)
        )

    def test_pages_all_expands_to_total_pages(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response([1, 2]),
        ]
        fake_client.upload.return_value = {"success": True, "text": "", "metadata": {"page_count": 2}}

        blocks = read_agent_attachment(_ATTACHMENT_ID, pages="all")
        assert [entry["page"] for entry in _meta(blocks)["pages_returned"]] == [1, 2]

    def test_image_block_is_decodable_with_correct_mime(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response([1], mime="image/jpeg"),
        ]
        fake_client.upload.return_value = _pdf_with_text("")

        images = _images(read_agent_attachment(_ATTACHMENT_ID))
        assert len(images) == 1
        assert images[0].mime_type == "image/jpeg"
        assert base64.b64decode(images[0].data) == b"PNG-1"


class TestMixedStrategy:
    def test_empty_pages_fall_back_per_page(self, fake_client: Any) -> None:
        """有文字层但存在空页 → 空页出图、其余页仍给文本，strategy="mixed"。"""

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        marked = "【第1页】\n" + "第一页正文" * 10 + "\n\n【第2页】\n\n【第3页】\n" + "第三页正文" * 10
        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-mixed"),
            _pages_response([2], has_text_layer=False),
        ]
        fake_client.upload.return_value = {"success": True, "text": marked, "metadata": {"page_count": 3}}

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["strategy"] == "mixed"
        assert meta["chars"] == len(marked)
        assert meta["total_pages"] == 3
        assert [entry["page"] for entry in meta["pages_returned"]] == [2]
        assert any("无文字层" in notice for notice in meta["notices"])
        # 文本块仍在（含可读页正文），且图块排在文本块之后
        assert any("第一页正文" in text for text in _texts(blocks))
        assert isinstance(blocks[-2], TextContent)
        assert blocks[-2].text == "第 2 页（原图，非 OCR）"
        assert isinstance(blocks[-1], ImageContent)


class TestParseEmpty:
    def test_empty_text_and_render_failure_returns_parse_empty(self, fake_client: Any) -> None:
        """文字层空且渲染失败 → error="parse_empty"，禁止返回空 content 冒充成功。"""

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.upload.return_value = _pdf_with_text("")
        # 页图端点抛错（服务端 500，没有错误码可用）
        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            RuntimeError("HTTP 500: render failed"),
        ]

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        # 渲染端 500 没有错误码可用 → 归 parse_empty（不是 not_found：附件本身能读到）
        assert meta["error"] == "parse_empty"
        assert meta["strategy"] == "image"
        assert meta["chars"] == 0
        assert _images(blocks) == []
        # 只返回元数据块：不能跟一个空正文块
        assert len(blocks) == 1
        assert any("渲染失败" in notice for notice in meta["notices"])

    def test_empty_pages_response_is_parse_empty(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        empty_pages = {"attachment_id": _ATTACHMENT_ID, "pages_returned": [], "error": ""}
        fake_client.get.side_effect = [_content_entry(_PDF, _PDF_MIME, b"%PDF-scan"), empty_pages]
        fake_client.upload.return_value = _pdf_with_text("")

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["error"] == "parse_empty"
        assert any("页图端点未返回任何页" in notice for notice in meta["notices"])

    @pytest.mark.parametrize("server_error", ["encrypted", "too_large", "unsupported_mime"])
    def test_render_error_code_from_server_wins_over_parse_empty(self, fake_client: Any, server_error: str) -> None:
        """服务端 200 + error 错误码要原样透出（不是笼统的 parse_empty）。"""

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.upload.return_value = _pdf_with_text("")
        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-scan"),
            _pages_response([], error=server_error),
        ]

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["error"] == server_error
        assert _images(blocks) == []
        assert any(server_error in notice for notice in meta["notices"])

    def test_server_truncation_notice_is_forwarded(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        response = _pages_response([1])
        response["notices"] = ["超过 max_pages=10 限制，还有 4 页未渲染（可用 pages 参数分段取）"]
        response["truncated_pages"] = True
        fake_client.get.side_effect = [_content_entry(_PDF, _PDF_MIME, b"%PDF-scan"), response]
        fake_client.upload.return_value = _pdf_with_text("")

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert any("还有 4 页未渲染" in notice for notice in meta["notices"])

    def test_render_failure_with_usable_text_keeps_text(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = [
            _content_entry(_PDF, _PDF_MIME, b"%PDF-mixed"),
            RuntimeError("HTTP 500: render failed"),
        ]
        fake_client.upload.return_value = {"success": True, "text": "【第1页】\n\n【第2页】\n" + "有字" * 40}

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert "error" not in meta
        assert meta["strategy"] == "text"
        assert any("回落到文字层" in notice for notice in meta["notices"])


class TestErrorCodes:
    def test_async_backend_task_announced_as_retryable(self, fake_client: Any) -> None:
        """auto 选到异步后端（mineru/textin）时告知 task_id 与轮询方式，不吞成空内容。

        用 docx：它能出文字、但**没有页图形态**，所以只能等 OCR 结果。
        （位图附件不再走这条路——它们直接出原图，见 test_image_attachment_goes_straight_to_page_image）
        """

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry(
            "材料.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"zzz"
        )
        fake_client.upload.return_value = {"success": True, "task_id": "task-7", "status": "pending", "text": ""}

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["retryable"] is True
        assert any("task-7" in notice and "get_document_parsing_task" in notice for notice in meta["notices"])

    def test_image_attachment_goes_straight_to_page_image(self, fake_client: Any) -> None:
        """位图附件不送 OCR：直接返回原图，不当成「解析中」丢给模型一个空结果。

        异步解析后端对图片会转 OCR 任务（task_id+pending）；若原样透传，模型
        只拿到「请去轮询」，而它本可以看图。这是本次故障的同一类静默失败。
        """

        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
        fake_client.get.return_value = _content_entry("扫描件.png", "image/png", base64.b64decode(png))
        fake_client.upload.return_value = {"success": True, "task_id": "task-9", "status": "pending", "text": ""}
        fake_client.get.side_effect = None
        fake_client.get.return_value = _content_entry("扫描件.png", "image/png", base64.b64decode(png))
        # 页图端点返回一页真 PNG
        fake_client.get.side_effect = lambda path, *a, **kw: (
            _content_entry("扫描件.png", "image/png", base64.b64decode(png))
            if path.endswith("/content")
            else {
                "attachment_id": _ATTACHMENT_ID,
                "filename": "扫描件.png",
                "mime": "image/png",
                "total_pages": 1,
                "strategy": "image",
                "error": "",
                "detail": "",
                "notices": [],
                "truncated_pages": False,
                "pages_returned": [
                    {
                        "page": 1,
                        "mime": "image/png",
                        "b64": png,
                        "bytes": 72,
                        "width": 10,
                        "height": 10,
                        "has_text_layer": False,
                        "error": "",
                        "detail": "",
                    }
                ],
            }
        )

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["strategy"] == "image"
        assert [page["page"] for page in meta["pages_returned"]] == [1]
        # 图片直出，不应当再转 OCR 任务
        fake_client.upload.assert_not_called()
        assert any(block.type == "image" for block in blocks)

    def test_parse_failure_maps_to_parse_failed(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry(
            "坏文件.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"zzz"
        )
        fake_client.upload.return_value = {"success": False, "error": "corrupt"}

        blocks = read_agent_attachment(_ATTACHMENT_ID)
        meta = _meta(blocks)
        assert meta["error"] == "parse_failed"
        assert meta["chars"] == 0
        assert len(blocks) == 1

    def test_encrypted_reason_maps_to_encrypted(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry(_PDF, _PDF_MIME, b"%PDF-locked")
        fake_client.upload.return_value = {"success": False, "error": "PDF is encrypted"}

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["error"] == "encrypted"

    def test_missing_attachment_maps_to_not_found(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = RuntimeError("HTTP 404: {'detail': '附件不存在'}")

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["error"] == "not_found"
        assert meta["chars"] == 0
        # 不抛异常，也不再继续调解析 / 页图端点
        fake_client.upload.assert_not_called()

    def test_403_maps_to_forbidden(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = RuntimeError("HTTP 403: forbidden")

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["error"] == "forbidden"

    def test_too_large_maps_to_too_large(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = RuntimeError("HTTP 413: payload too large")

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["error"] == "too_large"

    def test_unsupported_mime_from_parse_reason(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry("表格.xlsx", "application/vnd.ms-excel", b"xlsx")
        fake_client.upload.return_value = {"success": False, "error": "不支持的格式"}

        meta = _meta(read_agent_attachment(_ATTACHMENT_ID))
        assert meta["error"] == "unsupported_mime"

    def test_all_without_page_count_is_passed_through_to_page_endpoint(self, fake_client: Any) -> None:
        """页数未知时 ``pages="all"`` 应透传给页图端点，而不是报越界。

        扫描件回落路径下总页数未知（文字提取失败，没有 page_count）；若在这里
        报 page_out_of_range，模型会对用户说「这份材料没有页」——与事实相反。
        实际页数由端点打开文件后自己数并受 max_pages 截断。
        """
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.side_effect = lambda path, *a, **kw: (
            _content_entry(_PDF, _PDF_MIME, b"%PDF-fake") if path.endswith("/content") else _pages_response([1, 2])
        )
        # 文字提取转了异步任务 → 回落页图（total_pages 未知）
        fake_client.upload.return_value = {"success": True, "task_id": "t-1", "status": "pending", "text": ""}

        blocks = read_agent_attachment(_ATTACHMENT_ID, pages="all")
        meta = _meta(blocks)
        assert not meta.get("error")
        assert [page["page"] for page in meta["pages_returned"]] == [1, 2]
        pages_calls = [c for c in fake_client.get.call_args_list if str(c.args[0]).endswith("/pages")]
        assert pages_calls, "应当请求页图端点"
        assert pages_calls[-1].kwargs["params"]["pages"] == "all"

    def test_invalid_attachment_id_rejected_before_request(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        with pytest.raises(ValueError, match="UUID"):
            read_agent_attachment("../etc/passwd")
        # 格式不过直接拒绝，不发请求（也杜绝把任意字符串拼进 URL）
        fake_client.get.assert_not_called()

    def test_invalid_format_rejected_before_request(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        with pytest.raises(ValueError, match="format"):
            read_agent_attachment(_ATTACHMENT_ID, format="webp")
        fake_client.get.assert_not_called()


class TestPagesParsing:
    @pytest.mark.parametrize(
        ("pages", "expected"),
        [
            (None, None),
            ("all", "all"),
            ("1-3,5", [1, 2, 3, 5]),
            ("2,2,1", [1, 2]),
            ("[1, 3]", [1, 3]),
            ([3, 1], [1, 3]),
        ],
    )
    def test_parse_pages_forms(self, pages: Any, expected: Any) -> None:
        from mcp_server.tools.core.agent_attachments import _parse_pages

        assert _parse_pages(pages) == expected

    def test_invalid_page_token_rejected(self) -> None:
        from mcp_server.tools.core.agent_attachments import _parse_pages

        with pytest.raises(ValueError, match="页码"):
            _parse_pages("1,a")
