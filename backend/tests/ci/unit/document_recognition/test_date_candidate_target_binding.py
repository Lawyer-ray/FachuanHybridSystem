"""BUG-1 回归：文书识别确认日期时的提醒关联锚点回落。

真实时序（任务 #25）：识别完成 → 用户确认日期写提醒 → 案件日志才落库。
旧实现只认 ``task.case_log_id``，那一刻为 NULL，于是产出 contract/case/case_log
三字段全空的孤立提醒，日历上显示「未关联案件」且用户无补救入口。

这里不 mock 被测逻辑：``_confirm_single_item`` 与 ``_reminder_binding_kwargs``
用真实代码，只有提醒服务换成会真正校验绑定三元组的替身（记录磁盘上的提醒并
按 Reminder 模型的 CHECK 约束自检）。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from apps.document_recognition.services import date_candidate_service as dcs


class RecordingReminderService:
    """内存版提醒服务：落盘到列表，并像 DB 的 CheckConstraint 一样只允许绑一个目标。"""

    def __init__(self) -> None:
        self.reminders: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []

    def list_reminders(self, **kwargs: Any) -> list[Any]:
        self.list_calls.append(kwargs)
        return [
            SimpleNamespace(**reminder)
            for reminder in self.reminders
            if all(reminder[key] == value for key, value in kwargs.items())
        ]

    def create_reminder(self, **kwargs: Any) -> Any:
        bound = [name for name in ("contract_id", "case_id", "case_log_id") if kwargs.get(name) is not None]
        assert len(bound) <= 1, f"违反 Reminder 绑定互斥约束: {bound}"
        reminder = {
            "id": len(self.reminders) + 1,
            "contract_id": kwargs.get("contract_id"),
            "case_id": kwargs.get("case_id"),
            "case_log_id": kwargs.get("case_log_id"),
            "reminder_type": kwargs["reminder_type"],
            "content": kwargs["content"],
            "due_at": kwargs["due_at"],
            "metadata": kwargs["metadata"],
            "created_by": kwargs["created_by"],
            "include_in_important_time": False,
        }
        self.reminders.append(reminder)
        created = SimpleNamespace(**reminder)

        def _save(update_fields: list[str] | None = None) -> None:
            reminder["include_in_important_time"] = created.include_in_important_time

        created.save = _save
        return created


def _task(case_log_id: int | None, case_id: int | None) -> Any:
    return SimpleNamespace(id=25, case_log_id=case_log_id, case_id=case_id)


def _pending_row() -> Any:
    row = SimpleNamespace(
        id=11,
        status="pending",
        reminder_id=None,
        reminder_type="hearing",
        context_text="定于2026年11月5日上午9时30分在第三法庭开庭",
        due_at=datetime(2026, 11, 5, 9, 30),
    )
    row.save = lambda update_fields=None: None
    return row


def _confirm(task: Any, service: Any, user: Any | None = None) -> tuple[dict[str, Any], Any]:
    row = _pending_row()
    result = dcs._confirm_single_item(
        task=task,
        item={"candidate_id": row.id, "action": "confirm"},
        row=row,
        reminder_service=service,
        user_id=9,
        user=user,
        now=datetime(2026, 10, 20, 12, 0),
    )
    return result, row


class TestConfirmReminderTargetBinding:
    def test_case_log_bound_task_keeps_case_log_id(self):
        """优先级 1：case_log 已落库 → 仍挂 case_log，且不再绑 case。"""
        service = RecordingReminderService()

        result, row = _confirm(_task(case_log_id=427, case_id=88), service)

        assert result["status"] == "confirmed"
        assert len(service.reminders) == 1
        reminder = service.reminders[0]
        assert reminder["case_log_id"] == 427
        assert reminder["case_id"] is None
        assert reminder["contract_id"] is None
        assert row.reminder_id == reminder["id"]

    def test_case_bound_but_case_log_missing_falls_back_to_case_id(self):
        """优先级 2（BUG-1 现场）：日志还没落库 → 挂案件，不再是三字段全空的孤立提醒。"""
        service = RecordingReminderService()

        result, row = _confirm(_task(case_log_id=None, case_id=88), service)

        assert result["status"] == "confirmed"
        assert len(service.reminders) == 1
        reminder = service.reminders[0]
        assert reminder["case_id"] == 88
        assert reminder["case_log_id"] is None
        assert reminder["contract_id"] is None
        assert row.reminder_id == reminder["id"]

    def test_unbound_task_still_creates_standalone_reminder(self):
        """优先级 3：案件与日志都无 → 独立提醒，行为不变（快捕获场景不强制选案）。"""
        service = RecordingReminderService()

        result, _row = _confirm(_task(case_log_id=None, case_id=None), service)

        assert result["status"] == "confirmed"
        assert len(service.reminders) == 1
        reminder = service.reminders[0]
        assert reminder["case_log_id"] is None
        assert reminder["case_id"] is None
        assert reminder["contract_id"] is None
        assert reminder["metadata"]["source"] == dcs.REMINDER_SOURCE
        assert reminder["metadata"]["task_id"] == 25

    def test_case_id_fallback_does_not_widen_dedup_domain(self):
        """查重域仍只在 case_log 存在时生效：case_id 回落不额外调 list_reminders。"""
        service = RecordingReminderService()

        _confirm(_task(case_log_id=None, case_id=88), service)

        assert service.list_calls == []
        assert len(service.reminders) == 1

    @pytest.mark.parametrize(
        ("case_log_id", "case_id"),
        [(427, None), (427, 88), (None, 88), (None, None)],
    )
    def test_binding_stays_within_check_constraint(self, case_log_id: int | None, case_id: int | None):
        """四种组合下都只有至多一个关联字段被写入，不触碰 CheckConstraint。"""
        service = RecordingReminderService()

        _confirm(_task(case_log_id=case_log_id, case_id=case_id), service)

        reminder = service.reminders[0]
        bound = [
            value
            for value in (reminder["contract_id"], reminder["case_id"], reminder["case_log_id"])
            if value is not None
        ]
        assert len(bound) <= 1
        assert bound == ([case_log_id] if case_log_id is not None else ([case_id] if case_id is not None else []))


class TestReminderBindingKwargs:
    def test_case_log_wins_over_case(self):
        assert dcs._reminder_binding_kwargs(_task(case_log_id=427, case_id=88)) == {"case_log_id": 427}

    def test_case_id_used_when_case_log_absent(self):
        assert dcs._reminder_binding_kwargs(_task(case_log_id=None, case_id=88)) == {"case_id": 88}

    def test_standalone_when_both_absent(self):
        assert dcs._reminder_binding_kwargs(_task(case_log_id=None, case_id=None)) == {"case_log_id": None}
