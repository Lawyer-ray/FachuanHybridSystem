"""Tests for core.api (system config API endpoints).

Covers: list_system_configs, update_system_configs, create_system_config,
patch_system_config, delete_system_config, schema definitions.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestSchemas:
    def test_system_config_item_out(self):
        from apps.core.api import SystemConfigItemOut
        item = SystemConfigItemOut(
            key="k",
            value="v",
            category="cat",
            description="desc",
            is_secret=False,
            is_active=True,
        )
        assert item.key == "k"
        assert item.has_value is True

    def test_system_config_group_out(self):
        from apps.core.api import SystemConfigGroupOut, SystemConfigItemOut
        item = SystemConfigItemOut(
            key="k", value="v", category="c", description="d", is_secret=False, is_active=True
        )
        group = SystemConfigGroupOut(category="c", items=[item])
        assert len(group.items) == 1

    def test_system_config_list_out(self):
        from apps.core.api import SystemConfigGroupOut, SystemConfigListOut
        group = SystemConfigGroupOut(category="c", items=[])
        out = SystemConfigListOut(groups=[group])
        assert len(out.groups) == 1

    def test_system_config_update_in(self):
        from apps.core.api import SystemConfigUpdateIn
        inp = SystemConfigUpdateIn(category="cat", updates={"a": "1", "b": "2"})
        assert len(inp.updates) == 2

    def test_system_config_create_in_defaults(self):
        from apps.core.api import SystemConfigCreateIn
        inp = SystemConfigCreateIn(key="k")
        assert inp.value == ""
        assert inp.category == "general"
        assert inp.is_secret is False

    def test_system_config_patch_in_all_optional(self):
        from apps.core.api import SystemConfigPatchIn
        inp = SystemConfigPatchIn()
        assert inp.value is None
        assert inp.is_active is None

    def test_system_config_delete_out(self):
        from apps.core.api import SystemConfigDeleteOut
        out = SystemConfigDeleteOut(success=True)
        assert out.success is True

    def test_system_config_update_out(self):
        from apps.core.api import SystemConfigUpdateOut
        out = SystemConfigUpdateOut(success=True, updated_count=3)
        assert out.updated_count == 3


class TestListSystemConfigs:
    @patch("apps.core.api._repository")
    def test_basic(self, mock_repo):
        from apps.core.api import list_system_configs
        cfg = SimpleNamespace(
            key="k", value="v", category="c", description="d",
            is_secret=False, is_active=True,
        )
        mock_repo.get_all_active.return_value = [cfg]
        request = MagicMock()
        result = list_system_configs(request)
        assert len(result["groups"]) == 1
        assert result["groups"][0].items[0].key == "k"

    @patch("apps.core.api._repository")
    def test_secret_masked(self, mock_repo):
        from apps.core.api import list_system_configs
        cfg = SimpleNamespace(
            key="secret_key", value="real_value", category="c", description="d",
            is_secret=True, is_active=True,
        )
        mock_repo.get_all_active.return_value = [cfg]
        request = MagicMock()
        result = list_system_configs(request)
        assert result["groups"][0].items[0].value == "******"

    @patch("apps.core.api._repository")
    def test_empty_value(self, mock_repo):
        from apps.core.api import list_system_configs
        cfg = SimpleNamespace(
            key="k", value="", category="c", description="d",
            is_secret=False, is_active=True,
        )
        mock_repo.get_all_active.return_value = [cfg]
        request = MagicMock()
        result = list_system_configs(request)
        assert result["groups"][0].items[0].has_value is False


class TestUpdateSystemConfigs:
    @patch("apps.core.api._repository")
    def test_update_existing_key(self, mock_repo):
        from apps.core.api import update_system_configs, SystemConfigUpdateIn
        existing = SimpleNamespace(category="c", description="d", is_secret=False)
        mock_repo.get_by_key.return_value = existing
        payload = SystemConfigUpdateIn(category="c", updates={"k": "new_val"})
        request = MagicMock()
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            instance = MockSvc.return_value
            result = update_system_configs(request, payload)
            instance.set_value.assert_called_once()
            assert result["success"] is True
            assert result["updated_count"] == 1

    @patch("apps.core.api._repository")
    def test_create_new_key(self, mock_repo):
        from apps.core.api import update_system_configs, SystemConfigUpdateIn
        mock_repo.get_by_key.return_value = None
        payload = SystemConfigUpdateIn(category="c", updates={"k": "val"})
        request = MagicMock()
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            instance = MockSvc.return_value
            result = update_system_configs(request, payload)
            instance.set_value.assert_called_once()
            assert result["updated_count"] == 1


class TestCreateSystemConfig:
    @patch("apps.core.api._repository")
    def test_create_success(self, mock_repo):
        from apps.core.api import create_system_config, SystemConfigCreateIn
        mock_repo.get_by_key.return_value = None
        payload = SystemConfigCreateIn(key="new_key", value="val", category="c")
        request = MagicMock()
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            config = SimpleNamespace(
                key="new_key", value="val", category="c", description="",
                is_secret=False, is_active=True,
            )
            MockSvc.return_value.set_value.return_value = config
            result = create_system_config(request, payload)
            assert result.key == "new_key"

    @patch("apps.core.api._repository")
    def test_create_conflict(self, mock_repo):
        from apps.core.api import create_system_config, SystemConfigCreateIn
        existing = SimpleNamespace(id=1)
        mock_repo.get_by_key.return_value = existing
        payload = SystemConfigCreateIn(key="existing_key")
        request = MagicMock()
        with pytest.raises(Exception):
            create_system_config(request, payload)


class TestPatchSystemConfig:
    @patch("apps.core.api._repository")
    def test_patch_success(self, mock_repo):
        from apps.core.api import patch_system_config, SystemConfigPatchIn
        config = SimpleNamespace(id=1, key="k", value="old", category="c", description="d", is_secret=False, is_active=True)
        mock_repo.get_by_key.return_value = config
        payload = SystemConfigPatchIn(value="new_val")
        request = MagicMock()
        with patch("apps.core.services.system_config_service.SystemConfigService") as MockSvc:
            updated = SimpleNamespace(
                key="k", value="new_val", category="c", description="d",
                is_secret=False, is_active=True,
            )
            MockSvc.return_value.update_config.return_value = updated
            result = patch_system_config(request, "k", payload)
            assert result.value == "new_val"

    @patch("apps.core.api._repository")
    def test_patch_not_found(self, mock_repo):
        from apps.core.api import patch_system_config, SystemConfigPatchIn
        mock_repo.get_by_key.return_value = None
        payload = SystemConfigPatchIn()
        request = MagicMock()
        with pytest.raises(Exception):
            patch_system_config(request, "missing", payload)


class TestDeleteSystemConfig:
    @patch("apps.core.api._repository")
    def test_delete_success(self, mock_repo):
        from apps.core.api import delete_system_config
        config = SimpleNamespace(id=1)
        mock_repo.get_by_key.return_value = config
        request = MagicMock()
        result = delete_system_config(request, "k")
        assert result["success"] is True
        mock_repo.delete.assert_called_once_with(1)

    @patch("apps.core.api._repository")
    def test_delete_not_found(self, mock_repo):
        from apps.core.api import delete_system_config
        mock_repo.get_by_key.return_value = None
        request = MagicMock()
        with pytest.raises(Exception):
            delete_system_config(request, "missing")
