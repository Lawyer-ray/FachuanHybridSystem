"""解析记录归属口径测试（审计 P1 修复）。

口径：is_admin / is_superuser 见全量；普通用户见自己创建的记录与
存量 created_by 为 NULL 的旧记录（兼容旧数据）；非归属人非管理员 → NotFoundError（404）。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.core.exceptions import NotFoundError
from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.services.record_service import DocumentParsingRecordService
from apps.testing.factories import LawyerFactory


def _record(owner: Any | None = None, **kwargs: Any) -> DocumentParsingTask:
    defaults: dict[str, Any] = {"file_name": "doc.pdf", "file_path": "/tmp/doc.pdf", "file_size": 10}
    defaults.update(kwargs)
    return DocumentParsingTask.objects.create(created_by=owner, **defaults)


@pytest.mark.django_db
class TestListRecordsOwnership:
    def test_normal_user_sees_own_and_legacy_only(self):
        a = LawyerFactory()
        b = LawyerFactory()
        _record(owner=a, file_name="a.pdf")
        _record(owner=b, file_name="b.pdf")
        _record(file_name="legacy.pdf")

        svc = DocumentParsingRecordService()
        items, count, _num_pages = svc.list_records(page_size=50, user=a)

        names = {row["file_name"] for row in items}
        assert names == {"a.pdf", "legacy.pdf"}
        assert count == 2

    def test_admin_sees_all(self):
        a = LawyerFactory()
        b = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        _record(owner=a, file_name="a.pdf")
        _record(owner=b, file_name="b.pdf")

        items, count, _num_pages = DocumentParsingRecordService().list_records(page_size=50, user=admin)

        assert {row["file_name"] for row in items} == {"a.pdf", "b.pdf"}
        assert count == 2


@pytest.mark.django_db
class TestGetRecordOwnership:
    def test_non_owner_non_admin_gets_404(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        record = _record(owner=owner, text="他人上传文档的解析全文")

        with pytest.raises(NotFoundError):
            DocumentParsingRecordService().get_record(record.id, user=other)

    def test_owner_reads_full_text(self):
        owner = LawyerFactory()
        record = _record(owner=owner, text="全文内容", markdown="# md")

        detail = DocumentParsingRecordService().get_record(record.id, user=owner)

        assert detail["text"] == "全文内容"
        assert detail["markdown"] == "# md"

    def test_admin_reads_others_record(self):
        owner = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        record = _record(owner=owner)

        assert DocumentParsingRecordService().get_record(record.id, user=admin)["id"] == record.id
