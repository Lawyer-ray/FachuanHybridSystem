"""express_query 会话服务单元测试：解析、加锁、状态流转。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.express_query.models import ExpressSession, ExpressSessionStatus
from apps.express_query.services.session_service import (
    SessionUnavailableError,
    get_or_create_session,
    mark_login_expired,
    mark_login_success,
    mark_verified,
    resolve_session,
    session_lock,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@pytest.mark.django_db
class TestSessionResolve:
    def test_get_or_create_is_idempotent(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")

        first = get_or_create_session(lawyer, "ems")
        second = get_or_create_session(lawyer, "ems")

        assert first.id == second.id
        assert ExpressSession.objects.filter(lawyer=lawyer, carrier_type="ems").count() == 1
        assert first.status == ExpressSessionStatus.EMPTY

    def test_profile_key_is_per_lawyer_carrier(self, django_user_model) -> None:
        a = django_user_model.objects.create_user(username="lawyer_a", password="x")
        b = django_user_model.objects.create_user(username="lawyer_b", password="x")

        sa = get_or_create_session(a, "ems")
        sb = get_or_create_session(b, "ems")
        sf = get_or_create_session(a, "sf")

        assert sa.profile_key == f"ems_{a.id}"
        assert sb.profile_key == f"ems_{b.id}"
        assert sf.profile_key == f"sf_{a.id}"
        assert len({sa.profile_key, sb.profile_key, sf.profile_key}) == 3

    def test_task_without_owner_falls_back_to_none(self) -> None:
        task = MagicMock()
        task.created_by = None
        task.id = 1
        task.carrier_type = "ems"

        assert resolve_session(task) is None


@pytest.mark.django_db
class TestSessionLock:
    def test_lock_is_exclusive(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        session = get_or_create_session(lawyer, "ems")

        with session_lock(session):
            with pytest.raises(SessionUnavailableError):
                with session_lock(session):
                    pass

    def test_lock_released_after_exit(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        session = get_or_create_session(lawyer, "ems")
        key = f"express_query:session_lock:{session.id}"

        with session_lock(session):
            assert cache.get(key) is not None

        # 退出后锁必须被释放，否则下次任务永远拿不到
        assert cache.get(key) is None

        with session_lock(session):
            assert cache.get(key) is not None

    def test_lock_released_on_exception(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        session = get_or_create_session(lawyer, "ems")
        key = f"express_query:session_lock:{session.id}"

        # 用辅助函数抛错（而非裸 raise）：既保持「块内抛异常」的真实语义，
        # 又避开 CodeQL 对 contextmanager 内 raise 后线性流程的不可达误判。
        with pytest.raises(RuntimeError):
            with session_lock(session):
                _raise_boom()

        # 异常退出后锁必须已释放，否则后续任务永远拿不到
        assert cache.get(key) is None

        # 且必须能重新拿到，真正验证可重入（而不是靠一个空 pass 块）
        with session_lock(session):
            assert cache.get(key) is not None


def _raise_boom() -> None:
    raise RuntimeError("boom")

    def test_none_session_is_noop(self) -> None:
        # 无会话（无归属律师的历史任务）不加锁：嵌套获取也不应抛错
        with session_lock(None):
            with session_lock(None):
                entered = True
        assert entered


@pytest.mark.django_db
class TestSessionStateTransitions:
    def test_mark_login_success(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        session = get_or_create_session(lawyer, "ems")

        mark_login_success(session)
        session.refresh_from_db()

        assert session.status == ExpressSessionStatus.ACTIVE
        assert session.is_ready
        assert session.last_login_at is not None
        assert session.last_verified_at is not None
        assert session.last_error == ""

    def test_mark_login_expired(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        session = get_or_create_session(lawyer, "ems")

        mark_login_expired(session, "cookie 失效")
        session.refresh_from_db()

        assert session.status == ExpressSessionStatus.EXPIRED
        assert not session.is_ready
        assert session.last_error == "cookie 失效"

    def test_mark_verified_keeps_status(self, django_user_model) -> None:
        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        session = get_or_create_session(lawyer, "ems")
        mark_login_success(session)

        with patch("apps.express_query.services.session_service.timezone") as tz:
            from django.utils import timezone as real_tz

            tz.now.return_value = real_tz.now()
            mark_verified(session)

        session.refresh_from_db()
        assert session.status == ExpressSessionStatus.ACTIVE
        assert session.last_verified_at is not None


@pytest.mark.django_db
class TestUniqueConstraint:
    def test_one_session_per_lawyer_carrier(self, django_user_model) -> None:
        from django.db import IntegrityError

        lawyer = django_user_model.objects.create_user(username="lawyer_a", password="x")
        ExpressSession.objects.create(lawyer=lawyer, carrier_type="ems")

        with pytest.raises(IntegrityError):
            ExpressSession.objects.create(lawyer=lawyer, carrier_type="ems")
