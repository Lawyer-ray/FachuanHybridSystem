"""parsing_api 端点单元测试。

直接调用 async 视图函数，解析后端与任务调度全部 mock：
覆盖 _needs_async、表单参数解析工具、parse/extract-text 的同步与异步
双路径及异常分支、task 状态查询、records 列表与详情的响应结构。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.document_parsing.api.parsing_api import (
    _form_bool,
    _form_int,
    _form_str,
    _get_task_dispatch_service,
    _needs_async,
    extract_text,
    get_record,
    get_task_status,
    list_records,
    parse_document,
)
from apps.document_parsing.services.task_dispatch_service import DocumentParsingTaskDispatchService

API_MODULE = "apps.document_parsing.api.parsing_api"


def _authed_user() -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=True, id=1)


def _post_request(post: dict[str, str] | None = None, *, user: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(POST=post or {}, user=user)


def _upload(name: str = "doc.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


class TestFactory:
    def test_factory_returns_dispatch_service(self) -> None:
        assert isinstance(_get_task_dispatch_service(), DocumentParsingTaskDispatchService)


class TestNeedsAsync:
    def test_true_when_backend_requires_async(self) -> None:
        parser = SimpleNamespace(requires_async_execution=True)
        with patch(f"{API_MODULE}.get_document_parser", return_value=parser):
            assert _needs_async("mineru") is True

    def test_false_when_backend_sync(self) -> None:
        parser = SimpleNamespace(requires_async_execution=False)
        with patch(f"{API_MODULE}.get_document_parser", return_value=parser):
            assert _needs_async("local") is False

    def test_missing_attr_defaults_false(self) -> None:
        with patch(f"{API_MODULE}.get_document_parser", return_value=object()):
            assert _needs_async("auto") is False


class TestFormHelpers:
    def test_form_str(self) -> None:
        req = _post_request({"backend": "  textin "})
        assert _form_str(req, "backend", "auto") == "textin"
        assert _form_str(_post_request({}), "backend", "auto") == "auto"
        assert _form_str(_post_request({"backend": "   "}), "backend", "auto") == "auto"

    def test_form_bool(self) -> None:
        truthy = _post_request({"a": "true", "b": "1", "c": "yes", "d": "on"})
        for key in ("a", "b", "c", "d"):
            assert _form_bool(truthy, key, False) is True
        falsy = _post_request({"a": "false", "b": "0", "c": "no", "d": "off"})
        for key in ("a", "b", "c", "d"):
            assert _form_bool(falsy, key, True) is False
        assert _form_bool(_post_request({"x": "weird"}), "x", True) is True
        assert _form_bool(_post_request({}), "x", False) is False

    def test_form_int(self) -> None:
        req = _post_request({"n": " 42 ", "neg": "-7", "bad": "x1"})
        assert _form_int(req, "n", None) == 42
        assert _form_int(req, "neg", None) == -7
        assert _form_int(req, "bad", 9) == 9
        assert _form_int(_post_request({}), "n", None) is None


@pytest.mark.asyncio
class TestParseDocumentEndpoint:
    async def test_async_path_returns_task_id(self) -> None:
        dispatch = MagicMock()
        dispatch.submit_parse_task = AsyncMock(return_value="77")
        with (
            patch(f"{API_MODULE}._save_upload", return_value=("saved.pdf", "/tmp/saved.pdf")),
            patch(f"{API_MODULE}._needs_async", return_value=True),
            patch(f"{API_MODULE}._get_task_dispatch_service", return_value=dispatch),
        ):
            resp = await parse_document(
                _post_request({"backend": "mineru"}, user=_authed_user()), file=_upload(), body=None
            )

        assert resp.success is True
        assert resp.task_id == "77"
        assert resp.status == "pending"
        kwargs = dispatch.submit_parse_task.call_args.kwargs
        assert kwargs["backend"] == "mineru"
        assert kwargs["file_name"] == "doc.pdf"
        # created_by 是 get_request_user 解析出的认证用户对象
        assert getattr(kwargs["created_by"], "is_authenticated", False) is True

    async def test_sync_path_returns_parse_result(self) -> None:
        result = SimpleNamespace(text="全文", markdown="# md", metadata={"pages": 2}, parse_method="pymupdf")
        parser = MagicMock()
        parser.parse_document = MagicMock(return_value=result)
        with (
            patch(f"{API_MODULE}._save_upload", return_value=("saved.pdf", "/tmp/saved.pdf")),
            patch(f"{API_MODULE}._needs_async", return_value=False),
            patch(f"{API_MODULE}.get_document_parser", return_value=parser),
        ):
            resp = await parse_document(_post_request({"backend": "local"}), file=_upload(), body=None)

        assert resp.success is True
        assert resp.text == "全文"
        assert resp.markdown == "# md"
        assert resp.metadata == {"pages": 2}
        assert resp.parse_method == "pymupdf"
        assert parser.parse_document.call_args.kwargs["file_type"] == "pdf"

    async def test_body_params_used_when_form_missing(self) -> None:
        """JSON 调用（无 form 字段）从 body schema 取参。"""
        from apps.document_parsing.schemas.parsing_schemas import ParseDocumentRequest

        dispatch = MagicMock()
        dispatch.submit_parse_task = AsyncMock(return_value="78")
        body = ParseDocumentRequest(backend="textin", extract_tables=False, extract_images=True)
        with (
            patch(f"{API_MODULE}._save_upload", return_value=("s.pdf", "/tmp/s.pdf")),
            patch(f"{API_MODULE}._needs_async", return_value=True),
            patch(f"{API_MODULE}._get_task_dispatch_service", return_value=dispatch),
        ):
            resp = await parse_document(_post_request(), file=_upload(), body=body)

        assert resp.task_id == "78"
        kwargs = dispatch.submit_parse_task.call_args.kwargs
        assert kwargs["backend"] == "textin"
        assert kwargs["extract_tables"] is False
        assert kwargs["extract_images"] is True

    async def test_exception_returns_error_envelope(self) -> None:
        with patch(f"{API_MODULE}._save_upload", side_effect=RuntimeError("disk full")):
            resp = await parse_document(_post_request(), file=_upload(), body=None)

        assert resp.success is False
        assert "disk full" in (resp.error or "")


@pytest.mark.asyncio
class TestExtractTextEndpoint:
    async def test_async_path_returns_task_id(self) -> None:
        dispatch = MagicMock()
        dispatch.submit_extract_text_task = AsyncMock(return_value="88")
        with (
            patch(f"{API_MODULE}._save_upload", return_value=("saved.pdf", "/tmp/saved.pdf")),
            patch(f"{API_MODULE}._needs_async", return_value=True),
            patch(f"{API_MODULE}._get_task_dispatch_service", return_value=dispatch),
        ):
            resp = await extract_text(
                _post_request({"backend": "mineru", "max_length": "500"}, user=_authed_user()),
                file=_upload(),
                body=None,
            )

        assert resp.success is True
        assert resp.task_id == "88"
        assert resp.status == "pending"
        kwargs = dispatch.submit_extract_text_task.call_args.kwargs
        assert kwargs["max_length"] == 500
        assert getattr(kwargs["created_by"], "is_authenticated", False) is True

    async def test_sync_path_returns_text(self) -> None:
        result = SimpleNamespace(success=True, text="纯文本", method="pymupdf", metadata={})
        parser = MagicMock()
        parser.extract_text = MagicMock(return_value=result)
        with (
            patch(f"{API_MODULE}._save_upload", return_value=("s.pdf", "/tmp/s.pdf")),
            patch(f"{API_MODULE}._needs_async", return_value=False),
            patch(f"{API_MODULE}.get_document_parser", return_value=parser),
        ):
            resp = await extract_text(_post_request(), file=_upload(), body=None)

        assert resp.success is True
        assert resp.text == "纯文本"
        assert resp.method == "pymupdf"

    async def test_exception_returns_error_envelope(self) -> None:
        with patch(f"{API_MODULE}._save_upload", side_effect=RuntimeError("boom")):
            resp = await extract_text(_post_request(), file=_upload(), body=None)

        assert resp.success is False
        assert resp.text == ""
        assert "boom" in (resp.error or "")


class TestTaskStatusEndpoint:
    def test_returns_service_payload_shape(self) -> None:
        from apps.document_parsing.services.task_status_service import DocumentParsingTaskStatusService

        info = {
            "task_id": "55",
            "status": "success",
            "result": {"success": True, "text": "全文"},
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
        }
        with patch.object(DocumentParsingTaskStatusService, "get_task_status", return_value=info) as mock_status:
            resp = get_task_status(_post_request(user=_authed_user()), task_id="55")

        assert resp.task_id == "55"
        assert resp.status == "success"
        assert resp.result == {"success": True, "text": "全文"}
        assert resp.started_at == "2026-01-01T00:00:00Z"
        mock_status.assert_called_once_with("55", user=_authed_user())

    def test_non_dict_result_coerced_to_none(self) -> None:
        from apps.document_parsing.services.task_status_service import DocumentParsingTaskStatusService

        info = {"task_id": "56", "status": "failure", "result": "plain string", "started_at": None, "finished_at": None}
        with patch.object(DocumentParsingTaskStatusService, "get_task_status", return_value=info):
            resp = get_task_status(_post_request(), task_id="56")

        assert resp.result is None


class TestRecordsEndpoints:
    def test_list_records_maps_service_items(self) -> None:
        from apps.document_parsing.services.record_service import DocumentParsingRecordService

        items = [
            {
                "id": 1,
                "status": "completed",
                "file_name": "a.pdf",
                "file_size": 10,
                "backend_used": "local",
                "error_message": None,
                "text_preview": "预览",
                "created_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z",
            }
        ]
        with patch.object(
            DocumentParsingRecordService,
            "list_records",
            return_value=(items, 1, 1),
        ) as mock_list:
            resp = list_records(_post_request(user=_authed_user()), status="completed", page=1, page_size=20)

        assert resp.count == 1
        assert resp.num_pages == 1
        assert resp.items[0].file_name == "a.pdf"
        assert resp.items[0].backend_used == "local"
        mock_list.assert_called_once_with(status="completed", page=1, page_size=20, user=_authed_user())

    def test_get_record_returns_detail(self) -> None:
        from apps.document_parsing.services.record_service import DocumentParsingRecordService

        detail = {
            "id": 9,
            "status": "completed",
            "file_name": "b.pdf",
            "file_size": 20,
            "backend_used": "mineru",
            "error_message": None,
            "text": "全文内容",
            "markdown": "# md",
            "metadata": {"k": 1},
            "created_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T00:02:00Z",
        }
        with patch.object(DocumentParsingRecordService, "get_record", return_value=detail) as mock_get:
            resp = get_record(_post_request(user=_authed_user()), record_id=9)

        assert resp.id == 9
        assert resp.text == "全文内容"
        assert resp.metadata == {"k": 1}
        mock_get.assert_called_once_with(9, user=_authed_user())
