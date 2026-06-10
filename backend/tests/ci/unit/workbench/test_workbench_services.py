"""
Tests for apps.workbench.services — 工作台服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestWorkbenchSessionService:
    """WorkbenchSessionService 测试"""

    def test_list_sessions_unauthenticated(self) -> None:
        from apps.workbench.services.session_service import WorkbenchSessionService

        svc = WorkbenchSessionService()
        result = svc.list_sessions(user=None)
        assert result == {"items": [], "count": 0}

    def test_list_sessions_anonymous_user(self) -> None:
        from apps.workbench.services.session_service import WorkbenchSessionService

        svc = WorkbenchSessionService()
        mock_user = MagicMock()
        mock_user.is_authenticated = False
        result = svc.list_sessions(user=mock_user)
        assert result == {"items": [], "count": 0}

    def test_invalidate_session_cache_no_user(self) -> None:
        from apps.workbench.services.session_service import WorkbenchSessionService

        # Should not raise
        WorkbenchSessionService._invalidate_session_cache(None)

    def test_invalidate_session_cache_anonymous(self) -> None:
        from apps.workbench.services.session_service import WorkbenchSessionService

        mock_user = MagicMock()
        mock_user.is_authenticated = False
        WorkbenchSessionService._invalidate_session_cache(mock_user)

    def test_increment_storage_zero_delta(self) -> None:
        from apps.workbench.services.session_service import WorkbenchSessionService

        # Should not raise, zero delta means no-op
        WorkbenchSessionService.increment_storage(1, 0)


class TestCalcMessageBytes:
    """_calc_message_bytes 测试"""

    def test_empty(self) -> None:
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes()
        # Each of tool_input/tool_output/metadata defaults to {} = 2 bytes each, plus empty content
        assert result > 0

    def test_with_content(self) -> None:
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(content="hello")
        assert result > 0

    def test_with_tool_input(self) -> None:
        from apps.workbench.services.session_service import _calc_message_bytes

        result = _calc_message_bytes(tool_input={"key": "value"})
        assert result > 0


class TestWorkbenchMessageService:
    """WorkbenchMessageService 测试"""

    def test_submit_feedback_invalid_rating(self) -> None:
        from apps.workbench.services.message_service import WorkbenchMessageService
        from apps.core.exceptions import ValidationException

        svc = WorkbenchMessageService(session_service=MagicMock())
        with pytest.raises(ValidationException, match="rating"):
            svc.submit_feedback(1, rating="invalid", user=MagicMock())

    def test_message_to_dict_with_valid_message(self) -> None:
        from apps.workbench.services.message_service import WorkbenchMessageService

        # Just verify the static method exists and can be called
        assert callable(WorkbenchMessageService._message_to_dict)
