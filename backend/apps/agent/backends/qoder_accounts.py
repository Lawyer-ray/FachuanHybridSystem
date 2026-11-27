"""qoder 账号池：**多个账号共享额度**，按轮次轮转。

## 为什么是「多个账号」而不是「一人一个账号」

Qoder 的额度（Credits / 每日限额）是**账号级**的，而律所的业务数据权限是**律师级**的
（工具调用走共享 MCP，带律师本人 token，见 ``qoder_backend.build_mcp_servers``）。
两者不该绑在一起：

- 一人一账号 → N 份订阅费用，且新人入职要先开号才能用 AI；
- 全所一个账号 → 一个人跑长任务就吃掉全所额度，别人只能等明天。

所以：**账号是额度容器，人是权限主体**。池子里放几个账号，每轮挑一个最久没用的，
某个账号额度耗尽（``BUSY`` / ``RATE_LIMITED``）或登录失效（``AUTH``）就先把它挂起、
换下一个账号重跑——用户看到的是「稍微慢一点」，而不是「今日额度已满」。

## 落点

```
<FACHUAN_AGENT_HOME>/qoder/
├── config/                    # 历史单账号（升级前登录的），当作账号 ``default``
│   └── .auth/user
└── accounts/<account_id>/
    ├── meta.json              # 显示名 / 最后使用 / 最近一次失败
    └── config/                # 该账号的 QODER_CONFIG_DIR（含 .auth/user）
```

为什么历史目录不迁移：迁移要挪凭据文件，而那时可能有正在跑的轮次在用它。把
``config/`` 直接当成 ``default`` 账号读，升级零动作、也不会有「迁移做到一半」的状态。

## 「挂起」不是永久的

``mark_error`` 只记一个**冷却到期时间**（默认 10 分钟），到期自动回到候选池：
额度可能按小时/按天重置，登录也可能只是令牌抖动。永久拉黑一个账号需要人去看，
而池子里其它账号还能顶——所以这里只做「暂时别用它」，不做「它坏了」。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .toolface import agent_home

logger = logging.getLogger(__name__)

#: 账号池根目录（相对 ``<agent home>/qoder``）。
ACCOUNTS_SUBDIR = "accounts"
#: 历史单账号的 id（凭据在 ``<home>/qoder/config``，没有 meta 文件）。
LEGACY_ACCOUNT_ID = "default"
#: 单个账号的凭据文件名（相对该账号的 config 目录）。
CREDENTIAL_RELPATH = (".auth", "user")
#: 失败后的冷却时长（秒）。取值理由见模块 docstring 末段：额度会重置，别永久拉黑。
COOLDOWN_ENV = "FACHUAN_QODER_ACCOUNT_COOLDOWN"
DEFAULT_COOLDOWN_SECONDS = 600.0


def qoder_home() -> Path:
    """``<agent home>/qoder``（0700）。"""
    path = agent_home() / "qoder"
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def accounts_dir() -> Path:
    path = qoder_home() / ACCOUNTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def legacy_config_dir() -> Path:
    """历史单账号的 ``QODER_CONFIG_DIR``（升级前登录的凭据就在这）。"""
    return qoder_home() / "config"


def account_record_dir(account_id: str) -> Path:
    return accounts_dir() / _safe_id(account_id)


def account_config_dir(account_id: str) -> Path:
    """某个账号的 ``QODER_CONFIG_DIR``。"""
    if account_id == LEGACY_ACCOUNT_ID:
        return legacy_config_dir()
    path = account_record_dir(account_id) / "config"
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def credential_path(account_id: str) -> Path:
    return account_config_dir(account_id).joinpath(*CREDENTIAL_RELPATH)


def has_credential(account_id: str) -> bool:
    return credential_path(account_id).is_file()


def _safe_id(account_id: str) -> str:
    """只允许短字母数字 id（它来自 URL / 状态文件，不能拼出目录穿越）。"""
    cleaned = "".join(ch for ch in (account_id or "") if ch.isalnum())
    if not cleaned or len(cleaned) > 32:
        raise ValueError(f"非法的 qoder 账号 id: {account_id!r}")
    return cleaned


def cooldown_seconds() -> float:
    raw = os.environ.get(COOLDOWN_ENV, "").strip()
    if not raw:
        return DEFAULT_COOLDOWN_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_COOLDOWN_SECONDS
    return value if value > 0 else DEFAULT_COOLDOWN_SECONDS


@dataclass
class QoderAccount:
    """池子里的一个账号。"""

    id: str
    name: str
    #: 最近一次被选中跑轮的时刻（0 = 从没用过，会被优先选中）。
    last_used_at: float = 0.0
    #: 冷却到期时刻（0 = 健康）。
    cooldown_until: float = 0.0
    #: 最近一次失败的人话（给界面看；冷却结束后仍保留，直到下次成功）。
    last_error: str = ""

    @property
    def healthy(self) -> bool:
        return self.cooldown_until <= time.time()

    @property
    def has_credential(self) -> bool:
        return has_credential(self.id)


def _meta_path(account_id: str) -> Path:
    return account_record_dir(account_id) / "meta.json"


def _read_meta(account_id: str) -> dict[str, object]:
    try:
        data = json.loads(_meta_path(account_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_meta(account_id: str, **fields: object) -> None:
    if account_id == LEGACY_ACCOUNT_ID:
        # 历史账号的目录里还有 CLI 自己的文件，meta 单独放在 accounts/default/ 下
        account_record_dir(account_id).mkdir(parents=True, exist_ok=True)
    data = _read_meta(account_id)
    data.update(fields)
    try:
        _meta_path(account_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("qoder 账号元数据写入失败 account=%s", account_id, exc_info=True)


def _as_float(value: object) -> float:
    """meta.json 里读出来的时间戳（缺失/被手改成字符串时回落 0）。

    不用 ``float(x or 0)``：``object`` 上的 ``float()`` 是 mypy 的 ``no-any-return``
    高发点，而这里真正需要的是「不是数字就当 0」，不是「假装它是数字」。
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def list_accounts() -> list[QoderAccount]:
    """池子里的全部账号（含历史 ``default``）；顺序稳定（``default`` 在最前）。

    **只列有凭据或有过元数据的**：一个空目录不算账号，否则登录失败会在池子里留下
    一个永远选不中的空壳。
    """
    found: dict[str, QoderAccount] = {}
    if legacy_config_dir().joinpath(*CREDENTIAL_RELPATH).is_file():
        legacy_name = str(_read_meta(LEGACY_ACCOUNT_ID).get("name") or "") or "账号 1"
        found[LEGACY_ACCOUNT_ID] = QoderAccount(id=LEGACY_ACCOUNT_ID, name=legacy_name)
    with contextlib.suppress(OSError):
        for child in accounts_dir().iterdir():
            if not child.is_dir():
                continue
            account_id = child.name
            try:
                _safe_id(account_id)
            except ValueError:
                continue
            has_cred = has_credential(account_id)
            meta = _read_meta(account_id)
            if not has_cred and not meta:
                continue
            if account_id in found and has_cred:
                continue
            found[account_id] = QoderAccount(
                id=account_id,
                name=str(meta.get("name") or "") or f"账号 {len(found) + 1}",
                last_used_at=_as_float(meta.get("last_used_at")),
                cooldown_until=_as_float(meta.get("cooldown_until")),
                last_error=str(meta.get("last_error") or ""),
            )
    accounts = list(found.values())
    accounts.sort(key=lambda a: (a.id != LEGACY_ACCOUNT_ID, a.last_used_at))
    return accounts


