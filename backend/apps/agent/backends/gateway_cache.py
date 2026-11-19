"""``LLMProvider`` 解析结果的短 TTL 缓存（openai-agents / dsh 共用）。

## 为什么需要它

两个后端每轮都要把 ``LLMProvider`` 映射成「base_url + key + 模型」。这一步是
**同步 ORM 查询**，只能经 ``sync_to_async`` 丢到线程里跑：实测占掉一轮首字延迟
里约 1.3s（网关解析本身不慢，慢在「切线程 + 建连接 + 遍历 provider + 解密
``api_keys``」这一条固定开销上）。

## 红线一：用户在 Admin 里换模型 / 换 key 必须立刻生效

用户明确要求「可以换模型」。所以：

- TTL 短（默认 30s，上限 60s 见 :data:`MAX_TTL_SECONDS`）；
- ``LLMProvider`` 的 ``post_save`` / ``post_delete`` 信号直接清空缓存
  （见 ``apps/core/models/llm_provider.py`` 的信号注册）——Admin 保存那一刻
  起所有进程的下一轮就用新配置，不用等 TTL。

两条都做而不是只做一条：信号只管得到**本进程**（多 worker 部署时其他 worker
的缓存只能靠 TTL 自然过期），TTL 则保证最坏情况下 30s 内全网一致。

## 红线二：key 轮转不能被缓存固化

``_next_key`` 是一条有状态的轮转序列（``itertools.count``），缓存如果连
「选中的那一把 key」一起存，就等于把轮转冻结：所有会话永远压在同一把 key 上，
并发一高就限流。所以本模块只缓存 :class:`GatewaySettings`——**provider 的静态
配置**（base_url / 全部 key / 模型清单 / 思考开关），``_next_key`` 仍然每轮现调。

## 缓存键里必须有 model_hint

``_load_provider(model_hint)`` 会优先挑「白名单里含该模型」的 provider，
不同 model_hint 可能解析到**不同平台**（不同 base_url、不同 key）。键里不写
model_hint 就会把 A 平台的 key 发给 B 平台的地址。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: 缓存默认存活时间（秒）。取值理由见模块 docstring：既要挡住「每轮一次同步
#: ORM」的固定开销，又要在多 worker 部署（信号覆盖不到其他进程）时把
#: 「Admin 改了但这一轮还用旧配置」的窗口压到人感知不到的量级。
DEFAULT_TTL_SECONDS = 30.0

#: TTL 硬上限。配置错误（比如有人写 3600）时按上限截断——超过一分钟的窗口已经
#: 会让「Admin 里换模型」看起来没生效，而用户对这件事的容忍度是「刷新一下就该好」。
MAX_TTL_SECONDS = 60.0
TTL_ENV = "FACHUAN_GATEWAY_CACHE_TTL"

#: 缓存里最多留多少个键。键 = ``(model_hint,)``，实际只有几个（每个模型一个），
#: 上限只是防御「model 名被用户随意输入」造成无界增长。
_MAX_ENTRIES = 64


@dataclass(frozen=True)
class GatewaySettings:
    """一个 ``LLMProvider`` 的静态配置快照（不含任何轮转/选中状态）。

    ``api_keys`` 是**明文 key 列表**，所以 :meth:`__repr__` 被覆写成只打条数：
    dataclass 的默认 repr 会把全部字段展开，而「顺手 log 一个 dataclass」是完全
    常见的写法。
    """

    base_url: str
    api_keys: tuple[str, ...]
    models: tuple[str, ...]
    default_model: str
    enable_thinking: bool

    def __repr__(self) -> str:
        # 覆盖默认 repr：默认实现会把 api_keys 明文打出来，而一个 dataclass
        # 很可能被顺手 log 出去（``logger.debug("%s", settings)``）。
        return (
            f"GatewaySettings(base_url={self.base_url!r}, api_keys=<{len(self.api_keys)} keys>, "
            f"models={list(self.models)!r}, default_model={self.default_model!r}, "
            f"enable_thinking={self.enable_thinking!r})"
        )


@dataclass(frozen=True)
class _Entry:
    settings: GatewaySettings | None
    expires_at: float


def model_supports_thinking(model: str, provider: Any | None = None) -> bool:
    """该模型是否属于「可开关思考模式」的推理模型。

    ``provider`` 给得出时直接问它（``LLMProvider.supports_thinking``，同步上下文
    里已是实列）；走缓存路径拿不到实列时用 ``LLMProvider`` 同一份特征表——
    两处各写一套会让同一个模型在「传了 provider」与「走缓存」两条路径上判出
    不同结果，表现是同一平台的思考开关时灵时不灵。
    """
    method = getattr(provider, "supports_thinking", None) if provider is not None else None
    if callable(method):
        return bool(method(model))

    from apps.core.models.llm_provider import _THINKING_CAPABLE_MARKERS

    used = (model or "").lower()
    for ch in ("-", "_", ".", " ", "(", ")", "/", ":"):
        used = used.replace(ch, "")
    return any(marker in used for marker in _THINKING_CAPABLE_MARKERS)


_lock = threading.Lock()
_cache: dict[str, _Entry] = {}
#: 全局代数。每次 :func:`invalidate_gateway_cache` 加一：信号触发时我们无法
#: 逐个进程清缓存（多 worker），而本进程内清了就够——代数只用于测试断言
#: 「信号真的清了」，不参与命中判定。
_generation = 0


def ttl_seconds() -> float:
    """当前生效的 TTL（秒）。环境变量解析失败时回落到默认值并 warning。"""
    raw = os.environ.get(TTL_ENV, "").strip()
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("网关缓存 TTL 配置无法解析（%s=%r），使用默认 %ss", TTL_ENV, raw, DEFAULT_TTL_SECONDS)
        return DEFAULT_TTL_SECONDS
    if value <= 0:
        # 0 / 负数 = 关掉缓存：每次现查，行为与优化前完全一致（便于排障与回滚）。
        return 0.0
    return min(value, MAX_TTL_SECONDS)


def _cache_key(model_hint: str | None) -> str:
    """缓存键：只含 model_hint（**区分大小写原样保留**）。

    为什么不把「当前启用的 provider 列表」也算进键里：那要把 provider 查一遍
    才能算键，等于取消缓存的意义。信号失效 + 短 TTL 覆盖「provider 列表变了」
    这类变更。
    """
    return (model_hint or "").strip()


def settings_from_provider(provider: Any) -> GatewaySettings:
    """把 ``LLMProvider``（或同形状的桩）取成 :class:`GatewaySettings`。

    ``_provider_keys_and_models`` / ``_provider_models`` 复用 pi 的实现：``api_keys``
    的 ``key|model1,model2`` 格式、``extra_models`` 的混写分隔符各写一份必然分叉
    （见 ``openai_agents_backend.resolve_gateway`` 的注释）。
    """
    from ..pi.model_config import _provider_keys_and_models, _provider_models

    keys, _scopes = _provider_keys_and_models(provider)
    return GatewaySettings(
        base_url=str(getattr(provider, "base_url", "") or "").strip(),
        api_keys=tuple(keys),
        models=tuple(_provider_models(provider)),
        default_model=str(getattr(provider, "default_model", "") or "").strip(),
        enable_thinking=bool(getattr(provider, "enable_thinking", False)),
    )


def _load(model_hint: str | None) -> GatewaySettings | None:
    """真正读库的那一步（同步 ORM；调用方负责 ``sync_to_async``）。

    ``_load_provider`` 恰好是把查询异常吞成 warning 并返回 ``None`` 的那一层，
    所以这里拿不到「读库失败」与「没有可用 provider」的区别——两者都会在调用方
    变成 ``UNAVAILABLE``，与优化前一致。
    """
    from ..pi.model_config import _load_provider

    provider = _load_provider(model_hint or "")
    if provider is None:
        return None
    return settings_from_provider(provider)


def get_gateway_settings(model_hint: str | None) -> GatewaySettings | None:
    """取该 model_hint 的网关配置（**同步**，命中缓存时不动数据库）。

    调用方必须用 ``sync_to_async(..., thread_sensitive=True)`` 包一层：本函数
    未命中时会读同步 ORM，直接在事件循环里调用会抛 ``SynchronousOnlyOperation``。

    未命中且查不到 provider 时**缓存 ``None`` 一小段时间是刻意的**：没有可用
    provider 通常是管理员还没配好，期间每轮都去查库只会把首字延迟继续拖长，
    而真正配好后 ``post_save`` 信号会立刻清掉这条负缓存。

    返回的对象是**不可变快照**，调用方可以放心在多个协程间共享；``api_key``
    的轮转由调用方用 ``_next_key(settings.api_keys)`` 每轮现算。
    """
    ttl = ttl_seconds()
    if ttl <= 0:
        return _load(model_hint)

    key = _cache_key(model_hint)
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
    if entry is not None and entry.expires_at > now:
        return entry.settings

    settings = _load(model_hint)
    with _lock:
        if len(_cache) >= _MAX_ENTRIES and key not in _cache:
            _cache.clear()
        _cache[key] = _Entry(settings=settings, expires_at=time.monotonic() + ttl)
    return settings


def invalidate_gateway_cache(**_kwargs: object) -> None:
    """清空缓存（``LLMProvider`` 保存/删除时由信号调用；测试收尾也用它）。

    ``**_kwargs`` 不是摆设：本函数被直接 ``connect`` 到 ``post_save`` /
    ``post_delete``，Django 调用 receiver 时**总是**带 ``sender=`` 以及
    ``instance=`` / ``created=`` 等关键字参数。签名里不收就会在第一次保存
    ``LLMProvider`` 时抛 ``ValueError: Signal receivers must accept keyword
    arguments``——而那个异常发生在 Admin 保存路径上，表现为「点保存报错」，
    与缓存毫无字面关联，排查方向会被带偏（实测踩过：整个 agent 测试套件
    在 django.setup() 阶段就崩了）。
    """
    global _generation
    with _lock:
        _cache.clear()
        _generation += 1


def cache_generation() -> int:
    """当前失效代数（每次 :func:`invalidate_gateway_cache` 加一）。"""
    return _generation


def cached_entry_count() -> int:
    """当前缓存条目数（诊断与测试用）。"""
    with _lock:
        return len(_cache)


async def load_api_keys(model_hint: str | None) -> tuple[str, ...]:
    """本轮可用的网关 key 池（``LLMProvider.api_keys``）；拿不到时返回空元组。

    ## 为什么放在这里（而不是各调用方自己查库）

    「哪些 key 可用于本轮」与「网关怎么配」是同一件事，而网关配置的唯一来源
    就是本模块的缓存。两处各写一遍 ``sync_to_async(_load_provider)`` 迟早会漂移
    （一处带了 ``model_hint``、另一处没带 → 解析到不同平台 → 拿错 key 池发到
    另一个 base_url，且不报错）。

    ## 绝不抛异常

    key 分配是「别撞上网关每 key 并发上限」的**优化**，不是鉴权。读配置失败时
    返回空元组，调用方于是退回后端自己的 ``_next_key`` 轮转——那正是引入轮次级
    分配之前的行为。律师不该因为运维把 provider 配坏而**提问失败**。

    Args:
        model_hint: 本轮的模型名。不同 hint 可能解析到**不同 provider**（不同的
            base_url / key 池），所以它是缓存键的一部分，不能省。

    Returns:
        key 元组；无可用 provider / 读失败时为空元组。
    """
    from asgiref.sync import sync_to_async

    try:
        settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(model_hint)
    except Exception:
        logger.warning("读取网关配置失败，本轮沿用后端自己的 key 轮转", exc_info=True)
        return ()
    return tuple(settings.api_keys) if settings is not None else ()
