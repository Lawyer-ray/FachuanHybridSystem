"""read_folder_file 工具测试：参数校验、404 归一化、文本/图像路径与 read_agent_attachment 同构。"""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest import mock

import pytest
from mcp.types import TextContent

_PDF = "判决书.pdf"
_PDF_MIME = "application/pdf"


@pytest.fixture()
def fake_client() -> Any:
    from mcp_server.tools.contracts import folder_file
    from mcp_server.tools.core import agent_attachments

    shared = mock.MagicMock()
    with mock.patch.object(folder_file, "client", shared), mock.patch.object(agent_attachments, "client", shared):
        yield shared


def _meta_of(blocks: list[Any]) -> dict[str, Any]:
    return json.loads(blocks[0].text)


def test_invalid_contract_id_rejected(fake_client: Any) -> None:
    from mcp_server.tools.contracts.folder_file import read_folder_file

    for bad in (0, -3):
        with pytest.raises(ValueError):
            read_folder_file(contract_id=bad, subpath="1-一审/起诉状.pdf")


def test_empty_subpath_rejected(fake_client: Any) -> None:
    from mcp_server.tools.contracts.folder_file import read_folder_file

    with pytest.raises(ValueError):
        read_folder_file(contract_id=390, subpath="   ")


def test_content_404_maps_to_not_found_metadata(fake_client: Any) -> None:
    """无权/不存在在服务端同是 404——工具侧归一化成元数据错误，不抛异常。"""
    from mcp_server.tools.contracts.folder_file import read_folder_file

    fake_client.get.side_effect = RuntimeError("HTTP 404: 文件不存在（可能已被移动或移入删除区）")
    blocks = read_folder_file(contract_id=390, subpath="1-一审/起诉状.pdf")
    meta = _meta_of(blocks)
    assert meta["error"] == "not_found"
    assert len(blocks) == 1  # 只给元数据，不用空内容冒充成功


def test_plain_text_file_returns_body(fake_client: Any) -> None:
    from mcp_server.tools.contracts.folder_file import read_folder_file

    body = "一审起诉状正文" * 20
    fake_client.get.return_value = {
        "attachment_id": "folder:390/1-一审/起诉状.txt",
        "filename": "起诉状.txt",
        "mime": "text/plain",
        "size": len(body.encode()),
        "content_base64": base64.b64encode(body.encode()).decode("ascii"),
    }
    blocks = read_folder_file(contract_id=390, subpath="1-一审/起诉状.txt")
    meta = _meta_of(blocks)
    assert meta["strategy"] == "text"
    assert meta.get("error", "") == ""
    assert isinstance(blocks[1], TextContent)
    assert body[:20] in blocks[1].text


def test_pdf_text_extraction_path(fake_client: Any) -> None:
    """PDF 走解析端点取正文（max_length 探针），与附件版同一套编排。"""
    from mcp_server.tools.contracts.folder_file import read_folder_file

    body = "判决主文：驳回上诉，维持原判。" * 30
    fake_client.get.return_value = {
        "attachment_id": "folder:390/1-一审/判决书.pdf",
        "filename": _PDF,
        "mime": _PDF_MIME,
        "size": 1024,
        "content_base64": base64.b64encode(b"%PDF-fake").decode("ascii"),
    }
    fake_client.upload.return_value = {"success": True, "text": body, "task_id": ""}

    blocks = read_folder_file(contract_id=390, subpath="1-一审/判决书.pdf")
    meta = _meta_of(blocks)
    assert meta["strategy"] == "text"
    assert meta["chars"] == len(body)
    # 数据源打到 folder-refs 端点，而不是附件端点
    called_url = fake_client.get.call_args.args[0]
    assert called_url == "/agent/folder-refs/content"
    assert fake_client.upload.call_args.args[0] == "/document-parsing/extract-text"


def test_render_pages_uses_folder_endpoint(fake_client: Any) -> None:
    """文字层不可用时回落页图：pages 请求打到 folder-refs 端点。"""
    from mcp_server.tools.contracts.folder_file import read_folder_file

    fake_client.get.side_effect = [
        {  # /content
            "attachment_id": "folder:390/1-一审/扫描件.pdf",
            "filename": _PDF,
            "mime": _PDF_MIME,
            "size": 2048,
            "content_base64": base64.b64encode(b"%PDF-scanned").decode("ascii"),
        },
        {  # /pages
            "attachment_id": "folder:390/1-一审/扫描件.pdf",
            "filename": _PDF,
            "mime": _PDF_MIME,
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
                    "b64": base64.b64encode(b"PNG-1").decode("ascii"),
                    "bytes": 5,
                    "width": 595,
                    "height": 842,
                    "has_text_layer": False,
                    "error": "",
                    "detail": "",
                }
            ],
        },
    ]
    fake_client.upload.return_value = {"success": True, "text": "", "task_id": "task-1"}  # 空文本 → 回落页图

    blocks = read_folder_file(contract_id=390, subpath="1-一审/扫描件.pdf")
    meta = _meta_of(blocks)
    assert meta["strategy"] in ("image", "mixed")
    pages_url = fake_client.get.call_args_list[1].args[0]
    assert pages_url == "/agent/folder-refs/pages"
