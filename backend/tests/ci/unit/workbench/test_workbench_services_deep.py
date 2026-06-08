"""Tests for workbench.api.workbench_api and workbench.services.batch_service, message_service, chat_service."""
from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.cache import cache

from apps.organization.models import LawFirm, Lawyer
from apps.workbench.models import BatchJob, BatchJobItem, BatchJobStatus, WorkbenchMessage, WorkbenchSession
from apps.workbench.schemas import BatchJobOut
from apps.workbench.services.batch_service import BatchAnalysisService, _is_excel
from apps.workbench.services.message_service import WorkbenchMessageService
from apps.workbench.services.session_service import WorkbenchSessionService, _calc_message_bytes


@pytest.fixture
def wb_user(db: Any) -> Any:
    firm = LawFirm.objects.create(name="测试律所_WB")
    return Lawyer.objects.create_user(
        username="wb_test_user",
        email="wb@example.com",
        real_name="工作台用户",
        law_firm=firm,
    )


@pytest.fixture
def wb_other_user(db: Any) -> Any:
    firm = LawFirm.objects.create(name="其他律所_WB")
    return Lawyer.objects.create_user(
        username="wb_other_user",
        email="wb_other@example.com",
        real_name="其他用户",
        law_firm=firm,
    )


# ---------------------------------------------------------------------------
# session_service helpers
# ---------------------------------------------------------------------------


class TestCalcMessageBytes:
    def test_empty(self) -> None:
        result = _calc_message_bytes()
        assert result > 0  # len of str({}) encoded

    def test_content_only(self) -> None:
        result = _calc_message_bytes(content="hello")
        assert result > 0

    def test_all_fields(self) -> None:
        result = _calc_message_bytes(
            content="test",
            tool_input={"key": "value"},
            tool_output={"out": 1},
            metadata={"m": True},
        )
        assert result > 0


# ---------------------------------------------------------------------------
# WorkbenchSessionService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWorkbenchSessionService:
    def setup_method(self) -> None:
        self.svc = WorkbenchSessionService()

    def test_create_session_authenticated(self, wb_user: Any) -> None:
        session = self.svc.create_session(title="T", llm_model="gpt-4", user=wb_user)
        assert session.title == "T"
        assert session.llm_model == "gpt-4"
        assert session.user == wb_user

    def test_create_session_anonymous(self) -> None:
        session = self.svc.create_session(title="Anon", user=None)
        assert session.user is None

    def test_list_sessions_unauthenticated(self) -> None:
        result = self.svc.list_sessions(user=None)
        assert result == {"items": [], "count": 0}

    def test_list_sessions_authenticated(self, wb_user: Any) -> None:
        self.svc.create_session(title="S1", user=wb_user)
        cache.clear()
        result = self.svc.list_sessions(user=wb_user)
        assert result["count"] >= 1

    def test_list_sessions_caching(self, wb_user: Any) -> None:
        self.svc.create_session(title="Cached", user=wb_user)
        cache.clear()
        result1 = self.svc.list_sessions(user=wb_user, page=1)
        result2 = self.svc.list_sessions(user=wb_user, page=1)
        assert result1["count"] == result2["count"]

    def test_list_sessions_pagination(self, wb_user: Any) -> None:
        for i in range(5):
            self.svc.create_session(title=f"P{i}", user=wb_user)
        cache.clear()
        result = self.svc.list_sessions(user=wb_user, page=1, page_size=2)
        assert result["count"] == 5
        assert len(result["items"]) == 2

    def test_get_session_not_found(self, wb_user: Any) -> None:
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            self.svc.get_user_session(wb_user, 999999)

    def test_update_session(self, wb_user: Any) -> None:
        session = self.svc.create_session(title="Old", user=wb_user)
        updated = self.svc.update_session(session.id, title="New", user=wb_user)
        assert updated.title == "New"

    def test_update_session_model(self, wb_user: Any) -> None:
        session = self.svc.create_session(llm_model="gpt-4", user=wb_user)
        updated = self.svc.update_session(session.id, llm_model="claude-3", user=wb_user)
        assert updated.llm_model == "claude-3"

    def test_update_session_status(self, wb_user: Any) -> None:
        session = self.svc.create_session(title="St", user=wb_user)
        updated = self.svc.update_session(session.id, status="archived", user=wb_user)
        assert updated.status == "archived"

    def test_delete_session(self, wb_user: Any) -> None:
        session = self.svc.create_session(title="Del", user=wb_user)
        self.svc.delete_session(session.id, user=wb_user)
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            self.svc.get_user_session(wb_user, session.id)

    def test_increment_storage(self, wb_user: Any) -> None:
        session = self.svc.create_session(title="Stor", user=wb_user)
        WorkbenchSessionService.increment_storage(session.id, 100)
        session.refresh_from_db()
        assert session.storage_bytes >= 100

    def test_increment_storage_zero_delta(self, wb_user: Any) -> None:
        session = self.svc.create_session(title="NoStor", user=wb_user)
        original = session.storage_bytes
        WorkbenchSessionService.increment_storage(session.id, 0)
        session.refresh_from_db()
        assert session.storage_bytes == original

    def test_invalidate_cache_no_user(self) -> None:
        WorkbenchSessionService._invalidate_session_cache(None)

    def test_invalidate_cache_unauthenticated(self) -> None:
        user = MagicMock()
        user.is_authenticated = False
        WorkbenchSessionService._invalidate_session_cache(user)

    def test_get_other_user_session_raises(self, wb_user: Any, wb_other_user: Any) -> None:
        session = self.svc.create_session(title="Other's", user=wb_other_user)
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            self.svc.get_user_session(wb_user, session.id)


