"""CaseLogServiceAdapter 单元测试：委托透传 + 跨模块 create_log_internal。"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.cases.services.log.caselog_service_adapter import CaseLogServiceAdapter
from apps.core.exceptions import NotFoundError
from apps.testing.factories import CaseFactory, CaseLogFactory, LawyerFactory


def _make_adapter() -> tuple[CaseLogServiceAdapter, MagicMock]:
    caselog = MagicMock()
    return CaseLogServiceAdapter(caselog_service=caselog), caselog


class TestLazyInit:
    def test_caselog_service_lazy_created_once(self) -> None:
        adapter = CaseLogServiceAdapter()
        first = adapter.caselog_service
        assert first is not None
        assert adapter.caselog_service is first


class TestDelegation:
    def test_list_logs(self) -> None:
        adapter, caselog = _make_adapter()
        caselog.list_logs.return_value = ["log"]
        assert adapter.list_logs(case_id=1, user="u", org_access={"a": 1}, perm_open_access=False) == ["log"]
        caselog.list_logs.assert_called_once_with(case_id=1, user="u", org_access={"a": 1}, perm_open_access=False)

    def test_get_log(self) -> None:
        adapter, caselog = _make_adapter()
        caselog.get_log.return_value = "log"
        assert adapter.get_log(log_id=3, user="u") == "log"
        caselog.get_log.assert_called_once_with(log_id=3, user="u", org_access=None, perm_open_access=False)

    def test_create_log_uses_open_access(self) -> None:
        adapter, caselog = _make_adapter()
        caselog.create_log.return_value = "new-log"
        result = adapter.create_log(case_id=1, content="内容", user="u", reminder_type="general", reminder_time="t")
        assert result == "new-log"
        caselog.create_log.assert_called_once_with(
            case_id=1,
            content="内容",
            user="u",
            reminder_type="general",
            reminder_time="t",
            perm_open_access=True,
        )

    def test_update_log(self) -> None:
        adapter, caselog = _make_adapter()
        caselog.update_log.return_value = "updated"
        assert adapter.update_log(log_id=3, data={"content": "x"}) == "updated"
        caselog.update_log.assert_called_once_with(
            log_id=3, data={"content": "x"}, user=None, org_access=None, perm_open_access=False
        )

    def test_delete_log(self) -> None:
        adapter, caselog = _make_adapter()
        caselog.delete_log.return_value = {"success": True}
        assert adapter.delete_log(log_id=3) == {"success": True}
        caselog.delete_log.assert_called_once_with(log_id=3, user=None, org_access=None, perm_open_access=False)

    def test_upload_attachments(self) -> None:
        adapter, caselog = _make_adapter()
        caselog.upload_attachments.return_value = {"count": 1}
        assert adapter.upload_attachments(log_id=3, files=["f"]) == {"count": 1}
        caselog.upload_attachments.assert_called_once_with(
            log_id=3, files=["f"], user=None, org_access=None, perm_open_access=False
        )


@pytest.mark.django_db
class TestCreateLogInternal:
    def test_success_returns_log_id(self) -> None:
        case = CaseFactory()
        actor = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")

        log_id = CaseLogServiceAdapter().create_log_internal(case.id, "跨模块日志", user_id=actor.id)

        assert isinstance(log_id, int)
        log = CaseLogFactory(case=case, content="跨模块日志")
        assert log.case_id == case.id

    def test_missing_case_raises(self) -> None:
        with pytest.raises(NotFoundError, match="不存在"):
            CaseLogServiceAdapter().create_log_internal(99999, "内容")

    def test_created_log_readable(self) -> None:
        from apps.cases.models import CaseLog

        case = CaseFactory()
        actor = LawyerFactory(username=f"lawyer-{uuid4().hex[:8]}")
        log_id = CaseLogServiceAdapter().create_log_internal(case.id, "内部内容", user_id=actor.id)
        log = CaseLog.objects.get(id=log_id)
        assert log.content == "内部内容"
        assert log.case_id == case.id
        assert log.actor_id == actor.id
