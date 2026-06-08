"""workbench 模块单元测试

覆盖文件:
- apps/workbench/models/session.py
- apps/workbench/models/message.py
- apps/workbench/models/batch_job.py
- apps/workbench/services/session_service.py
- apps/workbench/services/message_service.py
- apps/workbench/schemas/workbench_schemas.py
- apps/workbench/schemas/batch_schemas.py
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ==================== Models ====================


class TestSessionStatus:
    """SessionStatus 枚举测试"""

    def test_session_status(self):
        from apps.workbench.models.session import SessionStatus

        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.ARCHIVED == "archived"


class TestWorkbenchSessionModel:
    """WorkbenchSession 模型测试"""

    def test_str_with_title(self, db):
        from apps.workbench.models.session import WorkbenchSession

        session = WorkbenchSession.objects.create(title="测试会话")
        assert str(session) == "测试会话"

    def test_str_without_title(self, db):
        from apps.workbench.models.session import WorkbenchSession

        session = WorkbenchSession.objects.create(title="")
        assert len(str(session)) == 8  # UUID 前8位

    def test_meta(self):
        from apps.workbench.models.session import WorkbenchSession

        assert WorkbenchSession._meta.db_table == "workbench_session"
        assert WorkbenchSession._meta.verbose_name == "工作台会话"


class TestWorkbenchMessageModel:
    """WorkbenchMessage 模型测试"""

    def test_role_choices(self):
        from apps.workbench.models.message import WorkbenchMessage

        assert WorkbenchMessage.Role.SYSTEM == "system"
        assert WorkbenchMessage.Role.USER == "user"
        assert WorkbenchMessage.Role.ASSISTANT == "assistant"
        assert WorkbenchMessage.Role.TOOL == "tool"

    def test_str_with_content(self, db):
        from apps.workbench.models.message import WorkbenchMessage
        from apps.workbench.models.session import WorkbenchSession

        session = WorkbenchSession.objects.create(title="会话")
        msg = WorkbenchMessage(session=session, role="user", content="你好，这是一条很长的测试消息" * 5)
        result = str(msg)
        assert result.startswith("[user]")
        assert len(result) <= 60

    def test_str_without_content(self, db):
        from apps.workbench.models.message import WorkbenchMessage
        from apps.workbench.models.session import WorkbenchSession

        session = WorkbenchSession.objects.create(title="会话")
        msg = WorkbenchMessage(session=session, role="tool", content="", tool_name="search")
        result = str(msg)
        assert "[tool]" in result
        assert "search" in result

    def test_meta(self):
        from apps.workbench.models.message import WorkbenchMessage

        assert WorkbenchMessage._meta.db_table == "workbench_message"


# ==================== Session Service ====================


class TestWorkbenchSessionService:
    """WorkbenchSessionService 测试"""

    @pytest.fixture
    def wb_lawyer(self, db):
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="Workbench测试律所")
        return Lawyer.objects.create_user(
            username="wblawyer",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
        )

    def _make_service(self):
        from apps.workbench.services.session_service import WorkbenchSessionService

        return WorkbenchSessionService()

    def test_create_session(self, db):
        service = self._make_service()
        session = service.create_session(title="新会话", llm_model="gpt-4")
        assert session.title == "新会话"
        assert session.llm_model == "gpt-4"

    def test_create_session_with_user(self, db, wb_lawyer):
        service = self._make_service()
        session = service.create_session(title="用户会话", user=wb_lawyer)
        assert session.user == wb_lawyer

    def test_create_session_without_user(self, db):
        service = self._make_service()
        session = service.create_session(title="匿名会话")
        assert session.user is None

    def test_list_sessions_no_user(self, db):
        service = self._make_service()
        result = service.list_sessions(user=None)
        assert result == {"items": [], "count": 0}

    def test_list_sessions_not_authenticated(self, db):
        service = self._make_service()
        user = SimpleNamespace(is_authenticated=False)
        result = service.list_sessions(user=user)
        assert result == {"items": [], "count": 0}

    def test_list_sessions_with_user(self, db, wb_lawyer):
        service = self._make_service()
        service.create_session(title="会话1", user=wb_lawyer)
        service.create_session(title="会话2", user=wb_lawyer)
        result = service.list_sessions(user=wb_lawyer)
        assert result["count"] == 2
        assert len(result["items"]) == 2

    def test_list_sessions_pagination(self, db, wb_lawyer):
        service = self._make_service()
        for i in range(5):
            service.create_session(title=f"会话{i}", user=wb_lawyer)
        result = service.list_sessions(user=wb_lawyer, page=1, page_size=2)
        assert result["count"] == 5
        assert len(result["items"]) == 2

    def test_get_session(self, db, wb_lawyer):
        service = self._make_service()
        session = service.create_session(title="详情", user=wb_lawyer)
        result = service.get_session(session.id, user=wb_lawyer)
        assert result.title == "详情"

    def test_get_session_not_found(self, db, wb_lawyer):
        from apps.core.exceptions import NotFoundError

        service = self._make_service()
        with pytest.raises(NotFoundError):
            service.get_session(999999, user=wb_lawyer)

    def test_update_session(self, db, wb_lawyer):
        service = self._make_service()
        session = service.create_session(title="旧标题", user=wb_lawyer)
        result = service.update_session(session.id, title="新标题", user=wb_lawyer)
        assert result.title == "新标题"

    def test_update_session_model(self, db, wb_lawyer):
        service = self._make_service()
        session = service.create_session(title="会话", llm_model="gpt-4", user=wb_lawyer)
        result = service.update_session(session.id, llm_model="claude-3", user=wb_lawyer)
        assert result.llm_model == "claude-3"

    def test_update_session_status(self, db, wb_lawyer):
        service = self._make_service()
        session = service.create_session(title="会话", user=wb_lawyer)
        result = service.update_session(session.id, status="archived", user=wb_lawyer)
        assert result.status == "archived"

    def test_delete_session(self, db, wb_lawyer):
        service = self._make_service()
        session = service.create_session(title="待删除", user=wb_lawyer)
        service.delete_session(session.id, user=wb_lawyer)
        with pytest.raises(Exception):
            service.get_session(session.id, user=wb_lawyer)

    def test_get_user_session_not_found(self, db, wb_lawyer):
        from apps.core.exceptions import NotFoundError

        service = self._make_service()
        with pytest.raises(NotFoundError):
            service.get_user_session(wb_lawyer, 999999)

    def test_increment_storage(self, db):
        from apps.workbench.models.session import WorkbenchSession

        service = self._make_service()
        session = service.create_session(title="存储测试")
        WorkbenchSessionService = type(service)
        WorkbenchSessionService.increment_storage(session.id, 1024)
        session.refresh_from_db()
        assert session.storage_bytes == 1024

    def test_increment_storage_zero_delta(self, db):
        service = self._make_service()
        session = service.create_session(title="零增量")
        # Should not raise
        service.increment_storage(session.id, 0)


# ==================== Message Service ====================


class TestWorkbenchMessageService:
    """WorkbenchMessageService 测试"""

    @pytest.fixture
    def msg_lawyer(self, db):
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="Msg测试律所")
        return Lawyer.objects.create_user(
            username="msglawyer",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
        )

    def _make_service(self):
        from apps.workbench.services.message_service import WorkbenchMessageService

        return WorkbenchMessageService()

    def test_list_messages_empty(self, db, msg_lawyer):
        from apps.workbench.services.session_service import WorkbenchSessionService

        session_svc = WorkbenchSessionService()
        session = session_svc.create_session(title="空消息", user=msg_lawyer)

        msg_svc = self._make_service()
        result = msg_svc.list_messages(session.id, user=msg_lawyer)
        assert result["count"] == 0
        assert result["items"] == []

    def test_submit_feedback_invalid_rating(self, db, msg_lawyer):
        from apps.core.exceptions import ValidationException
        from apps.workbench.models.message import WorkbenchMessage
        from apps.workbench.models.session import WorkbenchSession

        session = WorkbenchSession.objects.create(title="反馈测试")
        msg = WorkbenchMessage.objects.create(session=session, role="assistant", content="回复")

        msg_svc = self._make_service()
        with pytest.raises(ValidationException, match="rating"):
            msg_svc.submit_feedback(msg.id, rating="invalid", user=msg_lawyer)

    def test_submit_feedback_message_not_found(self, db, msg_lawyer):
        from apps.core.exceptions import NotFoundError

        msg_svc = self._make_service()
        with pytest.raises(NotFoundError):
            msg_svc.submit_feedback(999999, rating="good", user=msg_lawyer)


# ==================== Batch Job Model ====================


class TestBatchJobModel:
    """BatchJob 模型测试"""

    def test_batch_job_model_exists(self):
        from apps.workbench.models.batch_job import BatchJob

        assert BatchJob is not None


# ==================== Schemas ====================


class TestWorkbenchSchemas:
    """Schema 测试"""

    def test_schemas_module_exists(self):
        from apps.workbench.schemas import workbench_schemas

        assert workbench_schemas is not None

    def test_batch_schemas_module_exists(self):
        from apps.workbench.schemas import batch_schemas

        assert batch_schemas is not None


# ==================== _calc_message_bytes ====================


class TestCalcMessageBytes:
    """_calc_message_bytes 测试"""

    def test_empty(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes()
        assert result >= 0

    def test_with_content(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(content="你好世界")
        assert result > 0

    def test_with_tool_input(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(tool_input={"key": "value"})
        assert result > 0

    def test_with_tool_output(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(tool_output={"result": "ok"})
        assert result > 0

    def test_with_metadata(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(metadata={"feedback": "good"})
        assert result > 0

    def test_all_fields(self):
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(
            content="测试",
            tool_input={"a": 1},
            tool_output={"b": 2},
            metadata={"c": 3},
        )
        assert result > 0