# ---------------------------------------------------------------------------
# WorkbenchMessageService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWorkbenchMessageService:
    def setup_method(self) -> None:
        self.session_svc = WorkbenchSessionService()
        self.msg_svc = WorkbenchMessageService(session_service=self.session_svc)

    def test_list_messages_empty(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="MsgTest", user=wb_user)
        result = self.msg_svc.list_messages(session.id, user=wb_user)
        assert result["count"] == 0
        assert result["items"] == []

    def test_list_messages_with_data(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="MsgTest2", user=wb_user)
        WorkbenchMessage.objects.create(session_id=session.id, role="user", content="Hello")
        WorkbenchMessage.objects.create(session_id=session.id, role="assistant", content="Hi")
        result = self.msg_svc.list_messages(session.id, user=wb_user)
        assert result["count"] == 2

    def test_list_messages_cursor_pagination(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="CurTest", user=wb_user)
        msg1 = WorkbenchMessage.objects.create(session_id=session.id, role="user", content="M1")
        msg2 = WorkbenchMessage.objects.create(session_id=session.id, role="user", content="M2")
        result = self.msg_svc.list_messages(session.id, before_id=msg2.id, user=wb_user)
        assert result["count"] >= 1

    def test_list_messages_cursor_nonexistent(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="CurTest2", user=wb_user)
        result = self.msg_svc.list_messages(session.id, before_id=999999, user=wb_user)
        assert result == {"items": [], "count": 0, "has_more": False}

    def test_truncate_messages(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="TruncTest", user=wb_user)
        msg1 = WorkbenchMessage.objects.create(session_id=session.id, role="user", content="T1")
        msg2 = WorkbenchMessage.objects.create(session_id=session.id, role="assistant", content="T2")
        self.msg_svc.truncate_messages(session.id, msg1.id, user=wb_user)
        remaining = WorkbenchMessage.objects.filter(session_id=session.id).count()
        assert remaining == 0

    def test_truncate_messages_not_found(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="TruncTest2", user=wb_user)
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            self.msg_svc.truncate_messages(session.id, 999999, user=wb_user)

    def test_submit_feedback_good(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="FbTest", user=wb_user)
        msg = WorkbenchMessage.objects.create(session_id=session.id, role="assistant", content="Ans")
        self.msg_svc.submit_feedback(msg.id, rating="good", user=wb_user)
        msg.refresh_from_db()
        assert msg.metadata["feedback"]["rating"] == "good"

    def test_submit_feedback_bad_with_comment(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="FbTest2", user=wb_user)
        msg = WorkbenchMessage.objects.create(session_id=session.id, role="assistant", content="Ans")
        self.msg_svc.submit_feedback(msg.id, rating="bad", comment="wrong", user=wb_user)
        msg.refresh_from_db()
        assert msg.metadata["feedback"]["comment"] == "wrong"

    def test_submit_feedback_invalid_rating(self, wb_user: Any) -> None:
        session = self.session_svc.create_session(title="FbTest3", user=wb_user)
        msg = WorkbenchMessage.objects.create(session_id=session.id, role="assistant", content="Ans")
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            self.msg_svc.submit_feedback(msg.id, rating="neutral", user=wb_user)

    def test_submit_feedback_message_not_found(self, wb_user: Any) -> None:
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            self.msg_svc.submit_feedback(999999, rating="good", user=wb_user)

    @pytest.mark.django_db
    def test_message_to_dict(self, wb_user: Any) -> None:
        session = WorkbenchSession.objects.create(title="dt", user=wb_user)
        msg = WorkbenchMessage.objects.create(session_id=session.id, role="user", content="test")
        result = WorkbenchMessageService._message_to_dict(msg)
        assert isinstance(result, dict)
        assert "content" in result


