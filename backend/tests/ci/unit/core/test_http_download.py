"""core/http/download.py 单元测试。

覆盖 Content-Disposition 统一实现的纯逻辑（中文名 / 引号+CRLF / ASCII 名三类）、
build_download_response，以及三处既有实现（documents 工厂、media_protected、
message_hub inbox）对 core 的委托关系。
"""

from __future__ import annotations

from urllib.parse import quote

from django.http import HttpResponse

from apps.core.http.download import build_download_response, content_disposition


class TestContentDisposition:
    """content_disposition 纯逻辑。"""

    def test_ascii_filename(self) -> None:
        """ASCII 文件名：双形态（filename= 与 filename*=）均给出，值一致。"""
        value = content_disposition("report.pdf")
        assert value == "attachment; filename=\"report.pdf\"; filename*=UTF-8''report.pdf"

    def test_inline_flag(self) -> None:
        """inline=True 时语义切换为 inline，其余结构不变。"""
        value = content_disposition("report.pdf", inline=True)
        assert value.startswith("inline; ")
        assert 'filename="report.pdf"' in value
        assert "filename*=UTF-8''report.pdf" in value

    def test_chinese_filename(self) -> None:
        """中文文件名：整体百分号编码，ASCII 回退段可安全放入 quoted-string。"""
        name = "委托书（测试）.docx"
        value = content_disposition(name)
        quoted = quote(name)
        assert value == f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
        # ASCII 回退段不含原始中文字符
        ascii_part = value.split('filename="', 1)[1].split('"', 1)[0]
        ascii_part.encode("ascii", errors="strict").decode()
        assert "委托" not in ascii_part

    def test_quotes_and_crlf_are_percent_encoded(self) -> None:
        """文件名含引号 / CRLF：编码为 %22 / %0D%0A，不产生裸引号或换行（防响应头注入）。"""
        name = '材料"1".pdf\r\nX-Evil: 1'
        value = content_disposition(name)
        assert "%22" in value
        assert "%0D%0A" in value
        assert "\r" not in value
        assert "\n" not in value
        # 除 filename="..." 的两个定界引号外无其他引号
        assert value.count('"') == 2

    def test_space_and_uppercase_extension(self) -> None:
        """空格编码为 %20；扩展名大小写不敏感由调用方白名单保证，此处只做编码。"""
        value = content_disposition("a b.PDF")
        assert 'filename="a%20b.PDF"' in value
        assert "filename*=UTF-8''a%20b.PDF" in value


class TestBuildDownloadResponse:
    def test_attachment_response(self) -> None:
        response = build_download_response(b"docx-bytes", "起诉状.docx", "application/vnd.ms-word")
        assert isinstance(response, HttpResponse)
        assert response.status_code == 200
        assert response.content == b"docx-bytes"
        assert response["Content-Type"] == "application/vnd.ms-word"
        assert response["Content-Disposition"] == content_disposition("起诉状.docx")

    def test_inline_response(self) -> None:
        response = build_download_response(b"%PDF-1.4", "评估报告.pdf", "application/pdf", inline=True)
        assert response["Content-Disposition"].startswith("inline; ")
        assert quote("评估报告.pdf") in response["Content-Disposition"]


class TestExistingImplementationsDelegateToCore:
    """解耦（2026-10-19）回归：三份既有 RFC 5987 实现统一委托 core，语义不变。"""

    def test_documents_factory_delegates(self) -> None:
        from apps.documents.api.download_response_factory import build_download_response as docs_build

        response = docs_build(content=b"x", filename="合同.docx", content_type="application/octet-stream")
        assert response["Content-Disposition"] == content_disposition("合同.docx")

    def test_media_protected_disposition_delegates(self) -> None:
        from apps.core.api.media_protected import _attachment_disposition

        assert _attachment_disposition("证据.zip") == content_disposition("证据.zip")

    def test_inbox_disposition_delegates(self) -> None:
        from apps.message_hub.api.inbox_api import _build_content_disposition

        assert _build_content_disposition("attachment", "附件.pdf") == content_disposition("附件.pdf")
        assert _build_content_disposition("inline", "附件.pdf") == content_disposition("附件.pdf", inline=True)
