"""MineruBackend 测试（核心 — mock httpx）"""

import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.document_parsing.exceptions import MineruAPIError, ParsingTimeoutError
from apps.document_parsing.protocols.document_parser_protocol import (
    ParsedDocument,
    TextExtractionResult,
)
from apps.document_parsing.services.backends.mineru_backend import MineruBackend

_PATCH_PREFIX = "apps.document_parsing.services.backends.mineru_backend"


def _mock_response(status_code: int = 200, json_data: dict = None, content: bytes = b""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _make_backend(api_key: str = "test-key") -> MineruBackend:
    with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
        return MineruBackend(api_key=api_key)


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    """创建包含指定文件的 ZIP bytes。files: {filename: content}"""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ── __init__ ─────────────────────────────────────────────────────


class TestInit:
    def test_api_key_from_param(self) -> None:
        with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
            backend = MineruBackend(api_key="my-key")
        assert backend.api_key == "my-key"

    def test_api_key_from_config(self) -> None:
        with patch(f"{_PATCH_PREFIX}.get_sync_http_client"), patch(
            f"{_PATCH_PREFIX}._config_service"
        ) as mock_cfg:
            mock_cfg.get_value_internal.return_value = "cfg-key"
            backend = MineruBackend()
        assert backend.api_key == "cfg-key"

    def test_no_api_key_raises(self) -> None:
        with patch(f"{_PATCH_PREFIX}.get_sync_http_client"), patch(
            f"{_PATCH_PREFIX}._config_service"
        ) as mock_cfg:
            mock_cfg.get_value_internal.return_value = None
            with pytest.raises(ValueError, match="未配置 MinerU API Key"):
                MineruBackend()

    def test_custom_timeout(self) -> None:
        with patch(f"{_PATCH_PREFIX}.get_sync_http_client"):
            backend = MineruBackend(api_key="k", timeout=60)
        assert backend.timeout == 60


# ── get_supported_formats ────────────────────────────────────────


class TestGetSupportedFormats:
    def test_returns_all_formats(self) -> None:
        backend = _make_backend()
        fmts = backend.get_supported_formats()
        assert "pdf" in fmts
        assert "docx" in fmts
        assert "jpg" in fmts
        assert len(fmts) >= 10


# ── _upload_file ─────────────────────────────────────────────────


class TestUploadFile:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()

        batch_resp = _mock_response(200, {
            "code": 0,
            "data": {
                "batch_id": "batch-123",
                "file_urls": ["https://oss.example.com/upload?sig=abc"],
            },
        })
        put_resp = _mock_response(200)
        mock_client.post.return_value = batch_resp
        mock_client.put.return_value = put_resp

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            batch_id = backend._upload_file(str(pdf))

        assert batch_id == "batch-123"
        mock_client.post.assert_called_once()
        mock_client.put.assert_called_once()

    def test_batch_api_error_code(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_response(200, {
            "code": -10002,
            "msg": "field missing",
        })

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="获取上传 URL 失败"):
                backend._upload_file(str(pdf))

    def test_empty_file_urls(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_response(200, {
            "code": 0,
            "data": {"batch_id": "b1", "file_urls": []},
        })

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="未获取到上传 URL"):
                backend._upload_file(str(pdf))

    def test_http_error(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        import httpx
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="HTTP 请求失败"):
                backend._upload_file(str(pdf))


# ── _poll_batch_result ───────────────────────────────────────────


class TestPollBatchResult:
    def test_done_immediately(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, {
            "code": 0,
            "data": {
                "extract_result": [{
                    "state": "done",
                    "full_zip_url": "https://example.com/result.zip",
                    "file_name": "test.pdf",
                }],
            },
        })

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client), \
             patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend._poll_batch_result("batch-123")

        assert result["state"] == "done"
        assert result["full_zip_url"] == "https://example.com/result.zip"

    def test_failed_state(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, {
            "code": 0,
            "data": {
                "extract_result": [{
                    "state": "failed",
                    "err_msg": "corrupted file",
                }],
            },
        })

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client), \
             patch(f"{_PATCH_PREFIX}.time.sleep"):
            with pytest.raises(MineruAPIError, match="corrupted file"):
                backend._poll_batch_result("batch-123")

    def test_waiting_then_done(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_response(200, {
                    "code": 0,
                    "data": {"extract_result": []},
                })
            return _mock_response(200, {
                "code": 0,
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://example.com/result.zip",
                    }],
                },
            })

        mock_client.get.side_effect = side_effect

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client), \
             patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend._poll_batch_result("batch-123")

        assert result["state"] == "done"
        assert call_count == 2

    def test_api_error_code(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, {
            "code": -10002,
            "msg": "not found",
        })

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client), \
             patch(f"{_PATCH_PREFIX}.time.sleep"):
            with pytest.raises(MineruAPIError, match="查询结果失败"):
                backend._poll_batch_result("batch-123")

    def test_http_error_retries(self) -> None:
        import httpx
        backend = _make_backend()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("timeout")
            return _mock_response(200, {
                "code": 0,
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://example.com/result.zip",
                    }],
                },
            })

        mock_client = MagicMock()
        mock_client.get.side_effect = side_effect

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client), \
             patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend._poll_batch_result("batch-123")

        assert result["state"] == "done"
        assert call_count == 2

    def test_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _make_backend()
        backend.POLL_TIMEOUT = 0  # 立即超时

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, {
            "code": 0,
            "data": {"extract_result": [{"state": "running"}]},
        })

        import time as time_mod
        original_time = time_mod.time
        # 让 elapsed 始终大于 POLL_TIMEOUT
        monkeypatch.setattr(f"{_PATCH_PREFIX}.time.time", lambda: original_time() + 999)
        monkeypatch.setattr(f"{_PATCH_PREFIX}.time.sleep", lambda _: None)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(ParsingTimeoutError, match="超时"):
                backend._poll_batch_result("batch-123")