def usable_accounts() -> list[QoderAccount]:
    """现在能用的账号（有凭据 + 不在冷却期）。"""
    return [a for a in list_accounts() if a.has_credential and a.healthy]


def any_config_dir() -> Path | None:
    """任一可用账号的 config 目录（``--list-models`` 这类「随便拿一个账号问一下」的场景）。"""
    for account in usable_accounts():
        return account_config_dir(account.id)
    for account in list_accounts():
        if account.has_credential:
            return account_config_dir(account.id)
    return None


def pick_account(*, exclude: set[str] | None = None) -> QoderAccount | None:
    """挑本轮用哪个账号：**最久没被用过的健康账号**（``exclude`` 是本轮已试过的）。

    为什么不随机：随机在池子小的时候会连续撞同一个账号（概率 1/N 的二项分布），
    表现是「额度用得快慢不均」。按 ``last_used_at`` 升序等价于轮转，且不需要维护
    「下一个是谁」的状态——状态少了就少一处能漂。
    """
    skip = exclude or set()
    for account in usable_accounts():
        if account.id not in skip:
            return account
    return None


def mark_used(account_id: str) -> None:
    _write_meta(account_id, last_used_at=time.time())


def mark_error(account_id: str, *, message: str, cooldown: float | None = None) -> None:
    """把账号挂起一段时间（额度耗尽 / 登录失效），并记下给人看的原因。"""
    until = time.time() + (cooldown if cooldown is not None else cooldown_seconds())
    _write_meta(account_id, cooldown_until=until, last_error=message[:200])
    logger.info("qoder 账号进入冷却 account=%s until=%.0f", account_id, until)


def mark_ok(account_id: str) -> None:
    """一轮成功：清掉冷却与错误（额度可能已重置，别让旧标签一直挂着）。"""
    _write_meta(account_id, cooldown_until=0.0, last_error="")


def create_account(name: str = "") -> str:
    """新建一个空账号（登录成功后才有凭据）。返回新的 account_id。"""
    account_id = uuid.uuid4().hex[:12]
    account_record_dir(account_id).mkdir(parents=True, exist_ok=True)
    if name:
        _write_meta(account_id, name=name)
    return account_id


def set_account_name(account_id: str, name: str) -> None:
    _write_meta(account_id, name=name.strip()[:40])


def delete_account(account_id: str) -> bool:
    """删账号：凭据 + 元数据 + CLI 配置目录一起删。返回是否真的删到了东西。"""
    if account_id == LEGACY_ACCOUNT_ID:
        path = legacy_config_dir()
    else:
        path = account_record_dir(account_id)
    if not path.exists():
        return False
    import shutil

    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


__all__ = [
    "ACCOUNTS_SUBDIR",
    "CREDENTIAL_RELPATH",
    "DEFAULT_COOLDOWN_SECONDS",
    "LEGACY_ACCOUNT_ID",
    "QoderAccount",
    "account_config_dir",
    "account_record_dir",
    "accounts_dir",
    "any_config_dir",
    "cooldown_seconds",
    "create_account",
    "credential_path",
    "delete_account",
    "has_credential",
    "legacy_config_dir",
    "list_accounts",
    "mark_error",
    "mark_ok",
    "mark_used",
    "pick_account",
    "qoder_home",
    "set_account_name",
    "usable_accounts",
]
