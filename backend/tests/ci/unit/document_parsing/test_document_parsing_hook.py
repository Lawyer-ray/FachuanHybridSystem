"""document_parsing_hook 回写测试（parse 与 extract-text 双任务约定）."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.tasks import document_parsing_hook


def _q_task(record_id: int, result: Any, *, name: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name or f"document_parsing_{record_id}", result=result)


@pytest.mark.django_db
class TestDocumentParsingHook:
    def _record(self) -> DocumentParsingTask:
        return DocumentParsingTask.objects.create(
            file_name="doc.pdf", file_path="/tmp/doc.pdf", file_size=10, status=DocumentParsingTask.Status.PROCESSING
        )

    def test_parse_result_marks_completed(self):
        record = self._record()

        document_parsing_hook(
            _q_task(
                record.id,
                {"success": True, "text": "全文", "markdown": "# md", "metadata": {}, "parse_method": "mineru"},
            )
        )

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.COMPLETED
        assert record.backend_used == "mineru"
        assert record.markdown == "# md"

    def test_extract_text_result_marks_completed_with_method_key(self):
        """extract-text 结果无 parse_method，backend_used 应回退 method 键。"""
        record = self._record()

        document_parsing_hook(
            _q_task(record.id, {"success": True, "text": "纯文本", "method": "textin", "metadata": {}})
        )

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.COMPLETED
        assert record.backend_used == "textin"
        assert record.text == "纯文本"
        assert record.markdown == ""

    def test_failed_result_marks_failed(self):
        record = self._record()

        document_parsing_hook(_q_task(record.id, {"success": False, "error": "boom"}))

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.FAILED
        assert record.error_message == "boom"

    def test_unknown_task_name_skipped(self):
        record = self._record()

        document_parsing_hook(_q_task(record.id, {"success": True}, name="extract_text_somefile.pdf"))

        record.refresh_from_db()
        assert record.status == DocumentParsingTask.Status.PROCESSING
