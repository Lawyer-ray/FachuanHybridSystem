"""轮询端点归属校验测试（安全修复：task_id 令牌化 + 行级归属）。

口径：本人/管理员（is_admin 或 is_superuser，与 /records 端点一致）可查；
非归属人非管理员一律 NotFoundError（404 不泄露）。解析顺序：
记录 id 直查 → q_task_id 反查（灰度兼容）→ task_name 约定兜底（存量）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError
from apps.document_parsing.models import DocumentParsingTask
from apps.document_parsing.services.task_status_service import DocumentParsingTaskStatusService
from apps.testing.factories import LawyerFactory

_STATUS_INFO: dict[str, Any] = {
    "task_id": "q-x",
    "status": "success",
    "result": {"success": True, "text": "他人不可见的解析全文"},
    "started_at": None,
    "finished_at": None,
}


def _record(owner: Any | None = None, q_task_id: str = "", **kwargs: Any) -> DocumentParsingTask:
    defaults: dict[str, Any] = {
        "file_name": "doc.pdf",
        "file_path": "/tmp/doc.pdf",
        "file_size": 10,
        "q_task_id": q_task_id,
    }
    defaults.update(kwargs)
    return DocumentParsingTask.objects.create(created_by=owner, **defaults)


def _patch_query_service(q_task_by_id: Any = None) -> MagicMock:
    """mock TaskQueryService：get_task_status 返回固定形状，get_task_by_id 可配置。"""
    patcher = patch("apps.document_parsing.services.task_status_service.TaskQueryService")
    mock_cls = patcher.start()
    mock_cls.return_value.get_task_status.return_value = dict(_STATUS_INFO)
    mock_cls.return_value.get_task_by_id.return_value = q_task_by_id
    return mock_cls


@pytest.fixture(autouse=True)
def _stop_query_service_patcher():
    yield
    patch.stopall()


@pytest.mark.django_db
class TestGetTaskStatusOwnership:
    def test_owner_reads_by_record_id(self):
        owner = LawyerFactory()
        record = _record(owner=owner, q_task_id="q-1")
        _patch_query_service()

        info = DocumentParsingTaskStatusService().get_task_status(str(record.id), user=owner)

        assert info["status"] == "success"
        assert info["result"] == _STATUS_INFO["result"]
        # task_id 字段回显客户端令牌（记录 id）
        assert info["task_id"] == str(record.id)

    def test_non_owner_gets_404_by_record_id(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        record = _record(owner=owner, q_task_id="q-2")
        _patch_query_service()

        with pytest.raises(NotFoundError):
            DocumentParsingTaskStatusService().get_task_status(str(record.id), user=other)

    def test_admin_reads_others_by_record_id(self):
        owner = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        record = _record(owner=owner, q_task_id="q-3")
        _patch_query_service()

        info = DocumentParsingTaskStatusService().get_task_status(str(record.id), user=admin)

        assert info["status"] == "success"

    def test_non_owner_gets_404_by_legacy_q_task_id(self):
        """兼容路径归属校验：他人的旧 Q id 同样 404（不泄露队列状态）。"""
        owner = LawyerFactory()
        other = LawyerFactory()
        _record(owner=owner, q_task_id="q-legacy-owner")
        _patch_query_service()

        with pytest.raises(NotFoundError):
            DocumentParsingTaskStatusService().get_task_status("q-legacy-owner", user=other)

    def test_owner_reads_by_q_task_id(self):
        owner = LawyerFactory()
        _record(owner=owner, q_task_id="q-legacy-owner")
        _patch_query_service()

        info = DocumentParsingTaskStatusService().get_task_status("q-legacy-owner", user=owner)

        assert info["task_id"] == "q-legacy-owner"
        assert info["status"] == "success"

    def test_unknown_task_id_gets_404(self):
        user = LawyerFactory()
        _patch_query_service()

        with pytest.raises(NotFoundError):
            DocumentParsingTaskStatusService().get_task_status("999999", user=user)


@pytest.mark.django_db
class TestLegacyTaskNameFallback:
    """存量兜底：部署前提交的任务（q_task_id 空），经 Q Task.task_name 约定反解。"""

    def test_owner_reads_via_task_name_fallback(self):
        owner = LawyerFactory()
        record = _record(owner=owner)  # 存量记录：q_task_id 为空
        q_task = SimpleNamespace(name=f"document_parsing_{record.id}")
        _patch_query_service(q_task_by_id=q_task)

        info = DocumentParsingTaskStatusService().get_task_status("q-uuid-legacy", user=owner)

        assert info["status"] == "success"
        assert info["task_id"] == "q-uuid-legacy"

    def test_non_owner_gets_404_via_task_name_fallback(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        record = _record(owner=owner)
        q_task = SimpleNamespace(name=f"document_parsing_{record.id}")
        _patch_query_service(q_task_by_id=q_task)

        with pytest.raises(NotFoundError):
            DocumentParsingTaskStatusService().get_task_status("q-uuid-legacy", user=other)

    def test_unrelated_task_name_gets_404(self):
        """task_name 不符约定的 Q 任务不落兜底路径（extract 旧 task_name 等）。"""
        user = LawyerFactory()
        q_task = SimpleNamespace(name="extract_text_somefile.pdf")
        _patch_query_service(q_task_by_id=q_task)

        with pytest.raises(NotFoundError):
            DocumentParsingTaskStatusService().get_task_status("q-uuid-unknown", user=user)