# ── _parse_result_zip ────────────────────────────────────────────


class TestParseResultZip:
    def test_with_content_list_json(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({
            "result/test_content_list.json": json.dumps([
                {"type": "text", "text": "第一段"},
                {"type": "table", "text": "表格数据"},
                {"type": "text", "text": "第二段"},
            ]),
            "result/output.md": "# 标题\n\n正文",
        })

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, content=zip_bytes)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert isinstance(result, ParsedDocument)
        assert "第一段" in result.text
        assert "第二段" in result.text
        assert result.parse_method == "mineru"

    def test_with_markdown_only(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({
            "result/output.md": "# 标题\n\n这是正文内容",
        })

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, content=zip_bytes)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            result = backend._parse_result_zip(
                "https://example.com/result.zip",
                return_markdown=True,
            )

        assert result.markdown == "# 标题\n\n这是正文内容"
        assert "正文内容" in result.text

    def test_with_images(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({
            "result/output.md": "text",
            "result/img_0.jpg": b"\xff\xd8\xff\xe0",
            "result/img_1.png": b"\x89PNG",
        })

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, content=zip_bytes)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            result = backend._parse_result_zip(
                "https://example.com/result.zip",
                extract_images=True,
            )

        assert result.images is not None
        assert len(result.images) == 2
        assert result.metadata["has_images"] is True
        assert result.metadata["image_count"] == 2

    def test_no_images_extract_images_false(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({"result/output.md": "text"})

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, content=zip_bytes)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            result = backend._parse_result_zip(
                "https://example.com/result.zip",
                extract_images=False,
            )

        assert result.images is None

    def test_bad_zip_raises(self) -> None:
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, content=b"not a zip")

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="ZIP 文件损坏"):
                backend._parse_result_zip("https://example.com/result.zip")

    def test_empty_zip_no_text(self) -> None:
        backend = _make_backend()
        zip_bytes = _make_zip_bytes({"result/readme.txt": "no useful content"})

        mock_client = MagicMock()
        mock_client.get.return_value = _mock_response(200, content=zip_bytes)

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            result = backend._parse_result_zip("https://example.com/result.zip")

        assert result.text == ""


# ── _extract_text_from_content_list ──────────────────────────────


class TestExtractTextFromContentList:
    def test_normal(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text(json.dumps([
            {"type": "text", "text": "段落一"},
            {"type": "table", "text": "表格"},
            {"type": "text", "text": "段落二"},
        ]))

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == "段落一\n段落二"

    def test_empty_list(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text("[]")

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == ""

    def test_no_text_blocks(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text(json.dumps([
            {"type": "table", "text": "表格内容"},
            {"type": "image", "text": ""},
        ]))

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == ""

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        cl = tmp_path / "content_list.json"
        cl.write_text("not json!!!")

        backend = _make_backend()
        text = backend._extract_text_from_content_list(cl)
        assert text == ""


# ── extract_text ─────────────────────────────────────────────────


class TestExtractText:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_result = ParsedDocument(text="hello world", parse_method="mineru")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf))

        assert isinstance(result, TextExtractionResult)
        assert result.success is True
        assert result.text == "hello world"
        assert result.method == "mineru"

    def test_max_length_truncates(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_result = ParsedDocument(text="a" * 1000, parse_method="mineru")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf), max_length=10)

        assert len(result.text) == 10

    def test_failure_returns_error_result(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()

        with patch.object(backend, "parse_document", side_effect=Exception("boom")):
            result = backend.extract_text(str(pdf))

        assert result.success is False
        assert result.text == ""
        assert "boom" in result.metadata["error"]


# ── parse_document (端到端) ──────────────────────────────────────


class TestParseDocument:
    def test_file_not_found(self) -> None:
        backend = _make_backend()
        with pytest.raises(FileNotFoundError):
            backend.parse_document("/nonexistent/file.pdf")

    def test_full_flow(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        zip_bytes = _make_zip_bytes({
            "result/test_content_list.json": json.dumps([
                {"type": "text", "text": "解析成功"},
            ]),
            "result/output.md": "# 成功",
        })

        mock_client = MagicMock()
        # batch API
        mock_client.post.return_value = _mock_response(200, {
            "code": 0,
            "data": {
                "batch_id": "batch-456",
                "file_urls": ["https://oss.example.com/upload"],
            },
        })
        # PUT upload
        mock_client.put.return_value = _mock_response(200)
        # GET: poll → done, then zip download
        poll_resp = _mock_response(200, {
            "code": 0,
            "data": {
                "extract_result": [{
                    "state": "done",
                    "full_zip_url": "https://example.com/result.zip",
                }],
            },
        })
        zip_resp = _mock_response(200, content=zip_bytes)

        def get_side_effect(url, **kwargs):
            if "extract-results" in url:
                return poll_resp
            return zip_resp

        mock_client.get.side_effect = get_side_effect

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client), \
             patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend.parse_document(str(pdf), return_markdown=True)

        assert "解析成功" in result.text
        assert result.markdown == "# 成功"
        assert result.parse_method == "mineru"

    def test_mineru_error_reraised(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_response(200, {
            "code": -1,
            "msg": "api error",
        })

        with patch(f"{_PATCH_PREFIX}.get_sync_http_client", return_value=mock_client):
            with pytest.raises(MineruAPIError, match="api error"):
                backend.parse_document(str(pdf))

    def test_unexpected_error_wrapped(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend = _make_backend()
        with patch.object(backend, "_upload_file", side_effect=RuntimeError("unexpected")):
            with pytest.raises(MineruAPIError, match="unexpected"):
                backend.parse_document(str(pdf))
