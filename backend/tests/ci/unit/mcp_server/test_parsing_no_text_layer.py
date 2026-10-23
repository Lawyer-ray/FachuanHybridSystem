"""extract_document_text / parse_document 的空文字层守卫测试。

同类问题的第二现场：附件链路（read_agent_attachment）已修「空字符串冒充
成功」，但老 base64 工具对扫描件仍会 success=True + text="" 静默透传——
模型会把「无文字层」误读成「文档内容为空」并自信作答。
守卫规则：成功且文本为空 → 附 metadata.no_text_layer=true + notice 引导
（对话附件改走页面图 / 归档材料如实告知），不改变其余任何路径。
"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest


@pytest.fixture()
def fake_client() -> Any:
    from mcp_server.tools.documents import parsing

    shared = mock.MagicMock()
    with mock.patch.object(parsing, "client", shared):
        yield shared


class TestExtractDocumentTextNoTextLayer:
    def test_scanned_pdf_success_empty_text_gets_no_text_layer(self, fake_client: Any) -> None:
        """本次故障同类场景：扫描件 → 解析成功但空文本，必须显式标注。"""
        from mcp_server.tools.documents.parsing import extract_document_text

        fake_client.upload.return_value = {"success": True, "text": "", "method": "pymupdf", "metadata": {}}

        result = extract_document_text("AAAA", "扫描合同.pdf")

        assert result["metadata"]["no_text_layer"] is True
        assert "notice" in result
        # 引导必须指明两条出路：附件走页图 / 归档材料如实告知
        assert "read_agent_attachment" in result["notice"]
        assert "无文字层" in result["notice"]

    def test_whitespace_text_also_treated_as_empty(self, fake_client: Any) -> None:
        from mcp_server.tools.documents.parsing import extract_document_text

        fake_client.upload.return_value = {"success": True, "text": "  \n\t ", "method": "pymupdf", "metadata": {}}
        result = extract_document_text("AAAA", "blank.pdf")
        assert result["metadata"]["no_text_layer"] is True

    def test_normal_text_passthrough_unchanged(self, fake_client: Any) -> None:
        """回归：有文字层的正常路径零改动（不烧图、不添字段）。"""
        from mcp_server.tools.documents.parsing import extract_document_text

        original = {"success": True, "text": "合同正文……", "method": "pymupdf", "metadata": {"pages": 3}}
        fake_client.upload.return_value = original

        result = extract_document_text("AAAA", "合同.pdf")

        assert result == original

    def test_failure_path_untouched(self, fake_client: Any) -> None:
        """失败路径本就带 error，守卫不介入。"""
        from mcp_server.tools.documents.parsing import extract_document_text

        original = {"success": False, "text": "", "error": "corrupt"}
        fake_client.upload.return_value = original
        assert extract_document_text("AAAA", "坏.pdf") == original

    def test_async_task_response_untouched(self, fake_client: Any) -> None:
        """mineru/textin 异步受理（task_id、尚无 text 字段）不受影响。"""
        from mcp_server.tools.documents.parsing import extract_document_text

        original = {"success": True, "status": "queued", "task_id": "t-1"}
        fake_client.upload.return_value = original
        assert extract_document_text("AAAA", "大扫描件.pdf", backend="mineru") == original


class TestParseDocumentNoTextLayer:
    def test_parse_empty_text_annotated(self, fake_client: Any) -> None:
        from mcp_server.tools.documents.parsing import parse_document

        fake_client.upload.return_value = {"success": True, "text": "", "sections": []}
        result = parse_document("AAAA", "扫描.pdf")
        assert result["metadata"]["no_text_layer"] is True
        assert "notice" in result

    def test_parse_without_text_key_untouched(self, fake_client: Any) -> None:
        """parse 端点无顶层 text 字段时（结构化形态），守卫不判。"""
        from mcp_server.tools.documents.parsing import parse_document

        original = {"success": True, "sections": [{"type": "paragraph", "text": "内容"}]}
        fake_client.upload.return_value = original
        assert parse_document("AAAA", "合同.pdf") == original
