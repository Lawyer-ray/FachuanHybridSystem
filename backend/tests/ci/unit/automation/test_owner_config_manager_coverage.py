"""Tests for owner_config_manager — coverage for uncovered branches."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.chat.owner_config_manager import OwnerConfigManager


class TestOwnerConfigManagerInit:
    def test_init_loads_config(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr is not None


class TestValidateOwnerId:
    def test_valid_open_id(self) -> None:
        valid_id = "ou_" + "a" * 32
        assert OwnerConfigManager.OPEN_ID_PATTERN.match(valid_id) is not None

    def test_invalid_open_id(self) -> None:
        assert OwnerConfigManager.OPEN_ID_PATTERN.match("ou_short") is None

    def test_valid_union_id(self) -> None:
        valid_id = "on_" + "f" * 32
        assert OwnerConfigManager.UNION_ID_PATTERN.match(valid_id) is not None

    def test_invalid_union_id(self) -> None:
        assert OwnerConfigManager.UNION_ID_PATTERN.match("on_short") is None


class TestLoadDefaultOwnerId:
    def test_empty_env(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
        ):
            mgr = OwnerConfigManager()
            assert mgr._default_owner_id is None

    def test_env_variable_set(self) -> None:
        valid_id = "ou_" + "a" * 32
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(OwnerConfigManager, "_load_config", return_value={"DEFAULT_OWNER_ID": valid_id}),
        ):
            mgr = OwnerConfigManager()
            assert mgr._default_owner_id == valid_id

    def test_invalid_env_value(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(OwnerConfigManager, "_load_config", return_value={"DEFAULT_OWNER_ID": ""}),
        ):
            mgr = OwnerConfigManager()
            assert mgr._default_owner_id is None


class TestLoadConfig:
    def test_loads_from_db(self) -> None:
        with (
            patch("apps.core.config.utils.get_feishu_category_configs") as mock_get,
            patch.dict(os.environ, {}, clear=False),
            patch.object(OwnerConfigManager, "_load_config", wraps=None),
        ):
            mock_get.return_value = {"FEISHU_APP_ID": "app123", "FEISHU_APP_SECRET": "secret"}
            mgr = OwnerConfigManager()

    def test_loads_from_env(self) -> None:
        with (
            patch("apps.core.config.utils.get_feishu_category_configs", return_value=None),
            patch.dict(os.environ, {"FEISHU_APP_ID": "env_app", "FEISHU_APP_SECRET": "env_secret"}, clear=False),
            patch.object(OwnerConfigManager, "_load_config", wraps=None),
        ):
            mgr = OwnerConfigManager()

    def test_db_import_error(self) -> None:
        with (
            patch("apps.core.config.utils.get_feishu_category_configs", side_effect=ImportError("no module")),
            patch.dict(os.environ, {}, clear=False),
            patch.object(OwnerConfigManager, "_load_config", wraps=None),
        ):
            mgr = OwnerConfigManager()


class TestGetEffectiveOwnerId:
    def test_with_specified_id(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            valid_id = "ou_" + "a" * 32
            result = mgr.get_effective_owner_id(valid_id)
            assert result == valid_id

    def test_with_empty_specified_uses_default(self) -> None:
        default_id = "ou_" + "b" * 32
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=default_id),
        ):
            mgr = OwnerConfigManager()
            result = mgr.get_effective_owner_id(None)
            assert result == default_id

    def test_no_id_no_default(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            result = mgr.get_effective_owner_id(None)
            assert result is None

    def test_invalid_specified_id(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            # Invalid ID triggers a warning and falls back to None (no exception)
            result = mgr.get_effective_owner_id("invalid")
            assert result is None
