"""async-unsafe 保护的临时放行工具。

遗留任务路径需要在事件循环线程执行 sync ORM（Django 默认抛
SynchronousOnlyOperation）。历史上这些代码直接写进程级环境变量且从不还原，
导致 web 进程/Q worker 全局失去保护。本工具将放行收敛到 with 块内，
退出时恢复原值。

正确方向仍是逐步将这些调用迁移到 async ORM / sync_to_async；
在新代码中禁止使用本工具（新增代码请直接用 aget/aupdate/sync_to_async）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

_ENV_KEY = "DJANGO_ALLOW_ASYNC_UNSAFE"


@contextmanager
def allow_async_unsafe() -> Iterator[None]:
    """with 块内临时放行 Django sync ORM 的 async 上下文保护，退出时恢复原值。"""
    old = os.environ.get(_ENV_KEY)
    os.environ[_ENV_KEY] = "true"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(_ENV_KEY, None)
        else:
            os.environ[_ENV_KEY] = old
