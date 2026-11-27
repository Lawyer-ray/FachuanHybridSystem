"""qoder 登录态与「前端点一下登录」的接缝（全离线，不起 CLI、不联网）。

守 8 件事：

1. **凭据落点固定**：``<FACHUAN_AGENT_HOME>/qoder/config/.auth/user``。它是
   「已登录」的唯一判据（``qoder_login.is_authenticated``）——判据漂了，前端就会
   在明明已登录时反复让人去登录。
2. **显式令牌也算已登录**：配了 ``QODER_PERSONAL_ACCESS_TOKEN`` / SA 密钥的部署
   不需要走浏览器授权。
3. **``/agent/backends`` 的 qoder 行**：未登录 → ``available=False`` + ``action=login``；
   SDK 没装 → 不给登录按钮（装包是运维的事）。
4. **状态文件是跨 worker 的**：轮询落在别的 worker 上也读得到；未知 id 返回
   ``expired`` 而不是 404（前端对两者的处理完全一样）。
5. **账号名只读非敏感字段**：``.auth/user`` 里含令牌，解析失败必须返回空串，
   不能把异常或整段 JSON 带出去。
6. **退出登录只删凭据文件**，不删整个 config 目录（``machine_id`` 等还要留着）。
7. **未登录时后端秒级报 AUTH**，文案指向**前端入口**（律师没有服务器 shell）。
8. **登录态目录权限 0700**（里面是凭据）。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from apps.agent.backends import qoder_login
from apps.agent.backends.base import BackendError, BackendErrorKind
from apps.agent.backends.qoder_backend import ACCESS_TOKEN_ENV, SA_KEY_ENV, ensure_logged_in

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """每个用例一个独立的 agent home（否则会读到开发机真实的登录态）。"""
    home = tmp_path / "ah"
    monkeypatch.setenv("FACHUAN_AGENT_HOME", str(home))
    monkeypatch.delenv(ACCESS_TOKEN_ENV, raising=False)
    monkeypatch.delenv(SA_KEY_ENV, raising=False)
    return home


def _write_credential(payload: dict[str, object] | str) -> Path:
    path = qoder_login.credential_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


# ── 1/2. 判据 ──────────────────────────────────────────────────────────


def test_not_authenticated_without_credential(_isolated_home: Path) -> None:
    assert qoder_login.has_credential() is False
    assert qoder_login.is_authenticated() is False


def test_credential_file_means_authenticated(_isolated_home: Path) -> None:
    _write_credential({"name": "法穿"})
    assert qoder_login.has_credential() is True
    assert qoder_login.is_authenticated() is True


def test_explicit_token_counts_as_authenticated(
    _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配了令牌/SA 密钥的部署不需要（也不应该被要求）走浏览器授权。"""
    monkeypatch.setenv(ACCESS_TOKEN_ENV, "pat-xxx")
    assert qoder_login.has_credential() is False
    assert qoder_login.is_authenticated() is True


def test_legacy_account_paths(_isolated_home: Path) -> None:
    """默认账号 = 历史单账号目录（升级前的部署不需要重新授权）。"""
    path = qoder_login.config_dir()
    assert path == _isolated_home / "qoder" / "config"
    assert qoder_login.credential_path() == path / ".auth" / "user"


def test_new_account_config_dir_is_private(_isolated_home: Path) -> None:
    """新账号的配置目录 0700（里面放的是凭据）。"""
    from apps.agent.backends import qoder_accounts

    account_id = qoder_accounts.create_account()
    path = qoder_accounts.account_config_dir(account_id)
    assert path == _isolated_home / "qoder" / "accounts" / account_id / "config"
    assert oct(os.stat(path).st_mode)[-3:] == "700"


# ── 3. 后端清单上的登录入口 ────────────────────────────────────────────


def test_probe_offers_login_when_not_authenticated(_isolated_home: Path) -> None:
    from apps.agent.api.session_api import _qoder_probe

    available, reason, action = _qoder_probe()
    assert available is False
    assert action == "login"
    # 文案要给出**可执行动作**，而不是让用户去猜
    assert "登录" in reason


def test_probe_is_available_when_authenticated(_isolated_home: Path) -> None:
    from apps.agent.api.session_api import _qoder_probe

    _write_credential({"name": "法穿"})
    available, reason, action = _qoder_probe()
    assert (available, reason, action) == (True, "", "")


# ── 4. 状态文件跨 worker ──────────────────────────────────────────────


def test_unknown_login_id_is_expired(_isolated_home: Path) -> None:
    """未知 id 返回 ``expired`` 而不是 404：前端对两者的处理完全一样。"""
    out = qoder_login.login_status("deadbeef")
    assert out["state"] == "expired"
    assert out["message"]


def test_login_status_reads_state_file(_isolated_home: Path) -> None:
    """状态落盘（不是内存）：轮询请求落到别的 worker 上也要答得出。"""
    login_id = "abc123"
    login_dir = qoder_login.login_dir()
    (login_dir / f"{login_id}.json").write_text(
        json.dumps({"state": "waiting", "url": "https://qoder.com/device/x", "message": "等人确认"}),
        encoding="utf-8",
    )
    out = qoder_login.login_status(login_id)
    assert out == {
        "login_id": login_id,
        "state": "waiting",
        "url": "https://qoder.com/device/x",
        "message": "等人确认",
        "account": "",
        "account_id": "",
    }


