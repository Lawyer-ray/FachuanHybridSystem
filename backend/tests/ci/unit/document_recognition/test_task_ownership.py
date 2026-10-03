"""任务归属口径测试（审计 P1 修复）。

口径：is_admin / is_superuser 见全量；普通用户见自己创建的任务与
存量 created_by 为 NULL 的旧任务（兼容旧数据）；非归属人非管理员 → NotFoundError（404）。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.core.exceptions import NotFoundError
from apps.document_recognition.models import DateConfirmationStatus, DocumentRecognitionStatus, DocumentRecognitionTask
from apps.document_recognition.services import date_candidate_service
from apps.document_recognition.services.task_service import DocumentRecognitionTaskService
from apps.testing.factories import LawyerFactory


def _task(owner: Any | None = None, **kwargs: Any) -> DocumentRecognitionTask:
    defaults: dict[str, Any] = {
        "file_path": "/tmp/doc.pdf",
        "original_filename": "doc.pdf",
        "status": DocumentRecognitionStatus.SUCCESS,
        "date_confirmation_status": DateConfirmationStatus.PENDING,
    }
    defaults.update(kwargs)
    return DocumentRecognitionTask.objects.create(created_by=owner, **defaults)


@pytest.mark.django_db
class TestGetTaskOwnership:
    def test_owner_admin_superuser_visible(self):
        owner = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        superuser = LawyerFactory(is_superuser=True)
        task = _task(owner=owner)

        svc = DocumentRecognitionTaskService()
        assert svc.get_task(task.id, user=owner).id == task.id
        assert svc.get_task(task.id, user=admin).id == task.id
        assert svc.get_task(task.id, user=superuser).id == task.id

    def test_non_owner_non_admin_gets_404(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        task = _task(owner=owner)

        with pytest.raises(NotFoundError):
            DocumentRecognitionTaskService().get_task(task.id, user=other)

    def test_legacy_null_task_visible_to_normal_user(self):
        """存量 created_by 为 NULL 的旧任务保持所内可见（兼容旧数据口径）。"""
        other = LawyerFactory()
        task = _task()

        assert DocumentRecognitionTaskService().get_task(task.id, user=other).id == task.id


@pytest.mark.django_db
class TestPendingTasksOwnership:
    def test_pending_list_filtered_by_ownership(self):
        a = LawyerFactory()
        b = LawyerFactory()
        admin = LawyerFactory(is_admin=True)
        _task(owner=a, original_filename="a.pdf")
        _task(owner=b, original_filename="b.pdf")
        _task(original_filename="legacy.pdf")

        svc = DocumentRecognitionTaskService()
        names_a = {row["original_filename"] for row in svc.pending_tasks(limit=50, user=a)}
        assert names_a == {"a.pdf", "legacy.pdf"}

        names_admin = {row["original_filename"] for row in svc.pending_tasks(limit=50, user=admin)}
        assert names_admin == {"a.pdf", "b.pdf", "legacy.pdf"}


@pytest.mark.django_db
class TestCandidateActionsOwnership:
    def test_confirm_candidates_non_owner_404(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        task = _task(owner=owner)

        with pytest.raises(NotFoundError):
            date_candidate_service.confirm_candidates(task.id, [{"candidate_id": 1}], user=other)

    def test_revoke_confirmation_non_owner_404(self):
        owner = LawyerFactory()
        other = LawyerFactory()
        task = _task(owner=owner)

        with pytest.raises(NotFoundError):
            date_candidate_service.revoke_confirmation(task.id, 1, user=other)

    def test_create_task_writes_created_by(self):
        user = LawyerFactory()

        task = DocumentRecognitionTaskService().create_task(
            file_path="/tmp/x.pdf", original_filename="x.pdf", created_by=user
        )

        assert task.created_by_id == user.id
