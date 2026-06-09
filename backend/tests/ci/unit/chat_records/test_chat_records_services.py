"""
Tests for apps.chat_records.services — 聊天记录服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import PermissionDenied


class TestAccessPolicy:
    """访问策略测试"""

    def test_admin_can_access(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        admin = MagicMock()
        admin.is_staff = True
        # Should not raise
        ensure_can_access_project(user=admin, project=MagicMock())

    def test_no_user_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=None, project=MagicMock())

    def test_anonymous_user_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        user = MagicMock()
        user.is_authenticated = False
        user.is_admin = False
        user.is_superuser = False
        user.is_staff = False
        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=user, project=MagicMock())

    def test_owner_can_access(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_admin = False
        user.is_superuser = False
        user.id = 42
        project = MagicMock()
        project.created_by_id = 42
        # Should not raise
        ensure_can_access_project(user=user, project=project)

    def test_non_owner_raises(self) -> None:
        from apps.chat_records.services.core.access_policy import ensure_can_access_project

        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_admin = False
        user.is_superuser = False
        user.id = 42
        project = MagicMock()
        project.created_by_id = 99
        with pytest.raises(PermissionDenied):
            ensure_can_access_project(user=user, project=project)


class TestChatRecordsModules:
    """聊天记录模块可导入性测试"""

    def test_protocols_importable(self) -> None:
        from apps.chat_records.services.core import protocols

        assert protocols is not None

    def test_export_task_service_importable(self) -> None:
        from apps.chat_records.services.export import export_task_service

        assert export_task_service is not None