def test_login_id_with_path_tricks_is_rejected(_isolated_home: Path) -> None:
    """``login_id`` 来自 URL 路径：非字母数字一律当失效，防止拼出目录穿越。"""
    out = qoder_login.login_status("../../etc/passwd")
    assert out["state"] == "expired"


# ── 5. 账号名只读非敏感字段 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("payload", "expect"),
    [
        ({"name": "法穿"}, "法穿"),
        ({"email": "a@b.c"}, "a@b.c"),
        ({"user": {"name": "法穿"}}, "法穿"),
        ({"token": "secret"}, ""),
        ("{ not json", ""),
        ({"name": "  "}, ""),
    ],
)
def test_account_name_never_leaks_secrets(_isolated_home: Path, payload: object, expect: str) -> None:
    _write_credential(payload)  # type: ignore[arg-type]
    assert qoder_login.account_name() == expect


# ── 6. 退出登录只删凭据 ───────────────────────────────────────────────


def test_delete_credential_keeps_config_dir(_isolated_home: Path) -> None:
    path = _write_credential({"name": "法穿"})
    other = qoder_login.config_dir() / "installation_id"
    other.write_text("mid", encoding="utf-8")

    assert qoder_login.delete_credential() is True
    assert not path.exists()
    assert other.exists()  # machine_id 之类不能跟着没
    assert qoder_login.is_authenticated() is False
    # 再删一次是幂等的
    assert qoder_login.delete_credential() is False


# ── 7. 未登录时秒级报 AUTH ────────────────────────────────────────────


def test_ensure_logged_in_raises_auth_with_frontend_action(_isolated_home: Path) -> None:
    import asyncio

    with pytest.raises(BackendError) as excinfo:
        asyncio.run(ensure_logged_in())
    assert excinfo.value.kind is BackendErrorKind.AUTH
    assert excinfo.value.retryable is False
    # 动作必须是**前端入口**：律师没有 shell
    assert "登录 Qoder" in excinfo.value.message


def test_ensure_logged_in_passes_when_credential_present(_isolated_home: Path) -> None:
    import asyncio

    _write_credential({"name": "法穿"})
    asyncio.run(ensure_logged_in())  # 不抛


# ── 9. 账号池：轮转、冷却、增删 ────────────────────────────────────────


def _add_account(name: str = "") -> str:
    """造一个「已登录」的账号（写一个假凭据文件）。"""
    from apps.agent.backends import qoder_accounts

    account_id = qoder_accounts.create_account()
    cred = qoder_accounts.credential_path(account_id)
    cred.parent.mkdir(parents=True, exist_ok=True)
    cred.write_text(json.dumps({"name": name or account_id}), encoding="utf-8")
    return account_id


def test_account_pool_rotates_least_recently_used(_isolated_home: Path) -> None:
    """池子按「最久没用过的」轮转——随机会在小池子里连续撞同一个账号。"""
    from apps.agent.backends import qoder_accounts

    first = _add_account("A")
    second = _add_account("B")
    picked = qoder_accounts.pick_account()
    assert picked is not None
    qoder_accounts.mark_used(picked.id)
    other = qoder_accounts.pick_account()
    assert other is not None and other.id != picked.id
    assert {picked.id, other.id} == {first, second}


def test_account_cooldown_skips_then_recovers(_isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """额度耗尽的账号进冷却（默认 10 分钟），到期自动回到候选池。"""
    from apps.agent.backends import qoder_accounts

    account_id = _add_account("A")
    qoder_accounts.mark_error(account_id, message="今日额度已用尽", cooldown=0.05)
    assert qoder_accounts.usable_accounts() == []
    assert qoder_accounts.pick_account() is None

    time.sleep(0.1)
    usable = qoder_accounts.usable_accounts()
    assert [a.id for a in usable] == [account_id]
    # 冷却结束后错误原因仍留着（给人看「上次为什么失败」），但账号可用
    assert qoder_accounts.list_accounts()[0].last_error == "今日额度已用尽"


def test_mark_ok_clears_error(_isolated_home: Path) -> None:
    from apps.agent.backends import qoder_accounts

    account_id = _add_account("A")
    qoder_accounts.mark_error(account_id, message="x")
    qoder_accounts.mark_ok(account_id)
    account = qoder_accounts.list_accounts()[0]
    assert account.healthy and account.last_error == ""


def test_account_without_credential_is_not_listed(_isolated_home: Path) -> None:
    """登录失败会在池子里留下空目录——它不算账号，否则永远选不中。"""
    from apps.agent.backends import qoder_accounts

    qoder_accounts.create_account()
    assert qoder_accounts.list_accounts() == []


def test_delete_account_removes_everything(_isolated_home: Path) -> None:
    from apps.agent.backends import qoder_accounts

    account_id = _add_account("A")
    assert qoder_accounts.delete_account(account_id) is True
    assert qoder_accounts.list_accounts() == []
    assert not qoder_accounts.account_record_dir(account_id).exists()


def test_any_config_dir_prefers_usable_account(_isolated_home: Path) -> None:
    from apps.agent.backends import qoder_accounts

    account_id = _add_account("A")
    path = qoder_accounts.any_config_dir()
    assert path is not None
    assert path == qoder_accounts.account_config_dir(account_id)


def test_start_login_assigns_legacy_first_then_new_account(_isolated_home: Path) -> None:
    """第一次登录落历史账号；之后每点一次 = 往池子里加一个账号。"""
    from apps.agent.backends.qoder_login import _pick_login_account

    assert _pick_login_account(None) == "default"
    _add_account("A")
    assert _pick_login_account(None) != "default"
    assert _pick_login_account("abc123") == "abc123"
