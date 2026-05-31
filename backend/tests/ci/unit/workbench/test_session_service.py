"""Unit tests for WorkbenchSessionService."""

from __future__ import annotations

import pytest

from apps.core.exceptions import NotFoundError
from apps.workbench.models import WorkbenchMessage, WorkbenchSession
from apps.workbench.services.session_service import WorkbenchSessionService

@pytest.fixture
def svc() -> WorkbenchSessionService:
    return WorkbenchSessionService()

@pytest.fixture
def user(db):
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_user(
        username="test_workbench_user",
        email="workbench@example.com",
        real_name="测试用户",
    )

@pytest.fixture
def other_user(db):
    from apps.organization.models import Lawyer

    return Lawyer.objects.create_user(
        username="other_workbench_user",
        email="other_wb@example.com",
        real_name="其他用户",
    )

class TestCreateSession:
    def test_create_with_user(self, svc, user) -> None:
        session = svc.create_session(title="测试会话", llm_model="gpt-4", user=user)
        assert session.id is not None
        assert session.title == "测试会话"
        assert session.llm_model == "gpt-4"
        assert session.user == user

    def test_create_without_user(self, svc) -> None:
        session = svc.create_session(title="匿名会话")
        assert session.id is not None
        assert session.user is None

class TestListSessions:
    def test_list_returns_user_sessions(self, svc, user) -> None:
        svc.create_session(title="会话1", user=user)
        svc.create_session(title="会话2", user=user)
        result = svc.list_sessions(user=user)
        assert result["count"] == 2
        assert len(result["items"]) == 2

    def test_list_excludes_other_users(self, svc, user, other_user) -> None:
        svc.create_session(title="我的会话", user=user)
        svc.create_session(title="别人的会话", user=other_user)
        result = svc.list_sessions(user=user)
        assert result["count"] == 1
        assert result["items"][0]["title"] == "我的会话"

    def test_list_unauthenticated_returns_empty(self, svc) -> None:
        result = svc.list_sessions(user=None)
        assert result == {"items": [], "count": 0}

    def test_list_with_message_stats(self, svc, user) -> None:
        session = svc.create_session(title="有消息的会话", user=user)
        WorkbenchMessage.objects.create(session=session, role="user", content="你好")
        WorkbenchMessage.objects.create(session=session, role="assistant", content="你好！")
        result = svc.list_sessions(user=user)
        assert result["items"][0]["message_count"] == 2

    def test_list_pagination(self, svc, user) -> None:
        for i in range(5):
            svc.create_session(title=f"会话{i}", user=user)
        result = svc.list_sessions(user=user, page=1, page_size=2)
        assert result["count"] == 5
        assert len(result["items"]) == 2

class TestGetSession:
    def test_get_existing(self, svc, user) -> None:
        session = svc.create_session(title="获取测试", user=user)
        result = svc.get_session(session.id, user=user)
        assert result.title == "获取测试"

    def test_get_nonexistent_raises(self, svc, user) -> None:
        with pytest.raises(NotFoundError):
            svc.get_session(99999, user=user)

    def test_get_other_users_raises(self, svc, user, other_user) -> None:
        session = svc.create_session(title="别人的", user=other_user)
        with pytest.raises(NotFoundError):
            svc.get_session(session.id, user=user)

class TestUpdateSession:
    def test_update_title(self, svc, user) -> None:
        session = svc.create_session(title="原标题", user=user)
        updated = svc.update_session(session.id, title="新标题", user=user)
        assert updated.title == "新标题"

    def test_update_model(self, svc, user) -> None:
        session = svc.create_session(llm_model="gpt-4", user=user)
        updated = svc.update_session(session.id, llm_model="claude-3", user=user)
        assert updated.llm_model == "claude-3"

class TestDeleteSession:
    def test_delete(self, svc, user) -> None:
        session = svc.create_session(title="待删除", user=user)
        svc.delete_session(session.id, user=user)
        with pytest.raises(NotFoundError):
            svc.get_session(session.id, user=user)