# ---------------------------------------------------------------------------
# BatchAnalysisService
# ---------------------------------------------------------------------------


class TestIsExcel:
    def test_xlsx(self) -> None:
        assert _is_excel("data.xlsx") is True

    def test_xls(self) -> None:
        assert _is_excel("file.xls") is True

    def test_docx(self) -> None:
        assert _is_excel("file.docx") is False

    def test_no_extension(self) -> None:
        assert _is_excel("noext") is False

    def test_empty_string(self) -> None:
        assert _is_excel("") is False

    def test_uppercase(self) -> None:
        assert _is_excel("DATA.XLSX") is True


@pytest.mark.django_db
class TestBatchAnalysisService:
    def setup_method(self) -> None:
        self.svc = BatchAnalysisService()

    def test_validate_files_empty(self) -> None:
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException, match="至少一个文件"):
            self.svc.validate_files([])

    def test_validate_files_invalid_ext(self) -> None:
        from apps.core.exceptions import ValidationException
        f = MagicMock()
        f.name = "test.pdf"
        with pytest.raises(ValidationException, match="不支持"):
            self.svc.validate_files([f])

    def test_validate_files_valid(self) -> None:
        f = MagicMock()
        f.name = "test.docx"
        self.svc.validate_files([f])

    def test_validate_files_valid_xls(self) -> None:
        f = MagicMock()
        f.name = "data.xlsx"
        self.svc.validate_files([f])

    def test_get_job_by_id_not_found(self) -> None:
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            self.svc.get_job_by_id(uuid.uuid4())

    def test_mark_completed(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=1
        )
        self.svc.mark_completed(job.id, "Done!")
        job.refresh_from_db()
        assert job.status == BatchJobStatus.COMPLETED
        assert job.summary == "Done!"
        assert job.progress == 100

    def test_mark_failed(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=1
        )
        self.svc.mark_failed(job.id, "Error occurred")
        job.refresh_from_db()
        assert job.status == BatchJobStatus.FAILED
        assert "Error" in job.error_message

    def test_mark_failed_truncates_long_error(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=1
        )
        long_error = "x" * 5000
        self.svc.mark_failed(job.id, long_error)
        job.refresh_from_db()
        assert len(job.error_message) <= 4000

    def test_get_failed_items_detail(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=2
        )
        BatchJobItem.objects.create(
            job=job, file_name="a.docx", status=BatchJobStatus.FAILED, error="err1"
        )
        BatchJobItem.objects.create(
            job=job, file_name="b.docx", status=BatchJobStatus.COMPLETED
        )
        detail = self.svc.get_failed_items_detail(job.id)
        assert len(detail) == 1
        assert detail[0]["error"] == "err1"

    def test_list_batch_jobs(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=1
        )
        result = self.svc.list_batch_jobs(session.id)
        assert result["count"] >= 1

    def test_list_batch_jobs_pagination(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        for i in range(5):
            BatchJob.objects.create(
                session_id=session.id, job_type="doc_analysis", prompt=f"p{i}", total_items=1
            )
        result = self.svc.list_batch_jobs(session.id, page=1, page_size=2)
        assert result["count"] == 5
        assert len(result["items"]) == 2

    def test_retry_failed_not_in_terminal_state(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p",
            total_items=1, status=BatchJobStatus.RUNNING
        )
        result = self.svc.retry_failed(job.id)
        assert result["success"] is False

    def test_retry_failed_no_failed_items(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p",
            total_items=1, status=BatchJobStatus.COMPLETED
        )
        result = self.svc.retry_failed(job.id)
        assert result["success"] is False
        assert "没有失败" in result["message"]

    def test_retry_failed_pending_state(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p",
            total_items=1, status=BatchJobStatus.PENDING
        )
        result = self.svc.retry_failed(job.id)
        assert result["success"] is False

    def test_request_cancel_completed_job(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p",
            total_items=1, status=BatchJobStatus.COMPLETED
        )
        result = self.svc.request_cancel(job.id)
        assert result.status == BatchJobStatus.COMPLETED

    def test_request_cancel_already_cancelled(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p",
            total_items=1, status=BatchJobStatus.CANCELLED
        )
        result = self.svc.request_cancel(job.id)
        assert result.status == BatchJobStatus.CANCELLED

    def test_get_completed_items(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=2
        )
        BatchJobItem.objects.create(job=job, file_name="a.docx", status=BatchJobStatus.COMPLETED)
        BatchJobItem.objects.create(job=job, file_name="b.docx", status=BatchJobStatus.FAILED)
        items = list(self.svc.get_completed_items(job.id))
        assert len(items) == 1

    def test_get_active_items(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=3
        )
        BatchJobItem.objects.create(job=job, file_name="a.docx", status=BatchJobStatus.RUNNING)
        BatchJobItem.objects.create(job=job, file_name="b.docx", status=BatchJobStatus.COMPLETED)
        BatchJobItem.objects.create(job=job, file_name="c.docx", status=BatchJobStatus.PENDING)
        items = list(self.svc.get_active_items(job.id))
        assert len(items) == 2  # RUNNING + COMPLETED

    def test_get_job_progress(self) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=3,
            status=BatchJobStatus.RUNNING, started_processing_at=datetime.now(),
            completed_items=1, failed_items=0
        )
        BatchJobItem.objects.create(job=job, file_name="a.docx", status=BatchJobStatus.COMPLETED)
        result_job, items = self.svc.get_job_progress(job.id)
        assert result_job.id == job.id
        assert len(items) >= 1

    def test_save_batch_messages(self, wb_user: Any) -> None:
        session = WorkbenchSession.objects.create(title="t")
        job = BatchJob.objects.create(
            session_id=session.id, job_type="doc_analysis", prompt="p", total_items=1
        )
        count = self.svc.save_batch_messages(
            job.id,
            [{"content": "Result 1", "metadata": {"key": "val"}}, {"content": "Result 2"}],
            user=wb_user,
        )
        assert count == 2
        msgs = WorkbenchMessage.objects.filter(session_id=session.id)
        assert msgs.count() == 2


