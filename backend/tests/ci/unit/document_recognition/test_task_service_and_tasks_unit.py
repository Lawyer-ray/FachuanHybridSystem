"""task_service + tasks 单元测试 — 识别任务 CRUD/归属过滤与 Django-Q 任务编排。

覆盖：
- ``task_ownership_q`` 管理员/普通用户口径
- ``update_task_info`` 更新与校验分支
- ``search_cases_for_binding`` 委托 case_service
- ``execute_document_recognition_task`` 状态流转（成功/失败/任务缺失/管线模式）
- ``_send_recognition_notification`` 通知回写
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.document_recognition.models import DateConfirmationStatus, DocumentRecognitionStatus, DocumentRecognitionTask
from apps.document_recognition.services.data_classes import BindingResult, DocumentType, RecognitionResult
from apps.document_recognition.services.task_service import DocumentRecognitionTaskService, task_ownership_q
from apps.testing.factories import LawyerFactory


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC)


def _task(owner: Any | None = None, **kwargs: Any) -> DocumentRecognitionTask:
    defaults: dict[str, Any] = {
        "file_path": "/tmp/doc.pdf",
        "original_filename": "doc.pdf",
        "status": DocumentRecognitionStatus.PENDING,
    }
    defaults.update(kwargs)
    return DocumentRecognitionTask.objects.create(created_by=owner, **defaults)


@pytest.mark.django_db
class TestTaskOwnershipQ:
    def test_admin_returns_none(self) -> None:
        admin = LawyerFactory(is_admin=True)
        assert task_ownership_q(admin) is None

    def test_superuser_returns_none(self) -> None:
        superuser = LawyerFactory(is_superuser=True)
        assert task_ownership_q(superuser) is None

    def test_normal_user_filters_created_by(self) -> None:
        user = LawyerFactory()
        from django.db.models import Q

        q = task_ownership_q(user)
        assert isinstance(q, Q)
        assert "created_by" in str(q)

    def test_anonymous_user_filters(self) -> None:
        from django.db.models import Q

        assert isinstance(task_ownership_q(None), Q)


@pytest.mark.django_db
class TestUpdateTaskInfo:
    def test_updates_case_number_and_key_time(self) -> None:
        task = _task()
        result = DocumentRecognitionTaskService().update_task_info(
            task.id, case_number="（2026）粤0604民初1号", key_time="2026-03-15T09:30:00+08:00", user=None
        )
        assert result.case_number == "（2026）粤0604民初1号"
        assert result.key_time is not None
        assert result.key_time.year == 2026

    def test_invalid_key_time_raises_validation(self) -> None:
        task = _task()
        with pytest.raises(ValidationException) as exc_info:
            DocumentRecognitionTaskService().update_task_info(task.id, key_time="not-a-time")
        assert exc_info.value.code == "INVALID_TIME_FORMAT"

    def test_empty_key_time_clears(self) -> None:
        """清空 key_time 生效；case_number 空串清空会向 NOT NULL 列写 NULL（疑似 bug，
        见任务报告），这里只更新非空值验证可写路径。"""
        task = _task(case_number="（2026）粤1号", key_time=_aware(datetime(2026, 3, 15, 9, 30)))
        result = DocumentRecognitionTaskService().update_task_info(
            task.id, key_time="", case_number="（2026）粤0604民初2号"
        )
        assert result.key_time is None
        assert result.case_number == "（2026）粤0604民初2号"

    def test_task_not_visible_raises_not_found(self) -> None:
        owner = LawyerFactory()
        other = LawyerFactory()
        task = _task(owner=owner)
        with pytest.raises(NotFoundError):
            DocumentRecognitionTaskService().update_task_info(task.id, case_number="X", user=other)

    def test_no_changes_skips_save(self) -> None:
        task = _task()
        with patch.object(DocumentRecognitionTask, "save") as m_save:
            result = DocumentRecognitionTaskService().update_task_info(task.id, user=None)
        m_save.assert_not_called()
        assert result.id == task.id


@pytest.mark.django_db
class TestPendingTasksSummary:
    def test_summary_fields_and_case_name(self) -> None:
        from apps.cases.models import Case

        case = Case.objects.create(name="张三与李四纠纷")
        _task(
            status=DocumentRecognitionStatus.SUCCESS,
            date_confirmation_status=DateConfirmationStatus.PENDING,
            case=case,
            original_filename="summons.pdf",
            document_type=DocumentType.SUMMONS.value,
        )
        rows = DocumentRecognitionTaskService().pending_tasks(limit=10, user=None)
        assert len(rows) == 1
        row = rows[0]
        assert row["original_filename"] == "summons.pdf"
        assert row["case_name"] == "张三与李四纠纷"
        assert row["document_type"] == DocumentType.SUMMONS.value
        assert row["candidate_count"] == 0
        assert "created_at" in row

    def test_only_success_with_pending_confirmation_listed(self) -> None:
        _task(
            status=DocumentRecognitionStatus.FAILED,
            date_confirmation_status=DateConfirmationStatus.PENDING,
            original_filename="failed.pdf",
        )
        _task(
            status=DocumentRecognitionStatus.SUCCESS,
            date_confirmation_status=DateConfirmationStatus.COMPLETE,
            original_filename="done.pdf",
        )
        assert DocumentRecognitionTaskService().pending_tasks(limit=10, user=None) == []


@pytest.mark.django_db
class TestSearchCasesForBinding:
    def test_delegates_to_case_service(self) -> None:
        expected = [{"id": 1, "name": "案件A"}]
        case_service = MagicMock()
        case_service.search_cases_for_binding_internal.return_value = expected
        with patch("apps.core.interfaces.ServiceLocator.get_case_service", return_value=case_service):
            result = DocumentRecognitionTaskService().search_cases_for_binding(
                search_term="案件", limit=5, user=SimpleNamespace(id=1)
            )
        assert result == expected
        kwargs = case_service.search_cases_for_binding_internal.call_args.kwargs
        assert kwargs["search_term"] == "案件"
        assert kwargs["limit"] == 5


# ── tasks.py ───────────────────────────────────────────────────────


def _recognition_response(
    *,
    doc_type: DocumentType = DocumentType.SUMMONS,
    case_number: str = "（2026）粤0604民初1号",
    binding: BindingResult | None = None,
    date_candidates: list[dict[str, Any]] | None = None,
) -> Any:
    from apps.document_recognition.services.data_classes import RecognitionResponse

    binding = binding or BindingResult(
        success=True, case_id=5, case_name="案件A", case_log_id=7, message="文书已绑定到案件 案件A", error_code=""
    )
    recognition = RecognitionResult(
        document_type=doc_type,
        case_number=case_number,
        key_time=_aware(datetime(2026, 3, 15, 9, 30)),
        raw_text="（2026）粤0604民初1号传票正文",
        confidence=0.95,
        extraction_method="pdf_direct",
        llm_model="glm-4v",
        llm_backend="openai_compatible",
        llm_latency_ms=120,
        degraded=False,
    )
    return RecognitionResponse(
        recognition=recognition,
        binding=binding,
        file_path="/tmp/renamed.pdf",
        date_candidates=date_candidates or [],
        party_names=["张三"],
    )


@pytest.mark.django_db
class TestExecuteDocumentRecognitionTask:
    def _execute(self, task: DocumentRecognitionTask, service: MagicMock) -> dict[str, Any] | None:
        from apps.document_recognition.tasks import execute_document_recognition_task

        with patch("apps.core.interfaces.ServiceLocator.get_court_document_recognition_service", return_value=service):
            return execute_document_recognition_task(task.id)

    def test_task_missing_returns_none(self) -> None:
        from apps.document_recognition.tasks import execute_document_recognition_task

        assert execute_document_recognition_task(999999) is None

    def test_success_flow_updates_all_fields(self) -> None:
        task = _task()
        service = MagicMock()
        service.recognize_document.return_value = _recognition_response(
            date_candidates=[
                {
                    "due_at": "2026-03-15T09:30:00+08:00",
                    "reminder_type": "hearing",
                    "context_text": "开庭",
                    "source": "llm",
                    "confidence": 0.9,
                }
            ]
        )
        with patch("apps.document_recognition.tasks._send_recognition_notification") as m_notify:
            result = self._execute(task, service)

        task.refresh_from_db()
        assert result == {"task_id": task.id, "status": "success", "document_type": "summons"}
        assert task.status == DocumentRecognitionStatus.SUCCESS
        assert task.started_at is not None and task.finished_at is not None
        assert task.document_type == "summons"
        assert task.case_number == "（2026）粤0604民初1号"
        assert task.llm_model == "glm-4v"
        assert task.llm_backend == "openai_compatible"
        assert task.llm_latency_ms == 120
        assert task.degraded is False
        assert task.party_names == ["张三"]
        assert task.renamed_file_path == "/tmp/renamed.pdf"
        assert task.binding_success is True
        assert task.case_id == 5
        assert task.case_log_id == 7
        # 日期候选已落库
        assert task.date_candidates.count() == 1
        # 非管线模式 + 绑定成功 → 发通知
        m_notify.assert_called_once()

    def test_failure_flow_marks_failed(self) -> None:
        task = _task()
        service = MagicMock()
        service.recognize_document.side_effect = RuntimeError("识别引擎崩溃")
        result = self._execute(task, service)

        task.refresh_from_db()
        assert result == {"task_id": task.id, "status": "failed", "error": "识别引擎崩溃"}
        assert task.status == DocumentRecognitionStatus.FAILED
        assert task.error_message == "识别引擎崩溃"
        assert task.finished_at is not None

    def test_pipeline_mode_skips_prebinding_and_notification(self) -> None:
        """管线模式（法院短信来源）：预绑定参数透传，且不重复发通知。"""
        task = _task(source_court_sms_id=888, case_id=5, case_log_id=7)
        service = MagicMock()
        service.recognize_document.return_value = _recognition_response()
        with patch("apps.document_recognition.tasks._send_recognition_notification") as m_notify:
            result = self._execute(task, service)

        assert result is not None and result["status"] == "success"
        kwargs = service.recognize_document.call_args.kwargs
        assert kwargs["prebound_case_id"] == 5
        assert kwargs["prebound_case_log_id"] == 7
        assert kwargs["llm_model"] == task.llm_model
        m_notify.assert_not_called()

    def test_binding_failure_still_success_without_notification(self) -> None:
        task = _task()
        service = MagicMock()
        service.recognize_document.return_value = _recognition_response(
            binding=BindingResult.failure_result(message="未找到案号对应案件", error_code="CASE_NOT_FOUND")
        )
        with patch("apps.document_recognition.tasks._send_recognition_notification") as m_notify:
            result = self._execute(task, service)

        task.refresh_from_db()
        assert result is not None and result["status"] == "success"
        assert task.binding_success is False
        assert task.binding_message == "未找到案号对应案件"
        m_notify.assert_not_called()


@pytest.mark.django_db
class TestSendRecognitionNotification:
    _NOTIFY = "apps.document_recognition.services.notification_service.DocumentRecognitionNotificationService"

    @staticmethod
    def _binding() -> BindingResult:
        return BindingResult(
            success=True, case_id=5, case_name="案件A", case_log_id=7, message="绑定成功", error_code=""
        )

    def _notify_result(self, ok: bool) -> Any:
        return SimpleNamespace(
            success=ok,
            sent_at=_aware(datetime(2026, 10, 5, 12, 0)) if ok else None,
            file_sent=ok,
            message="发送成功" if ok else "机器人不可用",
        )

    def test_success_updates_task_flags(self) -> None:
        from apps.document_recognition.tasks import _send_recognition_notification

        task = _task(status=DocumentRecognitionStatus.SUCCESS)
        result = SimpleNamespace(binding=self._binding(), file_path="/tmp/renamed.pdf")
        with patch(self._NOTIFY) as notify_cls:
            notify_cls.return_value.send_notification.return_value = self._notify_result(ok=True)
            _send_recognition_notification(task, result)

        task.refresh_from_db()
        assert task.notification_sent is True
        assert task.notification_file_sent is True
        assert task.notification_sent_at is not None
        assert task.notification_error == ""

    def test_failure_records_error(self) -> None:
        from apps.document_recognition.tasks import _send_recognition_notification

        task = _task(status=DocumentRecognitionStatus.SUCCESS)
        result = SimpleNamespace(binding=self._binding(), file_path="/tmp/renamed.pdf")
        with patch(self._NOTIFY) as notify_cls:
            notify_cls.return_value.send_notification.return_value = self._notify_result(ok=False)
            _send_recognition_notification(task, result)

        task.refresh_from_db()
        assert task.notification_sent is False
        assert task.notification_error == "机器人不可用"

    def test_exception_marks_not_sent(self) -> None:
        from apps.document_recognition.tasks import _send_recognition_notification

        task = _task(status=DocumentRecognitionStatus.SUCCESS)
        result = SimpleNamespace(binding=self._binding(), file_path="/tmp/renamed.pdf")
        with patch(self._NOTIFY) as notify_cls:
            notify_cls.return_value.send_notification.side_effect = RuntimeError("通知服务异常")
            _send_recognition_notification(task, result)

        task.refresh_from_db()
        assert task.notification_sent is False
        assert "通知服务异常" in task.notification_error
