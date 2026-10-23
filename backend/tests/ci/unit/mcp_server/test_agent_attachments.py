"""read_agent_attachment 工具测试：正文提取路径、分段与失败处理。

附件内容经服务端流转（GET content → /document-parsing/extract-text），
模型只看到文本。用假 client 驱动两条路径（文本直读 / 解析端点提取）。
"""

from __future__ import annotations

import base64
from typing import Any
from unittest import mock

import pytest


@pytest.fixture()
def fake_client() -> Any:
    from mcp_server.tools.core import agent_attachments

    shared = mock.MagicMock()
    with mock.patch.object(agent_attachments, "client", shared):
        yield shared


def _content_entry(filename: str, mime: str, data: bytes) -> dict[str, Any]:
    return {
        "attachment_id": "att-1",
        "filename": filename,
        "mime": mime,
        "size": len(data),
        "content_base64": base64.b64encode(data).decode("ascii"),
    }


class TestReadAgentAttachment:
    def test_text_attachment_returns_decoded_content_directly(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry("笔记.txt", "text/plain", "你好，附件".encode())

        result = read_agent_attachment("att-1")
        assert result["content"] == "你好，附件"
        assert result["truncated"] is False
        # 文本类不走解析端点
        fake_client.upload.assert_not_called()

    def test_document_attachment_parsers_via_extract_endpoint(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry("合同.pdf", "application/pdf", b"%PDF-fake")
        fake_client.upload.return_value = {"success": True, "text": "合同正文……"}

        result = read_agent_attachment("att-1")
        assert result["content"] == "合同正文……"
        # 转投解析端点：multipart 文件名沿用原附件名，max_length 默认 20000
        call = fake_client.upload.call_args
        assert call.args[0] == "/document-parsing/extract-text"
        assert call.kwargs["files"]["file"][0] == "合同.pdf"

    def test_segmented_read_passes_start(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        text = "x" * 3000
        fake_client.get.return_value = _content_entry("笔记.txt", "text/plain", text.encode())

        first = read_agent_attachment("att-1", max_length=1000)
        assert first["truncated"] is True
        assert first["content"] == "x" * 1000
        second = read_agent_attachment("att-1", max_length=1000, start=1000)
        assert second["content"] == "x" * 1000
        assert second["truncated"] is True

    def test_parse_failure_returns_error_field_not_raises(self, fake_client: Any) -> None:
        from mcp_server.tools.core.agent_attachments import read_agent_attachment

        fake_client.get.return_value = _content_entry(
            "坏文件.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"zzz"
        )
        fake_client.upload.return_value = {"success": False, "error": "corrupt"}

        result = read_agent_attachment("att-1")
        assert "解析失败" in result["error"]
        assert result["content"] == ""
