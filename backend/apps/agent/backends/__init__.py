"""Agent 后端抽象层：统一接缝 + 注册表。

具体后端实现（``PiBackend`` 等）各自一个模块，import 时用 ``@register``
把自己挂进注册表；本包只导出接缝本身，不 import 任何实现——否则接入第二个
agent 时，光是 import 本包就会连带拉起 pi 的依赖。
"""

from __future__ import annotations

from .base import (
    MAKE_HANDLE_METHOD,
    AgentBackend,
    BackendCapabilities,
    BackendError,
    BackendErrorKind,
    LiveBackendHandle,
    RunContext,
    StreamFrame,
)
from .registry import available_kinds, clear, get, register

__all__ = [
    "MAKE_HANDLE_METHOD",
    "AgentBackend",
    "StreamFrame",
    "BackendCapabilities",
    "BackendError",
    "BackendErrorKind",
    "LiveBackendHandle",
    "RunContext",
    "available_kinds",
    "clear",
    "get",
    "register",
]
