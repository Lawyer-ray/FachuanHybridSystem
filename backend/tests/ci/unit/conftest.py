"""tests/ci/unit 的共享 fixture。

这里只放**进程级共享状态**的隔离，不放业务 fixture（业务 fixture 就近放在各自目录）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from apps.core.llm.key_pool import reset_shared_pools


@pytest.fixture(autouse=True)
def _isolate_shared_key_pools() -> Iterator[None]:
    """每个用例前后清空进程级 Key 池。

    Key 池按「平台名 + Key 列表 + 每 Key 上限 + 白名单」内容寻址并在**进程内复用**
    （服务路径与 Agent 路径共用同一注册表），因此失败冷却与在途计数是跨用例共享的状态：
    某个用例把 ``(Key, 模型)`` 打进 30 秒冷却后，后面用同一个池的用例就选不到该 Key，
    表现为「单独跑通过、一起跑失败」。
    """
    reset_shared_pools()
    yield
    reset_shared_pools()
