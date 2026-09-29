"""doc_convert record_service 单元测试。"""

from __future__ import annotations

import pytest
from django.core.files.storage import default_storage

from apps.doc_convert.models import DocConvertRecord
from apps.doc_convert.services.record_service import DocConvertRecordService, mbid_display_name


@pytest.mark.django_db
class TestDocConvertRecordService:
    def test_record_success_saves_file_and_summary(self):
        svc = DocConvertRecordService()
        record = svc.record_success(original_name="起诉状.docx", mbid="mjjdqsz", content=b"PK-fake-docx")

        assert record.status == DocConvertRecord.Status.SUCCESS
        assert record.mbid_name == "民间借贷起诉状"  # mbid → 展示名已解析
        assert record.output_file  # 产物已落盘
        assert default_storage.exists(record.output_file.name)

        items, count, _ = svc.list_records()
        assert count == 1
        assert items[0]["original_name"] == "起诉状.docx"
        assert items[0]["has_file"] is True

    def test_record_failure_marks_error(self):
        svc = DocConvertRecordService()
        record = svc.record_failure(original_name="上诉状.docx", mbid="mjjdqsz", error_message="云端转换超时")

        assert record.status == DocConvertRecord.Status.FAILED
        items, _, _ = svc.list_records(status="failed")
        assert items[0]["error_message"] == "云端转换超时"
        assert items[0]["has_file"] is False

    @pytest.mark.django_db(transaction=True)
    def test_delete_record_cleans_file(self):
        # 文件清理挂在 post_delete 的 transaction.on_commit 上，
        # 需要 transaction=True 让提交真正发生
        svc = DocConvertRecordService()
        record = svc.record_success(original_name="答辩状.docx", mbid="mjjdqsz", content=b"PK")
        path = record.output_file.name
        assert default_storage.exists(path)

        record_id = record.id
        svc.get_record(record_id).delete()

        assert not DocConvertRecord.objects.filter(id=record_id).exists()
        assert not default_storage.exists(path)

    def test_get_record_not_found_raises(self):
        from apps.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            DocConvertRecordService().get_record(99999)

    def test_mbid_display_name_unknown_passthrough(self):
        assert mbid_display_name("nonexistent-mbid") == "nonexistent-mbid"
