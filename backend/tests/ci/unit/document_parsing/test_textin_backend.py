"""TextinBackend 测试（核心 — mock xparse-client SDK + httpx）"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import xparse_client as xc

from apps.document_parsing.exceptions import FileFormatNotSupportedError, ParsingTimeoutError, TextinAPIError
from apps.document_parsing.protocols.document_parser_protocol import ParsedDocument, TextExtractionResult
from apps.document_parsing.services.backends.textin_backend import TextinBackend

_PATCH_PREFIX = "apps.document_parsing.services.backends.textin_backend"


# ── 工具函数 ──────────────────────────────────────────────────────


def _make_backend(
    app_id: str = "test-app",
    secret_code: str = "test-secret",  # pragma: allowlist secret
    *,
    timeout: int = 30,
) -> tuple[TextinBackend, MagicMock]:
    """构造一个 mock 掉 SDK 的 TextinBackend，返回 (backend, mock_client)。"""
    with patch(f"{_PATCH_PREFIX}.xc.XParseClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        backend = TextinBackend(app_id=app_id, secret_code=secret_code, timeout=timeout)
    return backend, mock_client


def _make_job_response(
    status: str = "completed",
    result_url: str | None = "https://example.com/result.json",
    job_id: str = "job-123",
    file_id: str | None = "file-456",
    error_message: str | None = None,
) -> xc.JobStatusResponse:
    return xc.JobStatusResponse(
        job_id=job_id,
        status=status,
        result_url=result_url,
        file_id=file_id,
        error_message=error_message,
    )


def _mock_httpx_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
    return resp


# ── __init__ ─────────────────────────────────────────────────────


class TestInit:
    def test_credentials_from_param(self) -> None:
        backend, _ = _make_backend(app_id="my-app", secret_code="my-secret")  # pragma: allowlist secret
        assert backend.app_id == "my-app"
        assert backend.secret_code == "my-secret"  # pragma: allowlist secret

    def test_credentials_from_config(self) -> None:
        with patch(f"{_PATCH_PREFIX}.xc.XParseClient"), patch(f"{_PATCH_PREFIX}._config_service") as mock_cfg:
            mock_cfg.get_value_internal.side_effect = ["cfg-app", "cfg-secret"]  # pragma: allowlist secret
            backend = TextinBackend()
        assert backend.app_id == "cfg-app"
        assert backend.secret_code == "cfg-secret"  # pragma: allowlist secret

    def test_missing_app_id_raises(self) -> None:
        with patch(f"{_PATCH_PREFIX}.xc.XParseClient"), patch(f"{_PATCH_PREFIX}._config_service") as mock_cfg:
            mock_cfg.get_value_internal.return_value = None
            with pytest.raises(ValueError, match="未配置 TextinParse 凭证"):
                TextinBackend()

    def test_missing_secret_code_raises(self) -> None:
        with patch(f"{_PATCH_PREFIX}.xc.XParseClient"), patch(f"{_PATCH_PREFIX}._config_service") as mock_cfg:
            mock_cfg.get_value_internal.side_effect = ["has-app", None]
            with pytest.raises(ValueError, match="未配置 TextinParse 凭证"):
                TextinBackend()

    def test_custom_timeout(self) -> None:
        backend, _ = _make_backend(timeout=90)
        assert backend.timeout == 90

    def test_sdk_init_failure_raises_textin_error(self) -> None:
        with patch(f"{_PATCH_PREFIX}.xc.XParseClient", side_effect=xc.XParseClientError("boom")):
            with pytest.raises(TextinAPIError, match="初始化 TextinParse SDK 失败"):
                TextinBackend(app_id="a", secret_code="s")

    def test_requires_async_execution_flag(self) -> None:
        backend, _ = _make_backend()
        assert backend.requires_async_execution is True


# ── get_supported_formats ────────────────────────────────────────


class TestGetSupportedFormats:
    def test_returns_broad_formats(self) -> None:
        backend, _ = _make_backend()
        fmts = backend.get_supported_formats()
        # TextinParse 覆盖比 MinerU 更广
        assert "pdf" in fmts
        assert "docx" in fmts
        assert "ofd" in fmts
        assert "rtf" in fmts
        assert "csv" in fmts
        assert "txt" in fmts
        assert "jpg" in fmts
        assert len(fmts) >= 15


# ── _create_job ─────────────────────────────────────────────────


class TestCreateJob:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, mock_client = _make_backend()
        mock_client.parse.create_job.return_value = MagicMock(job_id="job-abc")

        job_id = backend._create_job(pdf, extract_tables=True)

        assert job_id == "job-abc"
        mock_client.parse.create_job.assert_called_once()

    def test_sdk_error_wrapped(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, mock_client = _make_backend()
        mock_client.parse.create_job.side_effect = xc.UnsupportedFileTypeError("bad type")

        with pytest.raises(FileFormatNotSupportedError, match="不支持的文件格式"):
            backend._create_job(pdf)


# ── _poll_job ───────────────────────────────────────────────────


class TestPollJob:
    def test_completed_immediately(self) -> None:
        backend, mock_client = _make_backend()
        mock_client.parse.get_job.return_value = _make_job_response(status="completed")

        with patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend._poll_job("job-123")

        assert result.status == "completed"
        assert result.result_url == "https://example.com/result.json"

    def test_partial_completed_returns(self) -> None:
        backend, mock_client = _make_backend()
        mock_client.parse.get_job.return_value = _make_job_response(
            status="partial_completed", error_message="some pages failed"
        )

        with patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend._poll_job("job-123")

        assert result.status == "partial_completed"

    @pytest.mark.parametrize("terminal_status", ["failed", "stopped", "deleted"])
    def test_failed_status_raises(self, terminal_status: str) -> None:
        backend, mock_client = _make_backend()
        mock_client.parse.get_job.return_value = _make_job_response(status=terminal_status, error_message="boom")

        with patch(f"{_PATCH_PREFIX}.time.sleep"):
            with pytest.raises(TextinAPIError, match="boom"):
                backend._poll_job("job-123")

    def test_pending_then_completed(self) -> None:
        backend, mock_client = _make_backend()
        call_count = 0

        def side_effect(*, job_id: str):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_job_response(status="running")
            return _make_job_response(status="completed")

        mock_client.parse.get_job.side_effect = side_effect

        with patch(f"{_PATCH_PREFIX}.time.sleep"):
            result = backend._poll_job("job-123")

        assert result.status == "completed"
        assert call_count == 2

    def test_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend, _ = _make_backend()
        backend.POLL_TIMEOUT = 0  # 立即超时

        import time as time_mod

        original_time = time_mod.time
        monkeypatch.setattr(f"{_PATCH_PREFIX}.time.time", lambda: original_time() + 999)
        monkeypatch.setattr(f"{_PATCH_PREFIX}.time.sleep", lambda _: None)

        with pytest.raises(ParsingTimeoutError, match="超时"):
            backend._poll_job("job-123")

    def test_sdk_error_wrapped(self) -> None:
        backend, mock_client = _make_backend()
        mock_client.parse.get_job.side_effect = xc.AuthenticationError("bad token")

        with patch(f"{_PATCH_PREFIX}.time.sleep"):
            with pytest.raises(TextinAPIError, match="认证失败"):
                backend._poll_job("job-123")


# ── _extract_text_from_elements ─────────────────────────────────


class TestExtractTextFromElements:
    def test_narrative_and_title(self) -> None:
        backend, _ = _make_backend()
        elements = [
            {"type": "NarrativeText", "text": "第一段正文"},
            {"type": "Title", "text": "章节标题"},
            {"type": "NarrativeText", "text": "第二段正文"},
        ]
        assert backend._extract_text_from_elements(elements) == "第一段正文\n章节标题\n第二段正文"

    def test_excludes_footer(self) -> None:
        backend, _ = _make_backend()
        elements = [
            {"type": "NarrativeText", "text": "正文"},
            {"type": "Footer", "text": "12"},
        ]
        assert backend._extract_text_from_elements(elements) == "正文"

    def test_excludes_header(self) -> None:
        backend, _ = _make_backend()
        elements = [
            {"type": "Header", "text": "机密文件"},
            {"type": "NarrativeText", "text": "正文"},
        ]
        assert backend._extract_text_from_elements(elements) == "正文"

    def test_empty_list(self) -> None:
        backend, _ = _make_backend()
        assert backend._extract_text_from_elements([]) == ""

    def test_non_dict_elements_skipped(self) -> None:
        backend, _ = _make_backend()
        elements = ["not a dict", None, 42, {"type": "NarrativeText", "text": "ok"}]
        assert backend._extract_text_from_elements(elements) == "ok"

    def test_empty_text_skipped(self) -> None:
        backend, _ = _make_backend()
        elements = [
            {"type": "NarrativeText", "text": ""},
            {"type": "NarrativeText", "text": "有效"},
        ]
        assert backend._extract_text_from_elements(elements) == "有效"

    def test_strips_markdown_bold(self) -> None:
        backend, _ = _make_backend()
        elements = [{"type": "NarrativeText", "text": "这是**加粗**文字"}]
        assert backend._extract_text_from_elements(elements) == "这是加粗文字"

    def test_strips_markdown_italic(self) -> None:
        backend, _ = _make_backend()
        elements = [{"type": "NarrativeText", "text": "这是*斜体*文字"}]
        assert backend._extract_text_from_elements(elements) == "这是斜体文字"

    def test_strips_markdown_underscore(self) -> None:
        backend, _ = _make_backend()
        elements = [{"type": "NarrativeText", "text": "__粗体__和_斜体_"}]
        assert backend._extract_text_from_elements(elements) == "粗体和斜体"

    def test_fallback_excludes_header_footer(self) -> None:
        """无 NarrativeText/Title 时 fallback，但仍排除 Header/Footer"""
        backend, _ = _make_backend()
        elements = [
            {"type": "Table", "text": "表格内容"},
            {"type": "Header", "text": "页眉"},
            {"type": "Footer", "text": "13"},
            {"type": "ListItem", "text": "列表项"},
        ]
        text = backend._extract_text_from_elements(elements)
        assert "表格内容" in text
        assert "列表项" in text
        assert "页眉" not in text
        assert "13" not in text


# ── _parse_result ───────────────────────────────────────────────


class TestParseResult:
    def test_normal(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "# 标题\n\n正文内容",
            "elements": [
                {"type": "NarrativeText", "text": "正文内容"},
            ],
            "metadata": {"page_count": 3},
            "success_count": 1,
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, return_markdown=True)

        assert isinstance(result, ParsedDocument)
        assert result.text == "正文内容"
        assert result.markdown == "# 标题\n\n正文内容"
        assert result.parse_method == "textin"
        assert result.metadata["job_id"] == "job-123"
        assert result.metadata["file_id"] == "file-456"
        assert result.metadata["page_count"] == 3
        assert result.metadata["success_count"] == 1
        assert result.metadata["element_count"] == 1
        assert result.images is None

    def test_strips_page_numbers_from_markdown(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "正文\n\n12\n\n更多正文",
            "elements": [{"type": "NarrativeText", "text": "正文"}],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, return_markdown=True)

        # 独立数字行（页码）被删除
        assert "\n12\n" not in (result.markdown or "")
        assert "正文" in result.markdown

    def test_strips_html_comments_from_markdown(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "<!-- page: 1 -->正文内容",
            "elements": [{"type": "NarrativeText", "text": "正文内容"}],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, return_markdown=True)

        assert "<!--" not in (result.markdown or "")

    def test_strips_known_header_lines(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "机密文件\n\n正文\n\n机密文件",
            "elements": [
                {"type": "Header", "text": "机密文件"},
                {"type": "NarrativeText", "text": "正文"},
            ],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, return_markdown=True)

        # 页眉文本行被清理
        assert "机密文件" not in (result.markdown or "")
        assert "正文" in result.markdown

    def test_no_result_url_raises(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response(result_url=None)

        with pytest.raises(TextinAPIError, match="未返回 result_url"):
            backend._parse_result(job_result)

    def test_httpx_error_raises(self) -> None:
        import httpx

        backend, _ = _make_backend()
        job_result = _make_job_response()

        with patch(f"{_PATCH_PREFIX}.httpx.get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(TextinAPIError, match="下载结果文件失败"):
                backend._parse_result(job_result)

    def test_invalid_json_raises(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError("not json")

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=resp):
            with pytest.raises(TextinAPIError, match="解析结果 JSON 失败"):
                backend._parse_result(job_result)

    def test_return_markdown_false_omits_markdown(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "# 标题",
            "elements": [{"type": "NarrativeText", "text": "正文"}],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, return_markdown=False)

        assert result.markdown is None
        assert result.text == "正文"

    def test_fallback_to_markdown_when_no_elements(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "仅 markdown 内容",
            "elements": [],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result)

        # 无 elements 时 fallback 到 markdown 作为纯文本
        assert result.text == "仅 markdown 内容"

    def test_has_images_metadata(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "正文",
            "elements": [
                {"type": "NarrativeText", "text": "正文"},
                {"type": "image", "text": ""},
            ],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, extract_images=True)

        assert result.metadata["has_images"] is True

    def test_has_images_false_when_extract_images_false(self) -> None:
        backend, _ = _make_backend()
        job_result = _make_job_response()
        result_data = {
            "markdown": "正文",
            "elements": [
                {"type": "image", "text": ""},
            ],
            "metadata": {},
        }

        with patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)):
            result = backend._parse_result(job_result, extract_images=False)

        assert result.metadata["has_images"] is False


# ── extract_text ────────────────────────────────────────────────


class TestExtractText:
    def test_success(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, _ = _make_backend()
        mock_result = ParsedDocument(text="hello world", parse_method="textin")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf))

        assert isinstance(result, TextExtractionResult)
        assert result.success is True
        assert result.text == "hello world"
        assert result.method == "textin"

    def test_max_length_truncates(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, _ = _make_backend()
        mock_result = ParsedDocument(text="a" * 500, parse_method="textin")

        with patch.object(backend, "parse_document", return_value=mock_result):
            result = backend.extract_text(str(pdf), max_length=10)

        assert len(result.text) == 10

    def test_failure_returns_error_result(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, _ = _make_backend()

        with patch.object(backend, "parse_document", side_effect=Exception("boom")):
            result = backend.extract_text(str(pdf))

        assert result.success is False
        assert result.text == ""
        assert "boom" in result.metadata["error"]


# ── parse_document (端到端) ──────────────────────────────────────


class TestParseDocument:
    def test_file_not_found(self) -> None:
        backend, _ = _make_backend()
        with pytest.raises(FileNotFoundError):
            backend.parse_document("/nonexistent/file.pdf")

    def test_full_flow(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, mock_client = _make_backend()
        mock_client.parse.create_job.return_value = MagicMock(job_id="job-full")
        mock_client.parse.get_job.return_value = _make_job_response(status="completed")

        result_data = {
            "markdown": "# 成功\n\n解析正文",
            "elements": [{"type": "NarrativeText", "text": "解析正文"}],
            "metadata": {"page_count": 2},
            "success_count": 1,
        }

        with (
            patch(f"{_PATCH_PREFIX}.time.sleep"),
            patch(f"{_PATCH_PREFIX}.httpx.get", return_value=_mock_httpx_response(200, result_data)),
        ):
            result = backend.parse_document(str(pdf), return_markdown=True)

        assert "解析正文" in result.text
        assert result.markdown == "# 成功\n\n解析正文"
        assert result.parse_method == "textin"
        assert result.metadata["job_id"] == "job-123"
        mock_client.parse.create_job.assert_called_once()
        mock_client.parse.get_job.assert_called_once()

    def test_textin_error_reraised(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, _ = _make_backend()

        with patch.object(backend, "_create_job", side_effect=TextinAPIError("api broken")):
            with pytest.raises(TextinAPIError, match="api broken"):
                backend.parse_document(str(pdf))

    def test_timeout_reraised(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, _ = _make_backend()

        with patch.object(backend, "_create_job", side_effect=ParsingTimeoutError("too slow")):
            with pytest.raises(ParsingTimeoutError, match="too slow"):
                backend.parse_document(str(pdf))

    def test_unexpected_error_wrapped(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, _ = _make_backend()

        with patch.object(backend, "_create_job", side_effect=RuntimeError("unexpected")):
            with pytest.raises(TextinAPIError, match="unexpected"):
                backend.parse_document(str(pdf))

    def test_sdk_error_wrapped(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        backend, mock_client = _make_backend()
        mock_client.parse.create_job.side_effect = xc.RateLimitError("too fast")

        with pytest.raises(TextinAPIError, match="限流"):
            backend.parse_document(str(pdf))


# ── _wrap_sdk_error ─────────────────────────────────────────────


class TestWrapSdkError:
    def test_authentication_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.AuthenticationError("bad key"))
        assert isinstance(wrapped, TextinAPIError)
        assert "认证失败" in str(wrapped)

    def test_insufficient_balance_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.InsufficientBalanceError("no money"))
        assert isinstance(wrapped, TextinAPIError)
        assert "余额不足" in str(wrapped)

    def test_password_protected_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.PasswordProtectedError("encrypted"))
        assert isinstance(wrapped, TextinAPIError)
        assert "密码保护" in str(wrapped)

    def test_corrupted_file_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.CorruptedFileError("broken"))
        assert isinstance(wrapped, TextinAPIError)
        assert "文件损坏" in str(wrapped)

    def test_unsupported_file_type_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.UnsupportedFileTypeError("xyz"))
        assert isinstance(wrapped, FileFormatNotSupportedError)
        assert "不支持的文件格式" in str(wrapped)

    def test_file_size_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.FileSizeError("too big"))
        assert isinstance(wrapped, TextinAPIError)
        assert "文件过大" in str(wrapped)

    def test_rate_limit_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.RateLimitError("slow down"))
        assert isinstance(wrapped, TextinAPIError)
        assert "限流" in str(wrapped)

    def test_request_timeout_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.RequestTimeoutError("timed out"))
        assert isinstance(wrapped, ParsingTimeoutError)
        assert "请求超时" in str(wrapped)

    def test_api_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.APIError("server error"))
        assert isinstance(wrapped, TextinAPIError)
        assert "API 调用失败" in str(wrapped)

    def test_configuration_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.ConfigurationError("bad config"))
        assert isinstance(wrapped, TextinAPIError)
        assert "SDK 配置错误" in str(wrapped)

    def test_generic_xparse_error(self) -> None:
        backend, _ = _make_backend()
        wrapped = backend._wrap_sdk_error(xc.XParseClientError("unknown"))
        assert isinstance(wrapped, TextinAPIError)
        assert "解析失败" in str(wrapped)
