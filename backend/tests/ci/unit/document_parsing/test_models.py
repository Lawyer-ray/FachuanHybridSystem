"""DocumentParsingTask Model 测试"""

import json

import pytest
from django.utils import timezone

from apps.document_parsing.models.task import DocumentParsingTask


@pytest.mark.django_db
class TestDocumentParsingTask:
    def _make_task(self, **kwargs) -> DocumentParsingTask:
        defaults = {
            "file_name": "test.pdf",
            "file_path": "/tmp/test.pdf",
            "file_size": 1024,
        }
        defaults.update(kwargs)
        return DocumentParsingTask.objects.create(**defaults)

    def test_str(self) -> None:
        task = self._make_task()
        s = str(task)
        assert f"#{task.id}" in s
        assert "test.pdf" in s
        assert "待处理" in s

    def test_str_completed(self) -> None:
        task = self._make_task(status=DocumentParsingTask.Status.COMPLETED)
        assert "已完成" in str(task)

    def test_default_status(self) -> None:
        task = self._make_task()
        assert task.status == DocumentParsingTask.Status.PENDING

    def test_metadata_default_empty_dict(self) -> None:
        task = self._make_task()
        assert task.metadata == {}

    def test_metadata_pprint_empty(self) -> None:
        task = self._make_task()
        assert task.metadata_pprint == "{}"

    def test_metadata_pprint_normal(self) -> None:
        task = self._make_task(metadata={"pages": 5, "key": "值"})
        result = task.metadata_pprint
        parsed = json.loads(result)
        assert parsed["pages"] == 5
        assert parsed["key"] == "值"

    def test_metadata_pprint_invalid_json(self) -> None:
        task = self._make_task()
        # 直接赋值一个非 JSON-serializable 对象
        task.metadata = object()  # type: ignore[assignment]
        result = task.metadata_pprint
        assert isinstance(result, str)

    def test_mark_processing(self) -> None:
        task = self._make_task()
        task.mark_processing()
        task.refresh_from_db()
        assert task.status == DocumentParsingTask.Status.PROCESSING

    def test_mark_completed(self) -> None:
        task = self._make_task()
        before = timezone.now()
        task.mark_completed(
            text="parsed text",
            markdown="# heading",
            metadata={"pages": 3},
            backend_used="mineru",
        )
        task.refresh_from_db()
        assert task.status == DocumentParsingTask.Status.COMPLETED
        assert task.text == "parsed text"
        assert task.markdown == "# heading"
        assert task.metadata == {"pages": 3}
        assert task.backend_used == "mineru"
        assert task.completed_at is not None
        assert task.completed_at >= before

    def test_mark_failed(self) -> None:
        task = self._make_task()
        before = timezone.now()
        task.mark_failed("something went wrong")
        task.refresh_from_db()
        assert task.status == DocumentParsingTask.Status.FAILED
        assert task.error_message == "something went wrong"
        assert task.completed_at is not None
        assert task.completed_at >= before

    def test_status_choices(self) -> None:
        choices = DocumentParsingTask.Status.choices
        assert ("pending", "待处理") in choices
        assert ("processing", "处理中") in choices
        assert ("completed", "已完成") in choices
        assert ("failed", "失败") in choices

    def test_ordering(self) -> None:
        t1 = self._make_task(file_name="first.pdf")
        t2 = self._make_task(file_name="second.pdf")
        tasks = list(DocumentParsingTask.objects.all())
        # 按 -created_at 排序，最新的在前
        assert tasks[0].id == t2.id
        assert tasks[1].id == t1.id
