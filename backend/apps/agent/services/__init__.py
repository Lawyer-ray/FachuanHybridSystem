"""Agent 服务层包。

``memory_service`` 已拆为 ``memory/`` 子包；此处保留旧模块名别名，
使 ``from apps.agent.services import memory_service`` 等既有导入不变。

## 为什么别名是懒加载（PEP 562 ``__getattr__``）

``memory/`` 一路 import 到 ``apps.agent.models``，那会在**模块导入期**碰
``settings.AUTH_USER_MODEL``。本仓有不走 Django 的 CLI：``python -m
apps.agent.services.ui_action --ts``（UI 动作清单 → 前端 ``generated.ts`` 的生成器）。
``-m`` 必须先 import 父包（就是本文件），急切 import 于是把 Django 模型拖进一个没有
``django.setup()`` 的进程，直接 ``AppRegistryNotReady``——生成器根本跑不起来，
而报错位置指向 Django 模型、不是真凶。

改懒之后：Django 进程内的 ``from apps.agent.services import memory_service`` 行为完全
不变（首次访问才 import），纯数据 CLI 则完全不碰 Django。同款范式见
``apps/evidence/services/__init__.py``。
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["memory_service"]


def __getattr__(name: str) -> Any:
    """延迟导入：只有真访问 ``memory_service`` 时才把 memory 子包（及 Django 模型）拉进来。"""
    if name == "memory_service":
        return importlib.import_module(".memory", __package__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
