"""Regression tests for case-binding reminder bridge behavior.

多日期人工确认改造后，绑定期不再写任何提醒（`_update_log_reminder` 已删除）：
提醒只经 date_candidate_service.confirm_candidates 人工确认后写入。
本文件断言绑定期对 update_case_log_reminder_internal 零调用，
以及 format_log_content 的 date_count 文案。
"""

from __future__ import annotations

import inspect
from typing import Any

from apps.document_recognition.services.case_binding_service import CaseBindingService
from apps.document_recognition.services.data_classes import DocumentType


class _CaseServiceSpy:
    """记录 create_case_log / 提醒更新调用的替身。"""

    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.reminder_calls: list[dict[str, Any]] = []
        self.case_dto: Any = None

    def create_case_log_internal(self, *, case_id: int, content: str, user_id: int | None) -> int:
        self.create_calls.append({"case_id": case_id, "content": content, "user_id": user_id})
        return 42

    def add_case_log_attachment_internal(self, *, case_log_id: int, file_path: str, file_name: str) -> bool:
        return True

    def update_case_log_reminder_internal(
        self, *, case_log_id: int, reminder_time: Any, reminder_type: str
    ) -> bool:
        self.reminder_calls.append(
            {
                "case_log_id": case_log_id,
                "reminder_time": reminder_time,
                "reminder_type": reminder_type,
            }
        )
        return True

    def get_case_by_id_internal(self, case_id: int) -> Any:
        return self.case_dto


def test_create_case_log_never_writes_reminder() -> None:
    """create_case_log 只建日志+附件，不再写提醒（update...internal 零调用）。"""
    spy = _CaseServiceSpy()
    service = CaseBindingService(case_service=spy)  # type: ignore[arg-type]

    # 绕过 @transaction.atomic（单测无 DB）
    result = service.create_case_log.__wrapped__(  # type: ignore[attr-defined]
        service, case_id=1, content="【传票】\n识别到 3 个关键日期", file_path="/tmp/doc.pdf"
    )

    assert result == 42
    assert len(spy.create_calls) == 1
    assert spy.reminder_calls == []


def test_bind_document_to_case_writes_no_reminder() -> None:
    """绑定流程（bind_document_to_case）同样不写任何提醒。"""
    spy = _CaseServiceSpy()
    spy.case_dto = type("DTO", (), {"name": "张三诉李四"})()
    service = CaseBindingService(case_service=spy)  # type: ignore[arg-type]
    service.create_case_log = lambda **kwargs: 42  # type: ignore[method-assign]

    result = service.bind_document_to_case(
        case_id=1,
        document_type=DocumentType.SUMMONS,
        content="【传票】\n识别到 2 个关键日期（待人工确认后写入重要日期提醒）",
        file_path="/tmp/doc.pdf",
    )

    assert result.success is True
    assert spy.reminder_calls == []


def test_create_case_log_signature_has_no_reminder_params() -> None:
    """reminder_time / document_type 参数已从 create_case_log 签名移除。"""
    params = inspect.signature(CaseBindingService.create_case_log).parameters
    assert "reminder_time" not in params
    assert "document_type" not in params
    assert not hasattr(CaseBindingService, "_update_log_reminder")


def test_format_log_content_with_date_count() -> None:
    """date_count>0 时输出人工确认文案，而非直接写开庭时间。"""
    service = CaseBindingService(case_service=_CaseServiceSpy())  # type: ignore[arg-type]

    content = service.format_log_content(
        document_type=DocumentType.SUMMONS,
        case_number="（2024）京01民初123号",
        raw_text="",
        date_count=3,
    )

    assert "识别到 3 个关键日期（待人工确认后写入重要日期提醒）" in content
    assert "开庭时间" not in content


def test_format_log_content_without_date_count() -> None:
    """date_count=0 时不输出关键日期行。"""
    service = CaseBindingService(case_service=_CaseServiceSpy())  # type: ignore[arg-type]

    content = service.format_log_content(
        document_type=DocumentType.SUMMONS,
        case_number=None,
        raw_text="正文",
        date_count=0,
    )

    assert "关键日期" not in content
    assert "开庭时间" not in content
    assert "正文" in content
