"""Reminders 模块代码质量优化 V2 - 属性测试 + 单元测试。"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from apps.core.exceptions import ValidationException
from apps.reminders.models import Reminder, ReminderType
from apps.reminders.schemas import ReminderIn

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
VALID_REMINDER_TYPES: list[str] = list(ReminderType.values)
REMINDERS_APP_DIR: Path = Path(__file__).resolve().parents[3] / "apps" / "reminders"


# ===========================================================================
# Task 7.1 - Property 1: update_reminder 的 reminder_type 枚举校验
# ===========================================================================

class TestUpdateReminderTypeValidation:
    """
    Feature: reminders-quality-uplift-v2, Property 1: update_reminder 的 reminder_type 枚举校验

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @pytest.mark.django_db
    @given(reminder_type=st.text(min_size=1))
    @settings(max_examples=100, deadline=None)
    def test_update_reminder_type_enum_validation(self, reminder_type: str) -> None:
        """合法值更新成功，非法值抛出 ValidationException。"""
        from apps.reminders.services.reminder_service import ReminderService

        service = ReminderService()

        # 构造 mock reminder 对象
        mock_reminder = MagicMock(spec=Reminder)
        mock_reminder.contract_id = 1
        mock_reminder.case_log_id = None
        mock_reminder.reminder_type = "hearing"
        mock_reminder.content = "test"
        mock_reminder.due_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_reminder.metadata = {}
        mock_reminder.full_clean = MagicMock()
        mock_reminder.save = MagicMock()

        data: dict[str, Any] = {"reminder_type": reminder_type}

        with patch.object(service, "get_reminder", return_value=mock_reminder):
            if reminder_type in ReminderType.values:
                result = service.update_reminder(1, data)
                assert result.reminder_type == reminder_type
            else:
                with pytest.raises(ValidationException):
                    service.update_reminder(1, data)

    @pytest.mark.django_db
    def test_update_reminder_skip_validation_when_no_type_key(self) -> None:
        """data 不包含 reminder_type 键时跳过校验。"""
        from apps.reminders.services.reminder_service import ReminderService

        service = ReminderService()

        mock_reminder = MagicMock(spec=Reminder)
        mock_reminder.contract_id = 1
        mock_reminder.case_log_id = None
        mock_reminder.reminder_type = "hearing"
        mock_reminder.content = "test"
        mock_reminder.due_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_reminder.metadata = {}
        mock_reminder.full_clean = MagicMock()
        mock_reminder.save = MagicMock()

        data: dict[str, Any] = {"content": "updated content"}

        with patch.object(service, "get_reminder", return_value=mock_reminder):
            result = service.update_reminder(1, data)
            assert result.reminder_type == "hearing"


# ===========================================================================
# Task 7.2 - Property 2: ReminderIn 的互斥校验
# ===========================================================================

