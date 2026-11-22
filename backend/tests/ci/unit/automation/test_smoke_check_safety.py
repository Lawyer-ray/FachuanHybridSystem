"""P05-04 回归：smoke_check 的安全默认值。

旧实现：①无条件 `call_command("migrate")`；②口令 `settings.SMOKE_ADMIN_PASSWORD` 缺配时
退回内置默认口令 `smoke_admin_password`；③在真实库上没有任何确认闸门。
修法：migrate 必须 `--allow-migrate` 显式开启；口令只从 settings 读，缺失即 CommandError；
非 DEBUG / 非测试库需 `--yes`。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError

from apps.automation.management.commands.smoke_check import Command

_ALL_SKIP_OPTIONS: dict[str, Any] = {
    "database_path": None,
    "allow_migrate": False,
    "skip_migrate": False,
    "yes": True,
    "skip_admin": True,
    "skip_upload": True,
    "skip_websocket": True,
    "skip_q": True,
    "skip_disk": True,
    "disk_warning_pct": 85.0,
    "disk_critical_pct": 95.0,
}


def _safe_target_error(command: Command, options: dict[str, Any]) -> str | None:
    """跑确认闸门，返回 CommandError 文本；没有报错则返回 None（供断言用）。"""
    try:
        command._ensure_safe_target(options)
    except CommandError as exc:
        return str(exc)
    return None


def _run_handle(*, db_name: str = "fachuan_dev", debug: bool = False, **overrides: Any) -> MagicMock:
    """跑 `handle()`，把 migrate 调用、库名与外部副作用都换成 mock，返回 call_command 的 mock。"""
    options = {**_ALL_SKIP_OPTIONS, **overrides}
    command = Command()
    with (
        patch("apps.automation.management.commands.smoke_check.call_command") as mock_call_command,
        patch("apps.automation.management.commands.smoke_check.settings") as mock_settings,
        patch("apps.automation.management.commands.smoke_check.Client"),
        patch.object(Command, "_ensure_smoke_superuser", return_value=(MagicMock(), False)),
    ):
        mock_settings.DEBUG = debug
        mock_settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": db_name}}
        command.handle(**options)
    return mock_call_command


@pytest.mark.parametrize("deprecated_skip_migrate", [False, True])
def test_migrate_is_not_run_on_real_db_without_allow_migrate(deprecated_skip_migrate: bool) -> None:
    """非测试库上：默认（以及旧的 --skip-migrate）都不执行 migrate。"""
    mock_call_command = _run_handle(db_name="fachuan_dev", skip_migrate=deprecated_skip_migrate)

    mock_call_command.assert_not_called()


def test_allow_migrate_runs_migrate_on_real_db() -> None:
    """显式 --allow-migrate 才在真实库上跑 migrate。"""
    mock_call_command = _run_handle(db_name="fachuan_dev", allow_migrate=True)

    mock_call_command.assert_called_once_with("migrate", "--noinput", verbosity=0)


def test_migrate_still_runs_on_test_database() -> None:
    """测试库的 smoke 步骤（CI / make ci-backend）靠它建表，保持自动 migrate。"""
    mock_call_command = _run_handle(db_name="fachuan_ci_test")

    mock_call_command.assert_called_once_with("migrate", "--noinput", verbosity=0)


def test_missing_smoke_password_raises_and_creates_nothing() -> None:
    """settings 里没有口令时拒绝建超管（禁止内置默认口令）。"""
    command = Command()
    with (
        patch("apps.automation.management.commands.smoke_check.get_user_model") as mock_get_user_model,
        patch("apps.automation.management.commands.smoke_check.settings") as mock_settings,
    ):
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = None
        mock_get_user_model.return_value = mock_model
        mock_settings.SMOKE_ADMIN_PASSWORD = ""

        with pytest.raises(CommandError, match="SMOKE_ADMIN_PASSWORD"):
            command._ensure_smoke_superuser()

    mock_model.objects.create_superuser.assert_not_called()


def test_configured_password_is_used() -> None:
    """配了口令就用配的那一个，不再退回硬编码默认值。"""
    command = Command()
    with (
        patch("apps.automation.management.commands.smoke_check.get_user_model") as mock_get_user_model,
        patch("apps.automation.management.commands.smoke_check.settings") as mock_settings,
    ):
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = None
        mock_model.objects.create_superuser.return_value = "new_user"
        mock_get_user_model.return_value = mock_model
        mock_settings.SMOKE_ADMIN_PASSWORD = "configured-by-env"  # pragma: allowlist secret

        user, created = command._ensure_smoke_superuser()

    assert (user, created) == ("new_user", True)
    _, kwargs = mock_model.objects.create_superuser.call_args
    assert kwargs["password"] == "configured-by-env"  # pragma: allowlist secret


@pytest.mark.parametrize(
    ("debug", "db_name"),
    [(False, "fachuan_dev"), (False, "/var/data/fachuan_prod.sqlite3")],
)
def test_requires_yes_on_real_database(debug: bool, db_name: str) -> None:
    """DEBUG 关 + 库名不像测试库（即真实库）：没有 --yes 直接拒绝。"""
    command = Command()
    with patch("apps.automation.management.commands.smoke_check.settings") as mock_settings:
        mock_settings.DEBUG = debug
        mock_settings.DATABASES = {"default": {"NAME": db_name}}

        with pytest.raises(CommandError, match="--yes"):
            command._ensure_safe_target({"yes": False, "database_path": None})


@pytest.mark.parametrize(
    ("debug", "db_name"),
    [
        (True, "test_fachuan_dev"),
        (True, "fachuan_test"),
        (True, "/tmp/test_ci_smoke.sqlite3"),
        # pytest 会把库名再包一层 test_，且 setup_test_environment() 把 DEBUG 置 False
        (False, "test_test_fachuan_dev"),
        # 开发库（DEBUG 开）保持历史行为，不强制 --yes
        (True, "fachuan_dev"),
    ],
)
def test_disposable_unambiguous_target_needs_no_confirmation(debug: bool, db_name: str) -> None:
    """测试库 / 临时库 / DEBUG 开发库不需要 --yes，CI 与既有测试的现有调用不变。"""
    command = Command()
    with patch("apps.automation.management.commands.smoke_check.settings") as mock_settings:
        mock_settings.DEBUG = debug
        mock_settings.DATABASES = {"default": {"NAME": db_name}}

        error = _safe_target_error(command, {"yes": False, "database_path": None})

    assert error is None


def test_yes_flag_bypasses_confirmation() -> None:
    """显式 --yes 时允许在非 DEBUG 非测试库上运行；同一组合去掉 --yes 必须被拦。"""
    command = Command()
    with patch("apps.automation.management.commands.smoke_check.settings") as mock_settings:
        mock_settings.DEBUG = False
        mock_settings.DATABASES = {"default": {"NAME": "fachuan_dev"}}

        allowed_error = _safe_target_error(command, {"yes": True, "database_path": None})
        blocked_error = _safe_target_error(command, {"yes": False, "database_path": None})

    assert allowed_error is None
    assert blocked_error is not None
    assert "--yes" in blocked_error
