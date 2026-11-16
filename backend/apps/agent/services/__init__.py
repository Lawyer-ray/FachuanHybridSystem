"""Agent 服务层包。

``memory_service`` 已拆为 ``memory/`` 子包；此处保留旧模块名别名，
使 ``from apps.agent.services import memory_service`` 等既有导入不变。
"""

from __future__ import annotations

from . import memory as memory_service

__all__ = ["memory_service"]
