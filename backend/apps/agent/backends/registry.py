"""后端注册表：kind → AgentBackend 实现。

为什么用注册表而不是 if/elif：接入第三个 agent 时，if/elif 会长成
stream.py 里的分支汤，且新增后端要改主流程。注册表让「加一个 agent」
= 「写一个模块 + 一个装饰器」。
"""

from __future__ import annotations

import logging

from .base import AgentBackend

logger = logging.getLogger(__name__)

_BACKENDS: dict[str, AgentBackend] = {}


def register(backend: AgentBackend) -> AgentBackend:
    """注册一个后端。重复 kind 直接报错。

    不静默覆盖：两个模块注册同一个 kind 说明命名冲突或重复实现，
    上线后会发现「同一个名字跑出不同行为」，极难排查。

    Returns:
        传入的后端本身，便于当装饰器用（``@register``）。

    Raises:
        ValueError: 该 kind 已被占用（不论是否同一个对象——重复注册同一个实例
            也是重复 import 的信号，静默通过只会掩盖模块加载时机问题）。
    """
    if backend.kind in _BACKENDS:
        raise ValueError(f"agent backend 重复注册: {backend.kind}")
    _BACKENDS[backend.kind] = backend
    logger.debug("agent backend 已注册: %s", backend.kind)
    return backend


def get(kind: str) -> AgentBackend:
    """取后端实现；未注册时抛 LookupError（含可选清单）。

    Raises:
        LookupError: 该 kind 未注册。清单写进消息里，是为了让「kind 拼错」
            和「模块忘了 import 导致没注册」这两类问题一眼可分——只说
            「未知 backend」的话，两种情况长得一模一样。
    """
    try:
        return _BACKENDS[kind]
    except KeyError:
        raise LookupError(f"未知 agent backend: {kind!r}；已注册: {sorted(_BACKENDS)}") from None


def available_kinds() -> list[str]:
    """已注册的全部 kind（排序后返回）。

    排序是为了让「前端能力探测」「错误信息」「测试断言」拿到稳定的顺序：
    dict 插入序取决于 import 顺序，换个模块加载路径就变。
    """
    return sorted(_BACKENDS)


def clear() -> None:
    """清空注册表。仅供测试使用。

    生产代码不要调用：清空后所有 ``get()`` 都会抛 LookupError，正在跑的请求
    会在取后端那一步全部失败。
    """
    _BACKENDS.clear()
