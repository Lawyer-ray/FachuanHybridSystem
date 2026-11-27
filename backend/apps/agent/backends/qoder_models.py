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

import json
import logging
import os
import re
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


#: 失败后的「别再的重试」窗口（秒）。见 `list_models` 里的说明。
FAILURE_TTL_SECONDS = 60.0

#: 磁盘缓存文件名（放 ``<FACHUAN_AGENT_HOME>/qoder/`` 下，与账号配置同目录）。
#:
#: 为什么除了内存还要落盘：内存缓存只活在一个进程里。开发态 ``--reload`` 每次改
#: 后端文件就丢一次；生产态 gunicorn 每个 worker 各丢一次——而每次冷启动要起子进程
#: 跑 ``--list-models``（实测 5.13s，最坏跑满 15s 超时）。落盘之后只有「这台机器第一次」
#: 要付这笔钱，菜单不再长时间空着，发言时也能直接拿到律所模型当默认。
CACHE_FILE_NAME = "models.json"

#: 磁盘缓存的**内容格式版本**。解析规则一变（例如 id 里带括号的那条修好之后）
#: 就必须让旧文件失效：里面存的是「已经解析好的 id」，旧文件会继续把坏 id 喂给
#: CLI，而新代码没有任何机会纠正它。
CACHE_FORMAT = 2

#: 缓存（模块级变量而不是 `dict[str, object]`：后者每处取值都要 cast，类型噪音大于收益）。
_cached_models: list[str] = []
_cached_at: float = 0.0
_cached_failed_at: float = 0.0


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
    global _cached_at, _cached_failed_at
    _cached_at = 0.0
    # 失败窗口也必须清：刚登录成功就要允许立刻重试，否则用户得再等一分钟
    _cached_failed_at = 0.0


def _parse(output: str) -> list[str]:
    """``--list-models`` 输出 → 模型 **id** 列表（去掉表头与空行，保序去重）。

    ## BYOK 自定义模型的行长这样

    ``kimi-2.6 (fachuan-gw/kimi-2.6)`` —— 括号里才是 ``--model`` 要的 id，
    括号外只是给人看的显示名。把整行当 id 传给 CLI 必然「模型不存在」，所以这里
    只取括号内的部分（没有括号的行本身就是 id，如 ``Auto`` / ``Ultimate``）。
    """
    models: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        name = line.strip()
        if not name or name.lower() == _HEADER:
            continue
        model_id = _strip_display_name(name)
        if model_id in seen:
            continue
        seen.add(model_id)
        models.append(model_id)
    return models


def _strip_display_name(line: str) -> str:
    """``显示名 (id)`` → ``id``；没有这层包装就原样返回。

    从**行尾往前配对括号**，不能靠正则的「第一个/最后一个括号」：实测有一条
    ``kimi-2.6(Anthropic) (fachuan-gw/kimi-2.6(Anthropic))``——id 自己带括号，
    用「非贪婪匹配到第一个括号」的写法会从中间切开、拼出一个不存在的模型名，选它必然
    「模型不存在」。括号里含空格（``(beta 版)`` 这类显示名后缀）不当 id。
    """
    if not line.endswith(")"):
        return line
    depth = 0
    for idx in range(len(line) - 1, -1, -1):
        char = line[idx]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth:
                continue
            head = line[:idx].strip()
            inside = line[idx + 1 : -1].strip()
            if not head or not inside or any(ch.isspace() for ch in inside):
                return line
            return inside
    return line


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


def _cache_path() -> Path:
    from .qoder_accounts import qoder_home

    return qoder_home() / CACHE_FILE_NAME


def _read_disk_cache() -> tuple[list[str], float]:
    """读磁盘缓存；坏了（手改、半截写、权限变）就当没有——缓存不是真相来源。"""
    try:
        payload = json.loads(_cache_path().read_text("utf-8"))
    except (OSError, ValueError):
        return [], 0.0
    if not isinstance(payload, dict):
        return [], 0.0
    try:
        version = int(payload.get("v") or 0)
    except (TypeError, ValueError):
        version = 0
    if version != CACHE_FORMAT:
        return [], 0.0
    raw_models = payload.get("models")
    models = (
        [str(name) for name in raw_models if isinstance(name, str) and name] if isinstance(raw_models, list) else []
    )
    try:
        at = float(payload.get("at") or 0.0)
    except (TypeError, ValueError):
        at = 0.0
    return models, at


def _write_disk_cache(models: list[str], at: float) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"v": CACHE_FORMAT, "models": models, "at": at}, ensure_ascii=False), "utf-8")
    except OSError as exc:  # 目录只读 / 磁盘满：缓存写不进去不该影响本轮
        logger.info("qoder 模型清单落盘失败（忽略）: %s", exc)


def cached_models() -> list[str]:
    """**绝不跑子进程**的清单：先内存、再磁盘；都在 TTL 外就返回上次的内存值。

    给「发言路径」用（``QoderBackend`` 决定默认模型）：那里不能为了一份模型清单
    等 5 秒子进程，拿不到就让 CLI 用自己的默认。
    """
    global _cached_models, _cached_at

    now = time.time()
    if _cached_models and now - _cached_at < _ttl():
        return list(_cached_models)
    models, at = _read_disk_cache()
    if models and now - at < _ttl():
        _cached_models, _cached_at = models, at
        return list(models)
    return list(_cached_models)


def cached_default_model() -> str | None:
    """``default_model()`` 的**不阻塞**版本（只用已缓存的清单）。"""
    return _pick_default(cached_models())


