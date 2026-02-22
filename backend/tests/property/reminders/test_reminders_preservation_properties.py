"""
Preservation Property Tests: Reminders Quality Uplift

Property 2: Preservation - 外部行为不变性验证

在未修复代码上观察正常路径行为，编写 PBT 测试确保修复后行为一致。
这些测试在未修复代码上 **预期通过**，通过即确认基线行为。

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.core.exceptions import ValidationException
from apps.reminders.models import ReminderType
from apps.reminders.schemas import ReminderIn, ReminderUpdate
from apps.reminders.services.reminder_service import ReminderService
from apps.reminders.services.validators import validate_binding_exclusive

logger: logging.Logger = logging.getLogger(__name__)

# ── Hypothesis 策略 ──────────────────────────────────────────────────

VALID_REMINDER_TYPES: list[str] = list(ReminderType.values)

st_reminder_type = st.sampled_from(VALID_REMINDER_TYPES)
st_positive_int = st.integers(min_value=1, max_value=999_999)
st_content = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() != "")
st_due_at = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)
st_metadata = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        values=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
        max_size=3,
    ),
)


# ══════════════════════════════════════════════════════════════════════
# Property Test 1: CRUD 响应结构不变
# Validates: Requirements 3.1, 3.7
# ══════════════════════════════════════════════════════════════════════


def _ensure_contract() -> int:
    """确保数据库中存在一个 Contract 记录，返回其 pk。"""
    from apps.contracts.models import Contract

    obj = Contract.objects.first()
    if obj is not None:
        return int(obj.pk)
    obj = Contract.objects.create(name="test-contract", case_type="civil")
    return int(obj.pk)


def _ensure_case_log() -> int:
    """确保数据库中存在一个 CaseLog 记录，返回其 pk。"""
    from apps.cases.models import Case, CaseLog
    from apps.organization.models import Lawyer

    obj = CaseLog.objects.first()
    if obj is not None:
        return int(obj.pk)

    lawyer = Lawyer.objects.first()
    if lawyer is None:
        lawyer = Lawyer.objects.create_user(username="test-lawyer", password="test1234")

    case = Case.objects.first()
    if case is None:
        case = Case.objects.create(name="test-case")

    log = CaseLog.objects.create(case=case, content="test-log", actor=lawyer)
    return int(log.pk)


@pytest.mark.django_db(transaction=True)
@pytest.mark.property_test
@settings(
    max_examples=15,
    deadline=timedelta(seconds=10),
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    reminder_type=st_reminder_type,
    content=st_content,
    due_at=st_due_at,
    metadata=st_metadata,
    bind_to_contract=st.booleans(),
)
def test_crud_response_structure_preserved(
    reminder_type: str,
    content: str,
    due_at: datetime,
    metadata: dict[str, Any] | None,
    bind_to_contract: bool,
) -> None:
    """
    **Validates: Requirements 3.1, 3.7**

    生成随机提醒数据，验证 CRUD 响应结构不变。
    使用 Service 层直接调用，验证：
    - create_reminder 返回 Reminder 实例，包含所有必要字段
    - get_reminder 返回相同实例
    - list_reminders 包含创建的记录
    - update_reminder 返回更新后的实例
    - delete_reminder 返回 {"success": True}
    """
    contract_id: int | None = None
    case_log_id: int | None = None

    if bind_to_contract:
        contract_id = _ensure_contract()
    else:
        case_log_id = _ensure_case_log()

    service = ReminderService()

    # ── CREATE ──
    reminder = service.create_reminder(
        contract_id=contract_id,
        case_log_id=case_log_id,
        reminder_type=reminder_type,
        content=content,
        due_at=due_at,
        metadata=metadata,
    )
    assert reminder.pk is not None, "创建后应有 pk"
    assert reminder.reminder_type == reminder_type
    assert reminder.content == content.strip()
    assert reminder.due_at is not None
    assert reminder.created_at is not None

    # ── GET ──
    fetched = service.get_reminder(reminder.pk)
    assert fetched.pk == reminder.pk
    assert fetched.reminder_type == reminder.reminder_type
    assert fetched.content == reminder.content

    # ── LIST ──
    if contract_id is not None:
        qs = service.list_reminders(contract_id=contract_id)
    else:
        qs = service.list_reminders(case_log_id=case_log_id)
    found_ids: list[int] = list(qs.values_list("id", flat=True))
    assert reminder.pk in found_ids, "列表应包含刚创建的记录"

    # ── UPDATE ──
    updated = service.update_reminder(reminder.pk, {"content": "updated-content"})
    assert updated.pk == reminder.pk
    assert updated.content == "updated-content"

    # ── DELETE ──
    result = service.delete_reminder(reminder.pk) # type: ignore[func-returns-value]
    assert isinstance(result, dict)
    assert result.get("success") is True


# ══════════════════════════════════════════════════════════════════════
# Property Test 2: 存在性校验行为
# Validates: Requirements 3.4, 3.5
# ══════════════════════════════════════════════════════════════════════


# 策略: 生成不存在的 contract_id / case_log_id 组合
st_nonexistent_id = st.integers(min_value=900_000, max_value=999_999)


@pytest.mark.django_db
@pytest.mark.property_test
@settings(
    max_examples=20,
    deadline=timedelta(seconds=10),
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(
    contract_id=st_nonexistent_id,
    case_log_id=st_nonexistent_id,
    choice=st.sampled_from(["contract_only", "case_log_only", "both"]),
    reminder_type=st_reminder_type,
    content=st_content,
    due_at=st_due_at,
)
def test_existence_validation_behavior_preserved(
    contract_id: int,
    case_log_id: int,
    choice: str,
    reminder_type: str,
    content: str,
    due_at: datetime,
) -> None:
    """
    **Validates: Requirements 3.4, 3.5**

    生成随机 contract_id/case_log_id 组合，验证存在性校验行为：
    - 不存在的 contract_id → ValidationException
    - 不存在的 case_log_id → ValidationException
    - 同时传入 contract_id 和 case_log_id → 绑定互斥校验错误 (ValidationException)
    """
    service = ReminderService()

    if choice == "both":
        # 同时传入 → 绑定互斥校验错误 (Req 3.5)
        with pytest.raises(ValidationException):
            service.create_reminder(
                contract_id=contract_id,
                case_log_id=case_log_id,
                reminder_type=reminder_type,
                content=content,
                due_at=due_at,
            )
    elif choice == "contract_only":
        # 不存在的 contract → ValidationException (Req 3.4)
        with pytest.raises(ValidationException):
            service.create_reminder(
                contract_id=contract_id,
                case_log_id=None,
                reminder_type=reminder_type,
                content=content,
                due_at=due_at,
            )
    else:
        # 不存在的 case_log → ValidationException (Req 3.4)
        with pytest.raises(ValidationException):
            service.create_reminder(
                contract_id=None,
                case_log_id=case_log_id,
                reminder_type=reminder_type,
                content=content,
                due_at=due_at,
            )


# ══════════════════════════════════════════════════════════════════════
# Property Test 3: Service 层绑定互斥校验
# Validates: Requirements 3.5
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
@settings(
    max_examples=30,
    deadline=timedelta(seconds=5),
)
@given(
    contract_id=st.one_of(st.none(), st_positive_int),
    case_log_id=st.one_of(st.none(), st_positive_int),
)
def test_service_binding_exclusivity_validation_preserved(
    contract_id: int | None,
    case_log_id: int | None,
) -> None:
    """
    **Validates: Requirements 3.5**

    生成随机 contract_id/case_log_id 组合，验证 Service 层
    validate_binding_exclusive 的绑定互斥校验行为：
    - 两者都为 None → ValidationException
    - 两者都非 None → ValidationException
    - 恰好一个非 None → 通过（不抛异常）
    """
    both_none: bool = contract_id is None and case_log_id is None
    both_set: bool = contract_id is not None and case_log_id is not None

    if both_none or both_set:
        with pytest.raises(ValidationException):
            validate_binding_exclusive(
                contract_id=contract_id,
                case_log_id=case_log_id,
            )
    else:
        # 恰好一个非 None → 不应抛异常
        validate_binding_exclusive(
            contract_id=contract_id,
            case_log_id=case_log_id,
        )


# ══════════════════════════════════════════════════════════════════════
# Property Test 4: ReminderIn Schema 校验行为
# Validates: Requirements 3.7
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
@settings(
    max_examples=30,
    deadline=timedelta(seconds=5),
)
@given(
    contract_id=st.one_of(st.none(), st.integers(min_value=-100, max_value=100)),
    case_log_id=st.one_of(st.none(), st.integers(min_value=-100, max_value=100)),
    content=st.text(max_size=50),
    reminder_type=st.one_of(st_reminder_type, st.just("invalid_type")),
)
def test_schema_validation_behavior_preserved(
    contract_id: int | None,
    case_log_id: int | None,
    content: str,
    reminder_type: str,
) -> None:
    """
    **Validates: Requirements 3.7**

    生成随机 ReminderIn 输入，验证 Schema 校验行为：
    - 负数 ID → 校验错误
    - 空 content → 校验错误
    - 同时绑定两个目标 → 校验错误
    - 两者都为 None → 校验错误
    - 有效输入 → 通过
    """
    from pydantic import ValidationError

    has_negative_id: bool = (
        (contract_id is not None and contract_id <= 0)
        or (case_log_id is not None and case_log_id <= 0)
    )
    empty_content: bool = content.strip() == ""
    both_none: bool = contract_id is None and case_log_id is None
    both_set: bool = contract_id is not None and case_log_id is not None
    invalid_type: bool = reminder_type not in VALID_REMINDER_TYPES

    should_fail: bool = has_negative_id or empty_content or both_none or both_set or invalid_type

    if should_fail:
        with pytest.raises(ValidationError):
            ReminderIn(
                contract_id=contract_id,
                case_log_id=case_log_id,
                reminder_type=reminder_type,  # type: ignore[arg-type]
                content=content,
                due_at=datetime.now(tz=timezone.utc),
            )
    else:
        schema = ReminderIn(
            contract_id=contract_id,
            case_log_id=case_log_id,
            reminder_type=reminder_type,  # type: ignore[arg-type]
            content=content,
            due_at=datetime.now(tz=timezone.utc),
        )
        assert schema.content == content.strip()
        assert schema.contract_id == contract_id
        assert schema.case_log_id == case_log_id