# ---------------------------------------------------------------------------
# chat_service helpers
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        assert _estimate_tokens("") == 0

    def test_chinese_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("你好世界")
        assert result > 0

    def test_english_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("hello world")
        assert result > 0

    def test_mixed_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("hello你好world")
        assert result > 0

    def test_long_text(self) -> None:
        from apps.workbench.services.chat_service import _estimate_tokens
        result = _estimate_tokens("这是一段很长的中文文本" * 100)
        assert result > 100


class TestConvertModelMessages:
    def test_user_message(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        msg = SimpleNamespace(role="user", content="Hello", tool_output=None, tool_call_id=None, tool_name=None)
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_assistant_message(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        msg = SimpleNamespace(role="assistant", content="Hi", tool_output=None, tool_call_id=None, tool_name=None)
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_tool_message(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        msg = SimpleNamespace(
            role="tool", content="call",
            tool_output={"result": "ok"}, tool_call_id="tc1", tool_name="search"
        )
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_tool_message_string_output(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        msg = SimpleNamespace(
            role="tool", content="call",
            tool_output="raw string", tool_call_id="tc2", tool_name="calc"
        )
        result = _convert_to_model_messages([msg])
        assert len(result) == 1

    def test_empty_list(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        assert _convert_to_model_messages([]) == []

    def test_mixed_messages(self) -> None:
        from apps.workbench.services.chat_service import _convert_to_model_messages
        messages = [
            SimpleNamespace(role="user", content="q", tool_output=None, tool_call_id=None, tool_name=None),
            SimpleNamespace(role="assistant", content="a", tool_output=None, tool_call_id=None, tool_name=None),
        ]
        result = _convert_to_model_messages(messages)
        assert len(result) == 2


class TestChatServiceApproval:
    def test_resolve_approval_delegates(self) -> None:
        from apps.workbench.services.chat_service import WorkbenchChatService
        svc = WorkbenchChatService()
        svc.approval_manager = MagicMock()
        svc.approval_manager.resolve.return_value = True
        result = svc.resolve_approval("abc", True, user_id=1)
        assert result is True
        svc.approval_manager.resolve.assert_called_once_with("abc", True, user_id=1)

    def test_resolve_approval_reject(self) -> None:
        from apps.workbench.services.chat_service import WorkbenchChatService
        svc = WorkbenchChatService()
        svc.approval_manager = MagicMock()
        svc.approval_manager.resolve.return_value = False
        result = svc.resolve_approval("abc", False)
        assert result is False


class TestAgentMap:
    def test_agent_map_keys(self) -> None:
        from apps.workbench.services.chat_service import AGENT_MAP
        assert "triage" in AGENT_MAP
        assert "case" in AGENT_MAP
        assert "contract" in AGENT_MAP
        assert "research" in AGENT_MAP

    def test_usage_limits(self) -> None:
        from apps.workbench.services.chat_service import USAGE_LIMITS
        assert USAGE_LIMITS.request_limit == 50

    def test_constants(self) -> None:
        from apps.workbench.services.chat_service import MAX_HISTORY_TOKENS, MAX_HISTORY_MESSAGES, SUMMARY_THRESHOLD
        assert MAX_HISTORY_TOKENS > 0
        assert MAX_HISTORY_MESSAGES > 0
        assert SUMMARY_THRESHOLD > 0
