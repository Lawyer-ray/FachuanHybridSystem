"""默认 agent 后端 —— 「新会话不指定时用谁」的**唯一**判据。

## 为什么需要一个小模块

``"pi"`` 曾是这个问题的答案，且它散落在五处：``AgentSession.agent_kind`` 的列默认值、
``services/session_service.create_session``、``services/chat/stream`` 的兜底、
``chat/multi.primary_kind``、``/agent/backends`` 的列表顺序、以及前端的
``DEFAULT_AGENT_KIND``。换一次默认（本节就是换成 qoder）要改六处，漏一处的症状是
「菜单里默认标的是 A，实际建出来的会话是 B」——**没有任何报错**。

所以把判据收成一个函数，调用方只问它。

## 为什么不改 ``AgentSession.agent_kind`` 的列默认值

那会产出一条 migration（纯 default 变更），而**改默认值不影响任何已有行**：
历史会话的 ``agent_kind`` 是显式写入的 ``pi``，列默认只在「没人赋值的 insert」上生效，
而本仓库所有创建路径都显式赋值（见 ``session_service.create_session``）。
为一条不改变数据的迁移触迁移闸门（``migrate`` 需用户明确同意）不划算。

## 环境变量

``FACHUAN_DEFAULT_AGENT_KIND`` 可覆盖（部署级）。取值未注册时**回退**而不是报错：
默认值是偏好，不是契约——qoder 的 wheel 没装（平台没轮子）时，整站不该因为一个
默认偏好而起不来。
"""

from __future__ import annotations

import os

from .registry import available_kinds

#: 部署级覆盖入口。
DEFAULT_KIND_ENV = "FACHUAN_DEFAULT_AGENT_KIND"

#: 内置默认（未设环境变量时用谁）。
BUILTIN_DEFAULT_KIND = "qoder"

#: 最终兜底：所有后端都没注册时（只可能出现在测试里）返回它，调用方会自己报未知 kind。
LAST_RESORT_KIND = "pi"


def default_agent_kind() -> str:
    """本轮 / 本会话不指定后端时用谁。

    顺序：``FACHUAN_DEFAULT_AGENT_KIND`` → :data:`BUILTIN_DEFAULT_KIND` → ``pi`` →
    注册表里第一个。**只在「想要的没注册」时才回退**，这样「qoder 没装 → 自动用 pi」
    不需要运维再改一次配置。
    """
    kinds = available_kinds()
    wanted = os.environ.get(DEFAULT_KIND_ENV, "").strip() or BUILTIN_DEFAULT_KIND
    if wanted in kinds:
        return wanted
    if LAST_RESORT_KIND in kinds:
        return LAST_RESORT_KIND
    return kinds[0] if kinds else LAST_RESORT_KIND


__all__ = [
    "BUILTIN_DEFAULT_KIND",
    "DEFAULT_KIND_ENV",
    "LAST_RESORT_KIND",
    "default_agent_kind",
]
