"""新增 MCP 工具的行为测试（身份 / 期限聚合 / 任务统一状态）。

这些工具与「透传型」工具不同：它们自己消费后端数据并重组输出，所以
``test_output_contract`` 覆盖不到。这里用假的 ``client`` 返回直接驱动它们，
断言真实的筛选 / 排序 / 归一化逻辑。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.utils import timezone


def _reminder(
    reminder_id: int,
    days_from_today: int,
    *,
    reminder_type: str = "hearing",
    is_completed: bool = False,
    case_id: int | None = 1,
) -> dict[str, Any]:
    due = timezone.localtime() + timedelta(days=days_from_today)
    return {
        "id": reminder_id,
        "reminder_type": reminder_type,
        "content": f"事项{reminder_id}",
        "due_at": due.isoformat(),
        "is_completed": is_completed,
        "case_id": case_id,
        "contract_id": None,
        "case_log_id": None,
    }


@pytest.fixture()
def fake_client() -> Any:
    """同时替换 deadlines 与 tasks 两个模块里的 ``client``。

    两个模块各自 ``from mcp_server.client import client``，拿到的是同一个对象但
    分别持有引用——只 patch 一个会让另一个照常打真实 HTTP。
    """
    from mcp_server.tools.core import tasks
    from mcp_server.tools.reminders import deadlines

    shared = mock.MagicMock()
    with mock.patch.object(deadlines, "client", shared), mock.patch.object(tasks, "client", shared):
        yield shared


class TestUpcomingDeadlines:
    def test_filters_by_window_and_sorts(self, fake_client: Any) -> None:
        from mcp_server.tools.reminders.deadlines import list_upcoming_deadlines

        fake_client.get.return_value = [
            _reminder(1, 5),
            _reminder(2, 1),
            _reminder(3, 30),  # 窗口外
            _reminder(4, -3),  # 已过期
        ]
        result = list_upcoming_deadlines(days=7)

        assert result["total"] == 2
        assert [item["id"] for item in result["items"]] == [2, 1], "必须按到期时间升序"
        assert result["truncated"] is False
        assert result["days"] == 7

    def test_excludes_completed_by_default(self, fake_client: Any) -> None:
        from mcp_server.tools.reminders.deadlines import list_upcoming_deadlines

        fake_client.get.return_value = [_reminder(1, 2, is_completed=True), _reminder(2, 3)]
        assert list_upcoming_deadlines(days=7)["total"] == 1
        assert list_upcoming_deadlines(days=7, include_completed=True)["total"] == 2

    def test_filters_by_reminder_type(self, fake_client: Any) -> None:
        from mcp_server.tools.reminders.deadlines import list_upcoming_deadlines

        fake_client.get.return_value = [
            _reminder(1, 1, reminder_type="hearing"),
            _reminder(2, 2, reminder_type="appeal_deadline"),
        ]
        result = list_upcoming_deadlines(days=7, reminder_type="appeal_deadline")
        assert [item["id"] for item in result["items"]] == [2]

    def test_reports_truncation(self, fake_client: Any) -> None:
        from mcp_server.tools.reminders.deadlines import list_upcoming_deadlines

        fake_client.get.return_value = [_reminder(index, 1) for index in range(1, 11)]
        result = list_upcoming_deadlines(days=7, limit=3)
        assert result["total"] == 10
        assert result["returned"] == 3
        assert result["truncated"] is True

    def test_raises_on_unexpected_shape(self, fake_client: Any) -> None:
        """后端形状变了要显式报错，不能静默返回空列表骗模型。"""
        from mcp_server.client import FachuanApiError
        from mcp_server.tools.reminders.deadlines import list_upcoming_deadlines

        fake_client.get.return_value = {"items": [], "total": 0}
        with pytest.raises(FachuanApiError, match="非数组结构"):
            list_upcoming_deadlines(days=7)


class TestRemindersByTarget:
    def test_rejects_multiple_targets(self, fake_client: Any) -> None:
        from mcp_server.tools.reminders.deadlines import list_reminders_by_target

        with pytest.raises(ValueError, match="至多传一个"):
            list_reminders_by_target(case_id=1, contract_id=2)

    def test_passes_case_id(self, fake_client: Any) -> None:
        """list_all_reminders 漏了 case_id，这里必须支持。"""
        from mcp_server.tools.reminders.deadlines import list_reminders_by_target

        fake_client.get.return_value = [_reminder(1, 1)]
        result = list_reminders_by_target(case_id=42)
        fake_client.get.assert_called_once_with("/reminders/list", params={"case_id": 42})
        assert result["total"] == 1


class TestAsyncTaskStatus:
    def test_normalizes_completed(self, fake_client: Any) -> None:
        from mcp_server.tools.core.tasks import get_async_task_status

        fake_client.get.return_value = {"status": "completed", "progress": 100}
        result = get_async_task_status("pdf_split", "7")

        assert result["finished"] is True
        assert result["failed"] is False
        assert result["progress"] == 100

    def test_computes_progress_from_pages(self, fake_client: Any) -> None:
        from mcp_server.tools.core.tasks import get_async_task_status

        fake_client.get.return_value = {"status": "running", "processed_pages": 3, "total_pages": 12}
        result = get_async_task_status("pdf_split", "7")

        assert result["progress"] == 25
        assert result["finished"] is False

    def test_marks_failure(self, fake_client: Any) -> None:
        from mcp_server.tools.core.tasks import get_async_task_status

        fake_client.get.return_value = {"status": "failed", "error_message": "OCR 超时"}
        result = get_async_task_status("archive", "9")

        assert result["failed"] is True
        assert result["error"] == "OCR 超时"

    def test_rejects_unknown_kind(self, fake_client: Any) -> None:
        from mcp_server.tools.core.tasks import get_async_task_status

        with pytest.raises(ValueError, match="未知的 kind"):
            get_async_task_status("nope", "1")
        fake_client.get.assert_not_called()


class TestServerTime:
    def test_shape(self) -> None:
        from mcp_server.tools.core.identity import get_server_time

        result = get_server_time()
        assert result["date"]
        assert result["weekday"] in {"周一", "周二", "周三", "周四", "周五", "周六", "周日"}
        assert result["timezone"]
        assert isinstance(result["timestamp"], int)


class TestProjection:
    """列表投影：把「列表端点返回详情结构」造成的上下文溢出压下去。"""

    def test_default_projection_drops_nested(self) -> None:
        from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project

        item = {
            "id": 1,
            "name": "合同A",
            "status": "active",
            "contract_parties": [{"id": 9, "name": "客户"}],
            "payments": [{"amount": 100}],
            "reminders": [{"id": 3}],
        }
        result = project(item, None, CONTRACT_LIST_FIELDS)

        assert result["id"] == 1
        assert "contract_parties" not in result
        assert "payments" not in result
        assert "reminders" not in result

    def test_explicit_fields(self) -> None:
        from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project

        item = {"id": 1, "name": "合同A", "status": "active", "payments": []}
        result = project(item, ["id", "name"], CONTRACT_LIST_FIELDS)

        assert result == {"id": 1, "name": "合同A"}

    def test_missing_fields_reported(self) -> None:
        """请求了不存在的字段要明说，不能让模型以为是空值。"""
        from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project

        result = project({"id": 1}, ["id", "不存在的字段"], CONTRACT_LIST_FIELDS)
        assert result["_missing_fields"] == ["不存在的字段"]

    def test_full_bypasses_projection(self) -> None:
        from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project

        item = {"id": 1, "contract_parties": [{"id": 9}]}
        assert project(item, None, CONTRACT_LIST_FIELDS, full=True) == item

    def test_project_page_keeps_metadata(self) -> None:
        from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project_page

        page = {"items": [{"id": 1, "name": "A", "payments": []}], "total": 165, "page": 1, "page_size": 20}
        result = project_page(page, None, CONTRACT_LIST_FIELDS)

        assert result["total"] == 165
        assert result["page"] == 1
        assert result["projected"] is True
        assert "payments" not in result["items"][0]

    def test_projection_shrinks_payload(self) -> None:
        """投影必须真的省体积——这是它存在的唯一理由。"""
        import json

        from mcp_server.tools.core.projection import CONTRACT_LIST_FIELDS, project

        heavy = {
            "id": 1,
            "name": "合同",
            "status": "active",
            "contract_parties": [{"id": index, "detail": "x" * 200} for index in range(20)],
            "payments": [{"id": index, "amount": 100} for index in range(20)],
            "finalized_materials": [{"id": index, "name": "y" * 200} for index in range(20)],
        }
        before = len(json.dumps(heavy, ensure_ascii=False))
        after = len(json.dumps(project(heavy, None, CONTRACT_LIST_FIELDS), ensure_ascii=False))
        assert after * 10 < before, f"投影后体积应至少降一个数量级（{after} vs {before}）"
