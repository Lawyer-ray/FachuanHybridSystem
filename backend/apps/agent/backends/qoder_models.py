"""Qoder 侧可选模型清单（``qodercli --list-models`` 的缓存）。

## 为什么不能把平台的模型清单给它

``LLMProvider`` 里那批模型是**律所网关**的（kimi / glm …），qoder 云不认识；送给
它必然报错。反过来，qoder 这批（``Auto`` / ``Ultimate`` / ``Qwen4-Max`` / ``Kimi-K3.1-Pro`` …）
也只有它的账号认得。

所以「可选模型」必须**按后端各自问各自的来源**（``session_api._models_for_kind``）：

| 后端 | 模型来源 |
|:--|:--|
| pi / dsh / openai-agents / antigravity / claude-agent | ``LLMProvider``（Admin 里配） |
| qoder（默认） | **本模块**：Qoder 账号能用的模型 |
| qoder（``MODEL_SOURCE=gateway``） | ``LLMProvider``（BYOK 直连，需 ``allow_byok>=2``） |

## 为什么必须有缓存

``--list-models`` 要**起进程 + 联网**（实测 2.5s），而 ``GET /agent/backends`` 每次
打开切换器都会被调。不缓存 = 每次开菜单卡 2.5 秒。缓存 TTL 默认 10 分钟，登录成功
时主动失效（新账号的可用模型可能不同）。

失败时**返回上一次的清单**（而不是空）：模型清单不是安全边界，短暂网络故障不该让
已经选好的模型从下拉里消失——那会被理解成「模型没了」，用户只会重启页面。
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: 缓存 TTL（秒）。10 分钟：菜单卡顿的最小代价 vs 「运营给账号升级了套餐」的滞后。
CACHE_TTL_ENV = "FACHUAN_QODER_MODELS_TTL"
DEFAULT_TTL_SECONDS = 600.0
#: 单次 ``--list-models`` 的超时（秒）。实测 2.5s，15s 留足慢网络余量。
TIMEOUT_SECONDS = 15.0
#: 输出里的表头行（跳过）。
_HEADER = "model"

#: 缓存（模块级变量而不是 `dict[str, object]`：后者每处取值都要 cast，类型噪音大于收益）。
_cached_models: list[str] = []
_cached_at: float = 0.0


def _ttl() -> float:
    raw = os.environ.get(CACHE_TTL_ENV, "").strip()
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS
    return value if value >= 0 else DEFAULT_TTL_SECONDS


def invalidate() -> None:
    """丢掉缓存（登录成功 / 账号增删后调）。"""
    global _cached_at
    _cached_at = 0.0


def _parse(output: str) -> list[str]:
    """``--list-models`` 输出 → 模型 id 列表（去掉表头与空行，保序去重）。"""
    models: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        name = line.strip()
        if not name or name.lower() == _HEADER:
            continue
        if name in seen:
            continue
        seen.add(name)
        models.append(name)
    return models


def _run(config_dir: Path) -> list[str]:
    from .qoder_backend import build_env, resolve_cli_binary

    binary = resolve_cli_binary()
    if binary is None:
        return []
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    for key, value in build_env(config_dir=config_dir).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    try:
        proc = subprocess.run(
            [binary, "--list-models"],
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.info("qoder 模型清单获取失败（沿用上次结果）: %s", exc)
        return []
    return _parse(proc.stdout.decode(errors="replace"))


def list_models() -> list[str]:
    """当前账号能用的模型 id（带缓存；取不到时返回上一次的结果）。"""
    global _cached_models, _cached_at

    now = time.time()
    cached = list(_cached_models)
    if cached and now - _cached_at < _ttl():
        return cached

    from .qoder_accounts import any_config_dir

    config_dir = any_config_dir()
    if config_dir is None:
        return cached

    models = _run(config_dir)
    if models:
        _cached_models = models
        _cached_at = now
        return models
    return cached


def default_model() -> str | None:
    """不指定模型时 CLI 会用的那个（清单里的 ``Auto``，否则第一项）。

    为什么要显式给前端一个 `default_model`：模型下拉的未选态要显示「会自动用哪个」，
    空白会让人以为「没配好」（与其它后端的口径一致，见 ``BackendOptionOut``）。
    """
    models = list_models()
    for candidate in ("Auto", "auto"):
        if candidate in models:
            return candidate
    return models[0] if models else None


def for_display() -> tuple[list[str], str | None]:
    """``(models, default_model)``：``/agent/backends`` 直接用这个。"""
    models = list_models()
    if not models:
        return [], None
    default = "Auto" if "Auto" in models else models[0]
    return models, default


__all__ = [
    "CACHE_TTL_ENV",
    "DEFAULT_TTL_SECONDS",
    "TIMEOUT_SECONDS",
    "default_model",
    "for_display",
    "invalidate",
    "list_models",
]
