"""qoder 登录态：状态查询 + 由前端按钮触发的浏览器授权流程。

## 为什么要做成「前端点一下」

``qodercli login`` 是**浏览器设备授权**：它打印一个
``https://qoder.com/device/selectAccounts?...`` 链接，等人点开并确认，然后自己收尾。
这条链路没法用环境变量替代——运维把令牌配到服务器上是最省事的，但律师没有服务器
访问权，「换台机器换个人就得重新配」也不能接受。

所以做成三件事（对应 API 三个端点）：

1. ``GET  /agent/qoder/auth``          —— 现在登没登（**只读本地文件，不起进程、不联网**）
2. ``POST /agent/qoder/login``         —— 起 ``qodercli login``，把授权链接交回前端
3. ``GET  /agent/qoder/login/{id}``    —— 轮询这次授权的结果

## 凭据落在哪、为什么是这里

``<agent home>/qoder/config``（``FACHUAN_AGENT_HOME`` 下，0700）。三条理由：

- **共享**：``FACHUAN_AGENT_HOME`` 在多 worker 部署里是共享目录（见根 ``CLAUDE.md``），
  所以一个 worker 上点的登录，其它 worker 下一轮就能用；
- **不污染**开发机的 ``~/.qoder``（那是 IDE / CLI 自己用的）；
- **可枚举**：登录成功的判据就是 ``<该目录>/.auth/user`` 存在（实测：失败 / 进行中
  只有 ``machine_id`` / ``.credential-transaction``，成功后才有 ``user``）。

## 为什么不把令牌存进数据库

令牌要交给**子进程**（``QODER_CONFIG_DIR``），存库还得每轮解密写盘，多一份泄露面；
而且 CLI 自己会在该目录里刷新它（token 有有效期），存库的文字版迟早与磁盘版不一致。
**磁盘是唯一真相，数据库不参与。**

## 状态文件为什么落盘而不是放内存

登录进程归属某一个 worker，而轮询请求可能落到别的 worker（多进程部署）。状态落
``<agent home>/qoder/login/<id>.json`` 后，任何一个 worker 都能回答「授权完了没」。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from .toolface import agent_home

logger = logging.getLogger(__name__)

#: 登录态与登录流程都放在 ``<agent home>/qoder`` 下。
QODER_HOME_SUBDIR = "qoder"
#: ``QODER_CONFIG_DIR`` 指向的目录（登录凭据在这里的 ``.auth/user``）。
CONFIG_SUBDIR = "config"
#: 每次登录尝试的状态文件目录。
LOGIN_SUBDIR = "login"
#: 凭据文件（相对 config 目录）。存在 = 已登录（实测判据，见模块 docstring）。
CREDENTIAL_RELPATH = (".auth", "user")

#: 等授权链接打印出来的上限（秒）。CLI 冷启动约 1s，30s 留足慢机器余量。
URL_WAIT_SECONDS = 30.0
#: 一次登录尝试的总时限（秒）。超时杀进程并置 ``expired``——否则一个忘关的页面会
#: 让子进程挂一整天。
LOGIN_TIMEOUT_SECONDS = 600.0
#: 状态文件保留多久（秒）。轮询最后一个请求之后就没用了，留一天供排查。
STATE_TTL_SECONDS = 24 * 3600

#: 登录尝试的状态。
LoginState = Literal["waiting", "success", "failed", "expired"]
#: 从 CLI 输出里取授权链接（``https://`` 到行尾/空白）。
_URL_RE = re.compile(r"https://[^\s\"']+")

#: 后台监听任务的强引用。不加这个会被 GC 掉——表现为「链接出来了，但永远是 waiting」。
_WATCHERS: set[asyncio.Task[None]] = set()

#: 输出尾巴保留多少行（失败原因用）。
_TAIL_LINES = 20

#: 等待授权的提示语里不要带 URL（URL 单独一个字段给前端渲染成按钮）。
_TIP_WAITING = "已打开授权链接：请在浏览器里选择账号并确认，完成后本页会自动更新。"
_TIP_FAILED = "授权未完成：CLI 报错或已退出。请重新点「登录 Qoder」再试一次。"


# ── 目录与状态 ──────────────────────────────────────────────────────────


def qoder_home() -> Path:
    """``<agent home>/qoder``（0700）。"""
    path = agent_home() / QODER_HOME_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def config_dir() -> Path:
    """``QODER_CONFIG_DIR``：登录凭据与 CLI 会话的落点（0700）。"""
    path = qoder_home() / CONFIG_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def credential_path() -> Path:
    """凭据文件路径（存在即已登录）。"""
    return config_dir().joinpath(*CREDENTIAL_RELPATH)


def has_credential() -> bool:
    """本机（本 agent home）是否已有一套可用的 qoder 登录凭据。"""
    return credential_path().is_file()


def is_authenticated() -> bool:
    """qoder 现在能不能跑：配了显式凭据 **或** 磁盘上有登录态。

    **只看本地文件，不起进程、不联网**：它被 ``/agent/backends`` 调用，那个端点
    每次打开切换器都会被拉一次（与其它后端的探测同口径，见 ``session_api`` 的
    ``_opencode_probe`` 说明）。
    """
    from .qoder_backend import has_explicit_auth

    return has_explicit_auth() or has_credential()


def login_dir() -> Path:
    """登录状态文件目录（0700）。"""
    path = qoder_home() / LOGIN_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def _state_file(login_id: str) -> Path:
    return login_dir() / f"{login_id}.json"


def _write_state(login_id: str, **fields: Any) -> dict[str, Any]:
    """写一次状态（合并已有字段）。写失败只记日志：状态文件丢了最坏是「永远 waiting」。"""
    data: dict[str, Any] = {"login_id": login_id, "updated_at": time.time()}
    existing = _read_state(login_id)
    if existing:
        data.update({k: v for k, v in existing.items() if k not in data})
    data.update(fields)
    try:
        _state_file(login_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("qoder 登录状态写入失败 login=%s", login_id, exc_info=True)
    return data


def _read_state(login_id: str) -> dict[str, Any]:
    try:
        raw = _state_file(login_id).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _purge_stale_states() -> None:
    """清掉过期的状态文件（登录成功/失败后没人再来轮询）。"""
    deadline = time.time() - STATE_TTL_SECONDS
    with contextlib.suppress(OSError):
        for child in login_dir().glob("*.json"):
            with contextlib.suppress(OSError):
                if child.stat().st_mtime < deadline:
                    child.unlink()


def login_status(login_id: str) -> dict[str, Any]:
    """读一次登录尝试的状态。未知 id 返回 ``state="expired"``（不抛 404）。

    为什么不抛 404：前端轮询在「worker 重启 / 状态文件被清理」时会拿到 404，而它的
    正确处理与 ``expired`` 完全一样（提示用户重新点登录）。让它每次自己判断 404
    语义，等于把这个分支复制到前端。
    """
    if not login_id or not login_id.isalnum():
        return {"login_id": login_id, "state": "expired", "url": "", "message": "登录会话已失效，请重新登录。"}
    data = _read_state(login_id)
    if not data:
        return {"login_id": login_id, "state": "expired", "url": "", "message": "登录会话已失效，请重新登录。"}
    return {
        "login_id": login_id,
        "state": str(data.get("state") or "waiting"),
        "url": str(data.get("url") or ""),
        "message": str(data.get("message") or ""),
        "account": str(data.get("account") or ""),
    }


# ── 登录流程 ────────────────────────────────────────────────────────────


async def start_login() -> dict[str, Any]:
    """起一次 ``qodercli login``，返回 ``{login_id, state, url, message}``。

    Raises:
        BackendError: CLI 找不到 / 起不来 / 30s 内没打印授权链接。
    """
    from .base import BackendError, BackendErrorKind
    from .qoder_backend import build_env, resolve_cli_binary

    binary = resolve_cli_binary()
    if binary is None:
        raise BackendError(
            BackendErrorKind.UNAVAILABLE,
            "未找到 qodercli（请安装 qoder-agent-sdk，或设置 FACHUAN_QODER_CLI_PATH）",
        )

    _purge_stale_states()
    login_id = uuid.uuid4().hex
    _write_state(login_id, state="waiting", url="", message="正在启动 qodercli login…")

    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    for key, value in build_env(config_dir=config_dir()).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    # 别让服务器上的浏览器被打开（有 GUI 的开发机上会真的弹窗，且那个窗口对着的是
    # 服务器进程——授权要用户自己在**自己**的浏览器里点）。
    env["BROWSER"] = "true"

    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "login",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except OSError as exc:
        _write_state(login_id, state="failed", message=f"无法启动 qodercli：{exc}")
        raise BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE) from exc

    url = await _wait_for_url(proc)
    if url is None:
        with contextlib.suppress(Exception):
            proc.kill()
        message = "qodercli 未给出授权链接（30 秒内没有输出）。请检查服务器能否访问 qoder.com。"
        _write_state(login_id, state="failed", message=message)
        raise BackendError(BackendErrorKind.UNAVAILABLE, message)

    _write_state(login_id, state="waiting", url=url, message=_TIP_WAITING)
    watcher = asyncio.ensure_future(_watch_login(login_id, proc))
    _WATCHERS.add(watcher)
    watcher.add_done_callback(_WATCHERS.discard)
    return login_status(login_id)


async def _wait_for_url(proc: asyncio.subprocess.Process) -> str | None:
    """读 CLI 输出直到出现授权链接（或超时 / 进程退出）。"""
    assert proc.stdout is not None
    deadline = time.monotonic() + URL_WAIT_SECONDS
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
        except TimeoutError:
            return None
        if not line:
            return None
        match = _URL_RE.search(line.decode(errors="replace"))
        if match:
            return match.group(0)
    return None


async def _watch_login(login_id: str, proc: asyncio.subprocess.Process) -> None:
    """在后台等这次授权结束，把结果写进状态文件。

    ## 判据是「进程退出码 + 凭据文件」，不是输出文字

    CLI 成功时会打印 ``Login successful!``，但那条文案随时可能改。所以：

    - 进程退出码 0 **且** ``.auth/user`` 出现 → ``success``；
    - 其余 → ``failed``（附最后几行输出，便于判断是超时、网络还是账号问题）。

    ## 为什么必须有总时限

    用户可能点了链接又关掉页面，CLI 就会一直 ``Waiting for browser authorization…``。
    没有上限时这条子进程会挂到部署重启为止。
    """
    tail: list[str] = []
    try:
        code = await asyncio.wait_for(proc.wait(), timeout=LOGIN_TIMEOUT_SECONDS)
    except TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        _write_state(login_id, state="expired", message="授权超时（10 分钟未完成），请重新点「登录 Qoder」。")
        logger.info("qoder 登录超时 login=%s", login_id)
        return

    with contextlib.suppress(Exception):
        if proc.stdout is not None:
            rest = await proc.stdout.read()
            tail = rest.decode(errors="replace").splitlines()[-_TAIL_LINES:]
    detail = "\n".join(line for line in tail if line.strip())[-300:]

    if code == 0 and has_credential():
        _write_state(login_id, state="success", message="已登录 Qoder，可以开始提问了。", account=account_name())
        logger.info("qoder 登录成功 login=%s", login_id)
        return

    message = _TIP_FAILED + (f"（CLI 输出：{detail}）" if detail else "")
    _write_state(login_id, state="failed", message=message)
    logger.warning("qoder 登录失败 login=%s exit=%s", login_id, code)


def account_name() -> str:
    """已登录账号的显示名（取不到返回空串）。

    ## 为什么只读凭据文件的非敏感字段

    ``.auth/user`` 是 JSON，含令牌等敏感内容。这里只取「显示名」那一个字段，且
    读失败就返回空串——**绝不让异常把整段 JSON 带进日志或接口响应**。
    """
    path = credential_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("name", "display_name", "displayName", "username", "email", "user_name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:64]
    # 常见形状：{"user": {"name": ...}} —— 只在顶层找不到时试一层
    nested = data.get("user")
    if isinstance(nested, dict):
        for key in ("name", "display_name", "displayName", "username", "email"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:64]
    return ""


def delete_credential() -> bool:
    """删掉本机的 qoder 登录态（退出登录）。返回是否真的删到了东西。

    只在 ``.auth/user`` 存在时删它，**不删整个 config 目录**：那里还有 CLI 的
    machine_id 等非凭据文件，删了会让下次登录换一个设备身份。
    """
    path = credential_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        logger.warning("qoder 凭据删除失败: %s", path, exc_info=True)
        return False
    # ``.credential-transaction`` 是登录过程的中转文件，残留会让 CLI 认为有未完成的事务。
    with contextlib.suppress(OSError):
        shutil.rmtree(path.parent / ".credential-transaction", ignore_errors=True)
    return True


__all__ = [
    "CREDENTIAL_RELPATH",
    "LOGIN_TIMEOUT_SECONDS",
    "LoginState",
    "QODER_HOME_SUBDIR",
    "URL_WAIT_SECONDS",
    "account_name",
    "config_dir",
    "credential_path",
    "delete_credential",
    "has_credential",
    "is_authenticated",
    "login_status",
    "qoder_home",
    "start_login",
]
