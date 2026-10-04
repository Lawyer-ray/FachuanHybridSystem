"""workflow 模板步骤白名单单测（安全审计 A-01/B-01/B-02 修复）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.workflow.services import get_workflow_template_service

_validate_steps_for_user = get_workflow_template_service().validate_steps_for_user


def _step(**kwargs: object) -> SimpleNamespace:
    base = {"type": "activity", "mcp_tool": ""}
    base.update(kwargs)
    return SimpleNamespace(**base)


def _user(is_superuser: bool = False) -> MagicMock:
    u = MagicMock()
    u.is_superuser = is_superuser
    return u


class TestValidateStepsForUser:
    def test_code_type_forbidden_for_everyone(self) -> None:
        with pytest.raises(ValidationException):
            _validate_steps_for_user(_user(is_superuser=True), [_step(type="code")])

    def test_http_type_requires_superuser(self) -> None:
        with pytest.raises(ValidationException):
            _validate_steps_for_user(_user(is_superuser=False), [_step(type="http")])

    def test_http_type_allowed_for_superuser(self) -> None:
        # 超管使用 http 类型静默通过（返回 None）
        assert _validate_steps_for_user(_user(is_superuser=True), [_step(type="http")]) is None

    def test_mcp_tool_field_bypass_blocked(self) -> None:
        """复审关键用例：type 合法但携带 mcp_tool 字段，非超管必须被拒。"""
        with pytest.raises(ValidationException):
            _validate_steps_for_user(_user(is_superuser=False), [_step(type="llm", mcp_tool="get_case")])

    def test_mcp_tool_field_allowed_for_superuser(self) -> None:
        # 超管携带 mcp_tool 字段静默通过
        assert _validate_steps_for_user(_user(is_superuser=True), [_step(type="llm", mcp_tool="get_case")]) is None

    def test_safe_types_pass(self) -> None:
        # 普通用户的安全类型组合静默通过
        assert (
            _validate_steps_for_user(
                _user(is_superuser=False),
                [_step(type="activity"), _step(type="gate"), _step(type="llm")],
            )
            is None
        )
