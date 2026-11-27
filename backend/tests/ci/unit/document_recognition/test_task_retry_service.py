"""RetryTaskService：重跑状态机（2026-11-27 从 API 层下沉时的回归锁定）。

原来这段逻辑写在 ``api/document_recognition_api.py::retry_task`` 里（API 层直接
改模型 + ``task.save(update_fields=[...])``，四层架构硬违规），且**零单测覆盖**。
下沉到 Service 后补上这一组纯逻辑测试，锁住四条口径：

- ``success`` → ``TASK_ALREADY_SUCCESS``（不写库、不提交）；
- ``processing`` 未僵死 → ``TASK_STILL_RUNNING``（不写库、不提交）；
- ``processing`` 已僵死 → 允许重跑；
- 重置时 ``error_message`` 必须是**空串**（NOT NULL CharField，写 ``None``
  会让 ``save()`` 抛 IntegrityError → 接口 500，2026-11-23 审计修复的正是这条）。

全部无 DB（SimpleNamespace + MagicMock），与 ``test_date_candidates.py`` 同风格。
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.document_recognition.services.task_retry_service import STALLED_THRESHOLD_SECONDS, RetryTaskService

_RESET_FIELDS = ["status", "error_message", "started_at", "finished_at"]


def _task(status: str, *, started_ago: int | None = 5, task_id: int = 11) -> SimpleNamespace:
    """构造一个「替身任务」：时间字段真实，save 是 MagicMock。"""
    now = timezone.now()
    return SimpleNamespace(
        id=task_id,
        status=status,
        error_message="上一次失败的原始报错",
        started_at=None if started_ago is None else now - timedelta(seconds=started_ago),
        finished_at=None,
        created_at=now - timedelta(seconds=(started_ago or 0) + 1),
        save=MagicMock(),
    )


def _retry(task: SimpleNamespace) -> int:
    """以替身任务跑一次 ``RetryTaskService.retry``（顺带返回 submit_task 的替身）。"""
    with (
        patch("apps.document_recognition.services.task_service.DocumentRecognitionTaskService") as task_service,
        patch("apps.core.tasking.submit_task"),
    ):
        task_service.return_value.get_task.return_value = task
        return RetryTaskService().retry(task.id, user=None)


class TestRetryTaskRejections:
    def test_success_task_rejected(self) -> None:
        task = _task("success")

        with pytest.raises(Exception) as exc_info:
            _retry(task)

        assert getattr(exc_info.value, "code", None) == "TASK_ALREADY_SUCCESS"
        task.save.assert_not_called()

    def test_running_task_rejected(self) -> None:
        task = _task("processing", started_ago=10)

        with pytest.raises(Exception) as exc_info:
            _retry(task)

        assert getattr(exc_info.value, "code", None) == "TASK_STILL_RUNNING"
        task.save.assert_not_called()


class TestRetryTaskAllowed:
    def test_failed_task_resets_and_submits(self) -> None:
        task = _task("failed")

        with (
            patch("apps.document_recognition.services.task_service.DocumentRecognitionTaskService") as task_service,
            patch("apps.core.tasking.submit_task") as submit_task,
        ):
            task_service.return_value.get_task.return_value = task
            returned = RetryTaskService().retry(task.id, user=None)

        assert returned == task.id
        assert task.status == "pending"
        # NOT NULL CharField：必须空串而不是 None，否则重跑接口 500
        assert task.error_message == ""
        assert task.started_at is None and task.finished_at is None
        task.save.assert_called_once_with(update_fields=_RESET_FIELDS)
        submit_task.assert_called_once_with(
            "apps.document_recognition.tasks.execute_document_recognition_task",
            task.id,
            task_name=f"document_recognition_{task.id}_retry",
            timeout=600,
        )

    def test_stalled_processing_task_can_retry(self) -> None:
        task = _task("processing", started_ago=STALLED_THRESHOLD_SECONDS + 10)

        with (
            patch("apps.document_recognition.services.task_service.DocumentRecognitionTaskService") as task_service,
            patch("apps.core.tasking.submit_task") as submit_task,
        ):
            task_service.return_value.get_task.return_value = task
            RetryTaskService().retry(task.id, user=None)

        assert task.status == "pending"
        submit_task.assert_called_once()