class TestReminderInBindingExclusivity:
    """
    Feature: reminders-quality-uplift-v2, Property 2: ReminderIn 的互斥校验

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    @given(
        contract_id=st.one_of(st.none(), st.integers(min_value=1)),
        case_log_id=st.one_of(st.none(), st.integers(min_value=1)),
    )
    @settings(max_examples=100, deadline=None)
    def test_reminder_in_binding_exclusivity(
        self, contract_id: int | None, case_log_id: int | None
    ) -> None:
        """恰好一个有值时通过，否则抛出校验错误。"""
        exactly_one = (contract_id is None) != (case_log_id is None)

        if exactly_one:
            schema = ReminderIn(
                contract_id=contract_id,
                case_log_id=case_log_id,
                reminder_type="hearing",
                content="test",
                due_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
            assert schema.contract_id == contract_id
            assert schema.case_log_id == case_log_id
        else:
            with pytest.raises(ValidationError):
                ReminderIn(
                    contract_id=contract_id,
                    case_log_id=case_log_id,
                    reminder_type="hearing",
                    content="test",
                    due_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )


# ===========================================================================
# Task 7.3 - Property 3: __str__ 绑定关系格式化
# ===========================================================================

class TestReminderStrBindingFormat:
    """
    Feature: reminders-quality-uplift-v2, Property 3: __str__ 绑定关系格式化

    **Validates: Requirements 8.1, 8.2, 8.3**
    """

    @given(
        contract_id=st.one_of(st.none(), st.integers(min_value=1)),
        case_log_id=st.one_of(st.none(), st.integers(min_value=1)),
    )
    @settings(max_examples=100, deadline=None)
    def test_reminder_str_binding_format(
        self, contract_id: int | None, case_log_id: int | None
    ) -> None:
        """验证输出字符串包含正确的绑定标识。"""
        reminder = MagicMock(spec=Reminder)
        reminder.contract_id = contract_id
        reminder.case_log_id = case_log_id
        reminder.reminder_type = "hearing"
        reminder.due_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        # 直接调用 Reminder.__str__ 绕过 MagicMock 的 __str__
        result: str = Reminder.__str__(reminder)

        if contract_id:
            assert f"contract:{contract_id}" in result
        elif case_log_id:
            assert f"case_log:{case_log_id}" in result
        else:
            assert "unbound" in result


# ===========================================================================
# Task 7.4 - 单元测试：导入规范和 i18n 合规验证
# ===========================================================================

class TestImportAndI18nCompliance:
    """
    导入规范和 i18n 合规验证。

    _Requirements: 1.1, 1.2, 2.1, 3.1, 4.1, 5.1, 5.2_
    """

    @staticmethod
    def _read_source(relative_path: str) -> str:
        """读取 reminders 模块下的源文件内容。"""
        return (REMINDERS_APP_DIR / relative_path).read_text(encoding="utf-8")

    # --- 需求 1.1, 1.2: API 层工厂函数和 TYPE_CHECKING 使用相对导入 ---

    def test_api_get_service_uses_relative_import(self) -> None:
        """_get_service() 内使用 from ..services 相对导入。"""
        source = self._read_source("api/reminder_api.py")
        assert "from ..services import ReminderService" in source
        assert "from apps.reminders.services import ReminderService" not in source

    def test_api_type_checking_uses_relative_import(self) -> None:
        """TYPE_CHECKING 块使用 from ..services 相对导入。"""
        source = self._read_source("api/reminder_api.py")
        # 解析 AST 找到 TYPE_CHECKING 块内的导入
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                is_type_checking = (
                    (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                    or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
                )
                if is_type_checking:
                    for child in ast.walk(node):
                        if isinstance(child, ast.ImportFrom) and child.module:
                            assert not child.module.startswith("apps.reminders"), (
                                f"TYPE_CHECKING 块内应使用相对导入，发现: from {child.module}"
                            )

    # --- 需求 2.1: API 层 Schema 导入使用相对导入 ---

    def test_api_schema_uses_relative_import(self) -> None:
        """Schema 导入使用 from ..schemas 相对导入。"""
        source = self._read_source("api/reminder_api.py")
        assert "from ..schemas import" in source
        assert "from apps.reminders.schemas import" not in source

    # --- 需求 3.1: Service 层 Model 导入使用相对导入 ---

    def test_service_model_uses_relative_import(self) -> None:
        """Service 层使用 from ..models 相对导入。"""
        source = self._read_source("services/reminder_service.py")
        assert "from ..models import" in source
        assert "from apps.reminders.models import" not in source

    # --- 需求 4.1: Admin 层 Model 导入使用相对导入 ---

    def test_admin_model_uses_relative_import(self) -> None:
        """Admin 层使用 from ..models 相对导入。"""
        source = self._read_source("admin/reminder_admin.py")
        assert "from ..models import" in source
        assert "from apps.reminders.models import" not in source

    # --- 需求 5.1, 5.2: help_texts 使用 gettext_lazy ---

    def test_help_texts_uses_gettext_lazy(self) -> None:
        """help_texts 中的字符串使用 _() 包裹。"""
        source = self._read_source("admin/reminder_admin.py")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != "Meta":
                continue
            # 找到 Meta 类中的 help_texts 赋值
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "help_texts":
                        # help_texts 的值应该是 dict，其中 value 应该是 Call（即 _() 调用）
                        assert item.value is not None
                        assert isinstance(item.value, ast.Dict)
                        for val in item.value.values:
                            assert isinstance(val, ast.Call), (
                                "help_texts 的值应使用 _() 包裹，"
                                f"发现: {ast.dump(val)}"
                            )
