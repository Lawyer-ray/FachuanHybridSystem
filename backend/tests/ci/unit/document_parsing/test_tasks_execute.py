"""document_parsing.tasks 后台执行体与 hook 边缘分支测试。

补齐既有 test_document_parsing_hook.py 未覆盖的分支：
task_name 携带非法 id、记录不存在、非 dict result 回写失败，
以及 execute_parse_document / execute_extract_text 的成功与异常
返回字典（解析后端 mock）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.tasks import document_parsing_hook, execute_extract_text, execute_parse_document


def _q_task(name: str, result: object) -> SimpleNamespace:
    return SimpleNamespace(name=name, result=result)


@pytest.mark.django_db
class TestHookEdgeBranches:
    def test_bad_task_id_in_name_skipped(self) -> None:
        record = DocumentParsingTask.objects.create(
            file_name="a.pdf", file_path="/tmp/a.pdf", file_size=1, status=DocumentParsingTask.Status.PROCESSING
        )
        document_parsing_hook(_q_task("document_parsing_not-an-int", {"success": True}))

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.PROCESSING  # 未被回写

    def test_missing_record_skipped(self) -> None:
        # id 合法但记录不存在：仅记录日志，不抛异常、不影响其它记录
        document_parsing_hook(_q_task("document_parsing_999999", {"success": True}))
        assert not DocumentParsingTask.objects.filter(pk=999999).exists()

    def test_non_dict_result_marks_failed_with_str(self) -> None:
        record = DocumentParsingTask.objects.create(
            file_name="b.pdf", file_path="/tmp/b.pdf", file_size=1, status=DocumentParsingTask.Status.PROCESSING
        )
        document_parsing_hook(_q_task(f"document_parsing_{record.id}", "worker crashed"))

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.FAILED
        assert record.error_message == "worker crashed"

    def test_failed_dict_without_error_key_uses_placeholder(self) -> None:
        record = DocumentParsingTask.objects.create(
            file_name="c.pdf", file_path="/tmp/c.pdf", file_size=1, status=DocumentParsingTask.Status.PROCESSING
        )
        document_parsing_hook(_q_task(f"document_parsing_{record.id}", {"success": False}))

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.FAILED
        assert record.error_message == "未知错误"


class TestExecuteParseDocument:
    def test_success_returns_result_dict(self) -> None:
        parsed = SimpleNamespace(text="全文", markdown="# md", metadata={"pages": 3}, parse_method="mineru")
        parser = MagicMock()
        parser.parse_document = MagicMock(return_value=parsed)

        with patch("apps.document_parsing.services.get_document_parser", return_value=parser):
            result = execute_parse_document(
                "/tmp/x.pdf", "pdf", "mineru", extract_tables=True, extract_images=False, return_markdown=True
            )

        assert result == {
            "success": True,
            "text": "全文",
            "markdown": "# md",
            "metadata": {"pages": 3},
            "parse_method": "mineru",
        }
        kwargs = parser.parse_document.call_args.kwargs
        assert kwargs["file_path"] == "/tmp/x.pdf"
        assert kwargs["file_type"] == "pdf"
        assert kwargs["extract_tables"] is True

    def test_exception_returns_error_dict(self) -> None:
        with patch(
            "apps.document_parsing.services.get_document_parser",
            side_effect=RuntimeError("backend down"),
        ):
            result = execute_parse_document(
                "/tmp/y.pdf", "pdf", "textin", extract_tables=False, extract_images=False, return_markdown=True
            )

        assert result["success"] is False
        assert "backend down" in result["error"]


class TestExecuteExtractText:
    def test_success_returns_result_dict(self) -> None:
        extracted = SimpleNamespace(success=True, text="正文", method="textin", metadata={"len": 2})
        parser = MagicMock()
        parser.extract_text = MagicMock(return_value=extracted)

        with patch("apps.document_parsing.services.get_document_parser", return_value=parser):
            result = execute_extract_text("/tmp/z.pdf", "local", max_length=100)

        assert result == {"success": True, "text": "正文", "method": "textin", "metadata": {"len": 2}}
        parser.extract_text.assert_called_once_with(file_path="/tmp/z.pdf", max_length=100)

    def test_exception_returns_error_dict(self) -> None:
        with patch(
            "apps.document_parsing.services.get_document_parser",
            side_effect=RuntimeError("ocr unavailable"),
        ):
            result = execute_extract_text("/tmp/w.pdf", "local", max_length=None)

        assert result == {"success": False, "text": "", "error": "ocr unavailable"}
