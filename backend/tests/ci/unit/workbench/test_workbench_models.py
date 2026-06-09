"""workbench app Model 单元测试

覆盖 BatchJob, BatchJobItem, WorkbenchMessage, WorkbenchSession 的
__str__、choices、property。
"""

import pytest
import uuid

from apps.testing.factories import LawyerFactory
from apps.workbench.models.batch_job import BatchJob, BatchJobItem, BatchJobStatus
from apps.workbench.models.message import WorkbenchMessage
from apps.workbench.models.session import SessionStatus, WorkbenchSession


# ============================================================
# WorkbenchSession
# ============================================================


@pytest.mark.django_db
class TestWorkbenchSession:
    def test_str_with_title(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(
            user=lawyer,
            title="测试会话",
        )
        assert str(session) == "测试会话"

    def test_str_without_title(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer, title="")
        result = str(session)
        assert len(result) == 8  # session_id[:8]

    def test_status_choices(self):
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.ARCHIVED.value == "archived"

    def test_default_status(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer)
        assert session.status == SessionStatus.ACTIVE

    def test_default_storage_bytes(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer)
        assert session.storage_bytes == 0


# ============================================================
# WorkbenchMessage
# ============================================================


@pytest.mark.django_db
class TestWorkbenchMessage:
    def test_str_with_content(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer)
        msg = WorkbenchMessage.objects.create(
            session=session,
            role=WorkbenchMessage.Role.USER,
            content="请帮我分析这个案件",
        )
        result = str(msg)
        assert "[user]" in result
        assert "请帮我分析这个案件" in result

    def test_str_with_tool_name(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer)
        msg = WorkbenchMessage.objects.create(
            session=session,
            role=WorkbenchMessage.Role.TOOL,
            content="",
            tool_name="search_cases",
        )
        result = str(msg)
        assert "[tool]" in result
        assert "search_cases" in result

    def test_str_content_truncation(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer)
        long_content = "A" * 100
        msg = WorkbenchMessage.objects.create(
            session=session,
            role=WorkbenchMessage.Role.ASSISTANT,
            content=long_content,
        )
        result = str(msg)
        # __str__ 用 content[:50]，加上 "[assistant] " 前缀共 62 字符
        assert len(result) == len("[assistant] ") + 50

    def test_role_choices(self):
        assert WorkbenchMessage.Role.SYSTEM.value == "system"
        assert WorkbenchMessage.Role.USER.value == "user"
        assert WorkbenchMessage.Role.ASSISTANT.value == "assistant"
        assert WorkbenchMessage.Role.TOOL.value == "tool"


# ============================================================
# BatchJob
# ============================================================


@pytest.mark.django_db
class TestBatchJob:
    def _make_session(self):
        lawyer = LawyerFactory()
        return WorkbenchSession.objects.create(user=lawyer)

    def test_str(self):
        session = self._make_session()
        job = BatchJob.objects.create(
            session=session,
            prompt="分析证据",
            status=BatchJobStatus.PENDING,
        )
        result = str(job)
        assert "BatchJob" in result
        assert "待处理" in result

    def test_status_choices(self):
        assert BatchJobStatus.PENDING.value == "pending"
        assert BatchJobStatus.RUNNING.value == "running"
        assert BatchJobStatus.COMPLETED.value == "completed"
        assert BatchJobStatus.FAILED.value == "failed"
        assert BatchJobStatus.CANCELLED.value == "cancelled"

    def test_default_values(self):
        session = self._make_session()
        job = BatchJob.objects.create(session=session, prompt="测试")
        assert job.job_type == "doc_analysis"
        assert job.status == BatchJobStatus.PENDING
        assert job.total_items == 0
        assert job.completed_items == 0
        assert job.failed_items == 0
        assert job.progress == 0
        assert job.cancel_requested is False

    def test_uuid_primary_key(self):
        session = self._make_session()
        job = BatchJob.objects.create(session=session, prompt="UUID测试")
        assert isinstance(job.id, uuid.UUID)


# ============================================================
# BatchJobItem
# ============================================================


@pytest.mark.django_db
class TestBatchJobItem:
    def _make_job(self):
        lawyer = LawyerFactory()
        session = WorkbenchSession.objects.create(user=lawyer)
        return BatchJob.objects.create(session=session, prompt="测试")

    def test_str(self):
        job = self._make_job()
        item = BatchJobItem.objects.create(
            job=job,
            file_name="证据1.pdf",
            status=BatchJobStatus.PENDING,
        )
        result = str(item)
        assert "证据1.pdf" in result
        assert "待处理" in result

    def test_uuid_primary_key(self):
        job = self._make_job()
        item = BatchJobItem.objects.create(
            job=job,
            file_name="test.pdf",
        )
        assert isinstance(item.id, uuid.UUID)

    def test_default_status(self):
        job = self._make_job()
        item = BatchJobItem.objects.create(job=job, file_name="test.pdf")
        assert item.status == BatchJobStatus.PENDING
