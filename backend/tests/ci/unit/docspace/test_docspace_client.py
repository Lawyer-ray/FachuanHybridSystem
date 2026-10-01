"""DocSpaceClient 单元测试。

用 httpx.MockTransport 截获 DocSpace REST 调用，锁定：
- 请求契约：URL 拼接、Bearer 认证头、HTTP 方法；
- 响应契约：DocSpace JSON（fileExst/viewUrl 等驼峰字段）到 DocSpaceFile 的映射；
- 错误契约：空响应 ValueError、非 2xx 抛 HTTPStatusError、下载文件名回退。

不依赖真实网络与 DocSpace 实例。
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Callable
from xml.etree import ElementTree

import httpx
import pytest

from apps.docspace.services.docspace_client import DocSpaceClient, _extract_filename, _make_empty_docx


def _file_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": 42,
        "title": "裁决书.docx",
        "folderId": 7,
        "fileExst": "docx",
        "pureContentLength": 1024,
        "webUrl": "https://ds.example.com/editor",
        "viewUrl": "https://ds.example.com/download",
    }
    entry.update(overrides)
    return entry


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    async_: bool = False,
) -> list[httpx.Request]:
    """把 docspace_client 内部构造的 httpx 客户端替换为 MockTransport。

    返回捕获到的请求列表，供断言请求契约。
    """
    seen: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    attr = "AsyncClient" if async_ else "Client"
    real_cls = getattr(httpx, attr)

    def factory(**kwargs: Any) -> Any:
        kwargs["transport"] = httpx.MockTransport(recording_handler)
        return real_cls(**kwargs)

    monkeypatch.setattr(f"apps.docspace.services.docspace_client.httpx.{attr}", factory)
    return seen


@pytest.fixture
def client() -> DocSpaceClient:
    return DocSpaceClient("https://ds.example.com", "tok-123")


class TestUpload:
    def test_upload_file_success(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://ds.example.com/api/2.0/files/7/upload"
            assert request.headers["Authorization"] == "Bearer tok-123"
            return httpx.Response(200, json={"response": [_file_entry()]})

        seen = _install_transport(monkeypatch, handler)
        result = client.upload_file(7, "a.pdf", b"%PDF-1.4 fake")

        assert result.id == 42
        assert result.title == "裁决书.docx"
        assert result.folder_id == 7
        assert result.file_ext == "docx"
        assert result.content_length == 1024
        assert result.web_url == "https://ds.example.com/editor"
        assert result.download_url == "https://ds.example.com/download"
        assert len(seen) == 1

    def test_upload_file_empty_response_raises(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_transport(monkeypatch, lambda request: httpx.Response(200, json={"response": []}))
        with pytest.raises(ValueError, match="返回空结果"):
            client.upload_file(7, "a.pdf", b"x")

    def test_upload_file_http_error_raises(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_transport(monkeypatch, lambda request: httpx.Response(500, json={"error": "boom"}))
        with pytest.raises(httpx.HTTPStatusError):
            client.upload_file(7, "a.pdf", b"x")

    def test_create_empty_docx_posts_valid_zip(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # insert 接口：multipart 上传，文件名在表单里
            assert request.url.path == "/api/2.0/files/7/insert"
            assert request.headers["content-type"].startswith("multipart/form-data")
            return httpx.Response(200, json={"response": _file_entry(title="新建文档.docx")})

        _install_transport(monkeypatch, handler)
        result = client.create_empty_docx(7)
        assert result.title == "新建文档.docx"


class TestQuery:
    def test_get_file_info(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert str(request.url) == "https://ds.example.com/api/2.0/files/file/42"
            return httpx.Response(200, json={"response": _file_entry()})

        _install_transport(monkeypatch, handler)
        assert client.get_file_info(42).id == 42

    def test_list_files_parses_entries(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://ds.example.com/api/2.0/files/7"
            return httpx.Response(
                200,
                json={"response": {"files": [_file_entry(id=1, title="a.docx"), _file_entry(id=2, title="b.pdf")]}},
            )

        _install_transport(monkeypatch, handler)
        files = client.list_files(7)
        assert [f.id for f in files] == [1, 2]
        assert [f.title for f in files] == ["a.docx", "b.pdf"]

    def test_list_files_empty_folder(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_transport(monkeypatch, lambda request: httpx.Response(200, json={"response": {"files": []}}))
        assert client.list_files(7) == []


class TestDownload:
    def test_download_with_ascii_filename(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://ds.example.com/filehandler.ashx?action=download&fileid=42"
            return httpx.Response(
                200,
                content=b"file-bytes",
                headers={"Content-Disposition": 'attachment; filename="report.pdf"'},
            )

        _install_transport(monkeypatch, handler)
        content, filename = client.download_file(42)
        assert content == b"file-bytes"
        assert filename == "report.pdf"

    def test_download_with_utf8_encoded_filename(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_transport(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                content=b"x",
                headers={"Content-Disposition": "attachment; filename*=UTF-8''%E8%A3%81%E5%86%B3%E4%B9%A6.pdf"},
            ),
        )
        _, filename = client.download_file(42)
        assert filename == "裁决书.pdf"

    def test_download_without_disposition_falls_back(
        self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_transport(monkeypatch, lambda request: httpx.Response(200, content=b"x"))
        _, filename = client.download_file(42)
        assert filename == "file_42"


class TestDelete:
    def test_delete_file_uses_delete_method(self, client: DocSpaceClient, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _install_transport(monkeypatch, lambda request: httpx.Response(200, json={"response": {}}))
        client.delete_file(42)
        assert seen[0].method == "DELETE"


class TestBaseUrl:
    def test_trailing_slashes_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        c = DocSpaceClient("https://ds.example.com///", "tok")
        seen = _install_transport(monkeypatch, lambda request: httpx.Response(200, json={"response": _file_entry()}))
        c.get_file_info(1)
        assert str(seen[0].url).startswith("https://ds.example.com/api/2.0/")


class TestAsyncMethods:
    @pytest.mark.asyncio
    async def test_aupload_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://ds.example.com/api/2.0/files/7/upload"
            return httpx.Response(200, json={"response": [_file_entry(id=9)]})

        _install_transport(monkeypatch, handler, async_=True)
        c = DocSpaceClient("https://ds.example.com", "tok")
        result = await c.aupload_file(7, "a.pdf", b"x")
        assert result.id == 9

    @pytest.mark.asyncio
    async def test_alist_files_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_transport(monkeypatch, lambda request: httpx.Response(200, json={"response": {}}), async_=True)
        c = DocSpaceClient("https://ds.example.com", "tok")
        assert await c.alist_files(7) == []

    @pytest.mark.asyncio
    async def test_adelete_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _install_transport(monkeypatch, lambda request: httpx.Response(200), async_=True)
        c = DocSpaceClient("https://ds.example.com", "tok")
        await c.adelete_file(5)
        assert seen[0].method == "DELETE"


class TestInternalHelpers:
    def test_make_empty_docx_is_valid_ooxml_package(self) -> None:
        payload = _make_empty_docx()
        assert zipfile.is_zipfile(io.BytesIO(payload))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names
            # 三个 part 都是格式良好的 XML
            for name in names:
                ElementTree.fromstring(zf.read(name))

    def test_extract_filename_plain(self) -> None:
        assert _extract_filename('attachment; filename="a.pdf"') == "a.pdf"

    def test_extract_filename_utf8(self) -> None:
        assert _extract_filename("attachment; filename*=UTF-8''%E8%A3%81.pdf") == "裁.pdf"

    def test_extract_filename_missing(self) -> None:
        assert _extract_filename("") == ""
        assert _extract_filename("attachment") == ""
