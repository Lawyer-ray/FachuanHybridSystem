"""证件识别异步任务提交/轮询服务测试（安全修复：task_id 令牌化 + 归属校验）。

口径：本人/管理员（is_admin 或 is_superuser）可查；非归属人一律
NotFoundError（404 不泄露）。提交端点返回记录 id，Q 原始 id 回写 q_task_id。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.client.models import ClientIdentityDocParseTask
from apps.client.services.identity_doc_task_service import IdentityDocTaskService
from apps.core.exceptions import NotFoundError
from apps.testing.factories import LawyerFactory

_STATUS_INFO: dict[str, Any] = {
    "task_id": "q-x",
    "status": "success",
    "result": {"doc_type": "id_card", "extracted_data": {"name": "他人证件 PII"}},
    "started_at": None,
    "finished_at": None,
}


def _record(owner: Any | None = None, q_task_id: str = "", **kwargs: Any) -> ClientIdentityDocParseTask:
    defaults: dict[str, Any] = {"doc_type": "id_card", "q_task_id": q_task_id}
    defaults.update(kwargs)
    return ClientIdentityDocParseTask.objects.create(created_by=owner, **defaults)


@pytest.fixture(autouse=True)
def _stop_patchers():
    yield
    patch.stopall()


def _mock_query_service(q_status: str = "success") -> MagicMock:
    patcher = patch("apps.client.services.identity_doc_task_service.TaskQueryService")
    mock_cls = patcher.start()
    info = dict(_STATUS_INFO)
    info["status"] = q_status
    mock_cls.return_value.get_task_status.return_value = info
    return mock_cls


@pytest.mark.django_db
class TestSubmitRecognizeTask:
    def test_returns_record_id_and_persists_q_task_id(self):
        user = LawyerFactory()
        upload = MagicMock()
        upload.name = "id_card.jpg"
        task_port = MagicMock()
        task_port.submit_task.return_value = "q-uuid-1"

        with (
            patch(
                "apps.client.services.identity_doc_task_service.save_uploaded_file",
                return_value=("client_docs/recognize/xxx.jpg", "xxx.jpg"),
            ) as mock_save,
            patch(
                "apps.client.services.identity_doc_task_service.get_task_service_port",
                return_value=task_port,
            ) as mock_port_factory,
        ):
            result = IdentityDocTaskService().submit_recognize_task(uploaded_file=upload, doc_type="id_card", user=user)

        # 响应形状不变：task_id 值换记录 id 令牌
        assert result["status"] == "pending"
        assert result["task_id"].isdigit()
        record = ClientIdentityDocParseTask.objects.get(pk=int(result["task_id"]))
        assert record.q_task_id == "q-uuid-1"
        assert record.created_by == user
        assert record.status == ClientIdentityDocParseTask.Status.PENDING
        # 提交参数：目标函数 + 保存路径 + 归一化 doc_type
        mock_save.assert_called_once()
        task_port.submit_task.assert_called_once_with(
            "apps.client.tasks.execute_identity_doc_recognition",
            "client_docs/recognize/xxx.jpg",
            "id_card",
        )
        mock_port_factory.assert_called_once()

    def test_blank_doc_type_falls_back_to_id_card(self):
        """doc_type 缺省回退 id_card（任务函数必填参数，缺省会 100% TypeError）。"""
        upload = MagicMock()
        upload.name = "a.jpg"
        task_port = MagicMock()
        task_port.submit_task.return_value = "q-uuid-2"

        with (
            patch(
                "apps.client.services.identity_doc_task_service.save_uploaded_file",
                return_value=("client_docs/recognize/a.jpg", "a.jpg"),
            ),
            patch(
                "apps.client.services.identity_doc_task_service.get_task_service_port",
                return_value=task_port,
            ),
        ):
            result = IdentityDocTaskService().submit_recognize_task(uploaded_file=upload, doc_type="  ", user=None)

        record = ClientIdentityDocParseTask.objects.get(pk=int(result["task_id"]))
        assert record.doc_type == "id_card"
        assert task_port.submit_task.call_args.args[2] == "id_card"


@pytest.mark.django_db
class TestGetTaskStatusOwnership:
    def test_owner_reads_by_record_id(self):
        owner = LawyerFactory()
        record = _record(owner=owner, q_task_id="q-1")
        _mock_query_service()

        info = IdentityDocTaskService().get_task_status(str(record.id), user=owner)

        assert info["status"] == "success"
        assert info["result"] == _STATUS_INFO["result"]
        # task_id 字段回显客户端令牌
        assert info["task_id"] == str(record.id)

    def test_non_owner_gets_404_by_record_id(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        record = _record(owner=owner, q_task_id="q-2")
        _mock_query_service()

        with pytest.raises(NotFoundError):
            IdentityDocTaskService().get_task_status(str(record.id), user=other)

    def test_admin_reads_others_by_record_id(self):
        owner = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        record = _record(owner=owner, q_task_id="q-3")
        _mock_query_service()

        assert IdentityDocTaskService().get_task_status(str(record.id), user=admin)["status"] == "success"

    def test_non_owner_gets_404_by_q_task_id(self):
        """兼容路径归属校验：他人的 Q id 同样 404（不泄露证件 OCR 结果）。"""
        owner = LawyerFactory()
        other = LawyerFactory()
        _record(owner=owner, q_task_id="q-legacy")
        _mock_query_service()

        with pytest.raises(NotFoundError):
            IdentityDocTaskService().get_task_status("q-legacy", user=other)

    def test_owner_reads_by_q_task_id(self):
        owner = LawyerFactory()
        _record(owner=owner, q_task_id="q-legacy")
        _mock_query_service()

        info = IdentityDocTaskService().get_task_status("q-legacy", user=owner)

        assert info["task_id"] == "q-legacy"
        assert info["status"] == "success"

    def test_unknown_task_id_gets_404(self):
        user = LawyerFactory()
        _mock_query_service()

        with pytest.raises(NotFoundError):
            IdentityDocTaskService().get_task_status("999999", user=user)

    def test_terminal_q_status_synced_back_to_record(self):
        """轮询时把队列终态 lazy 回写记录 status。"""
        owner = LawyerFactory()
        record = _record(owner=owner, q_task_id="q-4")
        _mock_query_service(q_status="failure")

        IdentityDocTaskService().get_task_status(str(record.id), user=owner)

        record.refresh_from_db()
        assert record.status == ClientIdentityDocParseTask.Status.FAILED
