"""Tests for owner_config_manager — additional coverage for uncovered branches."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.chat.owner_config_manager import OwnerConfigManager
from apps.core.exceptions import ConfigurationException, ValidationException


class TestValidateOwnerId:
    def test_empty_string(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.validate_owner_id("") is False

    def test_none_input(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.validate_owner_id(None) is False  # type: ignore[arg-type]

    def test_non_string_input(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.validate_owner_id(123) is False  # type: ignore[arg-type]

    def test_whitespace_only(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.validate_owner_id("   ") is False

    def test_valid_open_id(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            valid_id = "ou_" + "a" * 32
            assert mgr.validate_owner_id(valid_id) is True

    def test_valid_union_id(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            valid_id = "on_" + "f" * 32
            assert mgr.validate_owner_id(valid_id) is True

    def test_invalid_format(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.validate_owner_id("invalid_id") is False

    def test_open_id_wrong_length(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.validate_owner_id("ou_" + "a" * 10) is False


class TestValidateOwnerIdStrict:
    def test_valid_does_not_raise(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            valid_id = "ou_" + "a" * 32
            mgr.validate_owner_id_strict(valid_id)  # Should not raise

    def test_invalid_raises(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            with pytest.raises(ValidationException, match="群主ID格式无效"):
                mgr.validate_owner_id_strict("bad_id")


class TestGetEffectiveOwnerIdExtended:
    def test_specified_id_with_validation_disabled(self) -> None:
        config = {"OWNER_VALIDATION_ENABLED": False}
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value=config),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            result = mgr.get_effective_owner_id("any_string")
            assert result == "any_string"

    def test_whitespace_specified_falls_through(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            result = mgr.get_effective_owner_id("   ")
            assert result is None


class TestHandleEmptyOwnerId:
    def test_none_returns_default(self) -> None:
        default_id = "ou_" + "a" * 32
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=default_id),
        ):
            mgr = OwnerConfigManager()
            result = mgr.handle_empty_owner_id(None)
            assert result == default_id

    def test_empty_string_returns_default(self) -> None:
        default_id = "ou_" + "b" * 32
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=default_id),
        ):
            mgr = OwnerConfigManager()
            result = mgr.handle_empty_owner_id("")
            assert result == default_id

    def test_whitespace_returns_default(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            result = mgr.handle_empty_owner_id("   ")
            assert result is None

    def test_valid_id_returns_stripped(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            result = mgr.handle_empty_owner_id("  ou_abc  ")
            assert result == "ou_abc"


class TestConfigProperties:
    def test_is_test_environment(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={"TEST_MODE": True}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.is_test_environment() is True

    def test_is_validation_enabled(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={"OWNER_VALIDATION_ENABLED": False}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.is_validation_enabled() is False

    def test_is_retry_enabled(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={"OWNER_RETRY_ENABLED": False}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.is_retry_enabled() is False

    def test_get_max_retries(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={"OWNER_MAX_RETRIES": 5}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            assert mgr.get_max_retries() == 5


class TestGetConfigSummary:
    def test_summary_with_default_owner(self) -> None:
        valid_id = "ou_" + "a" * 32
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=valid_id),
        ):
            mgr = OwnerConfigManager()
            summary = mgr.get_config_summary()
            assert summary["has_default_owner"] is True
            assert summary["default_owner_id_prefix"] == "ou_"

    def test_summary_without_default_owner(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            summary = mgr.get_config_summary()
            assert summary["has_default_owner"] is False
            assert summary["default_owner_id_prefix"] is None


class TestReloadConfig:
    def test_reload_success(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            with (
                patch.object(mgr, "_load_config", return_value={"TEST_MODE": True}),
                patch.object(mgr, "_load_default_owner_id", return_value="ou_" + "c" * 32),
            ):
                mgr.reload_config()
                assert mgr._default_owner_id == "ou_" + "c" * 32

    def test_reload_failure(self) -> None:
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value={}),
            patch.object(OwnerConfigManager, "_load_default_owner_id", return_value=None),
        ):
            mgr = OwnerConfigManager()
            with (
                patch.object(mgr, "_load_config", side_effect=ValueError("config error")),
            ):
                with pytest.raises(ConfigurationException, match="重新加载配置失败"):
                    mgr.reload_config()


class TestLoadDefaultOwnerId:
    def test_test_environment_with_test_owner(self) -> None:
        config = {
            "TEST_MODE": True,
            "TEST_OWNER_ID": "ou_" + "d" * 32,
        }
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value=config),
        ):
            mgr = OwnerConfigManager()
            result = mgr._load_default_owner_id()
            assert result == "ou_" + "d" * 32

    def test_test_environment_no_test_owner(self) -> None:
        config = {"TEST_MODE": True}
        with (
            patch.object(OwnerConfigManager, "_load_config", return_value=config),
        ):
            mgr = OwnerConfigManager()
            result = mgr._load_default_owner_id()
            assert result is None