def list_models() -> list[str]:
    """当前账号能用的模型 id（带缓存；取不到时返回上一次的结果）。

    ## 失败也要缓存（2026-11-27 修）

    原来只缓存**成功**：`--list-models` 一旦持续失败（账号权限不对、CLI 卡在
    登录提示、网络不通），每次 `GET /agent/backends` 都要重跑子进程直到
    ``TIMEOUT_SECONDS``——实测把切换器端点拖到 **15 秒**，而前端在首屏就打开
    菜单，看到的是「后端清单暂不可用」这句误报。失败后应该很快退回上次结果。

    窗口取 ``FAILURE_TTL_SECONDS``（60s）而不是 TTL 的 10 分钟：模型清单会随
    账号套餐变，修好之后不该让人再等十分钟。成功缓存不动（仍是一个 TTL）。
    """
    global _cached_models, _cached_at, _cached_failed_at

    now = time.time()
    cached = list(_cached_models)
    if cached and now - _cached_at < _ttl():
        return cached
    # 内存没有 → 看磁盘（跨 reload / 跨 worker 的同一份清单）
    disk_models, disk_at = _read_disk_cache()
    if disk_models and now - disk_at < _ttl():
        _cached_models = disk_models
        _cached_at = disk_at
        return list(disk_models)
    # 刚失败过：不重启子进程，直接给上次结果（可能是空）
    if _cached_failed_at and now - _cached_failed_at < FAILURE_TTL_SECONDS:
        return disk_models or cached

    from .qoder_accounts import any_config_dir

    config_dir = any_config_dir()
    if config_dir is None:
        _cached_failed_at = now
        return disk_models or cached

    models = _run(config_dir)
    if models:
        _cached_models = models
        _cached_at = now
        _cached_failed_at = 0.0
        _write_disk_cache(models, now)
        return models
    _cached_failed_at = now
    return disk_models or cached


def platform_models(models: list[str] | None = None) -> list[str]:
    """律所网关那批模型（id 形如 ``fachuan-gw/<model>``），保持清单原顺序。"""
    from .qoder_byok import PLATFORM_PROVIDER_ID

    prefix = f"{PLATFORM_PROVIDER_ID}/"
    source = list_models() if models is None else models
    return [name for name in source if name.startswith(prefix)]


def default_model() -> str | None:
    """不指定模型时该用哪个 —— **律所网关模型优先**，其次 ``Auto``。

    ## 为什么不默认 ``Auto``（2026-11-27 改）

    ``Auto`` 是**Qoder 云侧**的型号，用哪个由它的账号套餐决定：本所账号实测报
    ``You do not have access to this model service. Please check your account permissions.``
    也就是说「不选模型」= 有一半概率直接失败，而失败信息还是英文的账号权限话术。
    ``fachuan-gw/*`` 这一批走律所自己的网关（BYOK，见 ``qoder_byok``），已经跑通。

    律师不选模型时的真实意图就是「和别处一样用律所自己的模型」，所以这里把
    律所模型排在前面；一个都没有（没登录 / 没接 BYOK / 关掉了 ``show_byok``）
    才回落到 ``Auto``。

    这个值同时被两处用，必须一致：
    - ``/agent/backends`` 的 ``default_model``（前端未选态显示「用什么」）；
    - ``QoderBackend`` 真正下发给 CLI 的 ``model``（不选时也照这个跑）。
    """
    return _pick_default(list_models())


def _pick_default(models: list[str]) -> str | None:
    """清单里该当默认的那个：律所网关模型 → ``Auto`` → 第一项。"""
    platform = platform_models(models)
    if platform:
        return platform[0]
    for candidate in ("Auto", "auto"):
        if candidate in models:
            return candidate
    return models[0] if models else None


#: 是否在模型下拉里列出 BYOK 自定义模型（``fachuan-gw/kimi-2.6`` 这种）。
#:
#: 默认**开**（2026-11-27 已跑通）：SDK 起 CLI 时必须带
#: ``QODER_SDK_CUSTOM_BASE_URL_BYOK=1`` 才会加载 BYOK provider（见 ``build_env``），
#: 加上之后 ``fachuan-gw/kimi-2.6`` 实测能回答且 ``model_usage`` 是它自己。
#: 留这个开关是为了「怀疑 BYOK 把栏弄坏」时能一键回到只有 Qoder 自有模型的形态。
SHOW_BYOK_ENV = "FACHUAN_QODER_SHOW_BYOK"


def show_byok() -> bool:
    raw = os.environ.get(SHOW_BYOK_ENV, "").strip().lower()
    if not raw:
        return True
    return raw in {"1", "true", "yes", "on"}


def for_display() -> tuple[list[str], str | None]:
    """``(models, default_model)``：``/agent/backends`` 直接用这个。"""
    models = list_models()
    if not show_byok():
        models = [name for name in models if "/" not in name]
    if not models:
        return [], None
    # 默认项与 `default_model()` 同一口径（律所模型优先）：两处不一致时前端会
    # 显示「默认 fachuan-gw/kimi-2.6」而实际跑的是 Auto——比不记住更糟。
    return models, _pick_default(models)


__all__ = [
    "CACHE_FILE_NAME",
    "CACHE_FORMAT",
    "CACHE_TTL_ENV",
    "DEFAULT_TTL_SECONDS",
    "FAILURE_TTL_SECONDS",
    "TIMEOUT_SECONDS",
    "cached_default_model",
    "cached_models",
    "default_model",
    "for_display",
    "platform_models",
    "invalidate",
    "show_byok",
    "list_models",
]
