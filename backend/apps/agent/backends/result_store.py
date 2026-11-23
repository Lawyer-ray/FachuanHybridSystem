"""有上限的「每轮收尾事实」存储（F6，2026-11-23 二轮审计）。

四个 agent 后端都用 `_results[run_id] = XxxRunResult` 记「本轮收尾事实」，
只有 `claude_agent_backend` 做了 `MAX_KEPT_RESULTS=256` 封顶；dsh / openai_agents /
antigravity 三个是裸 `dict`，只在部分路径 `pop` 自己那个 run_id ——
常驻进程（含共享 MCP）每跑一次就残留一条，长期缓慢涨内存。

这里把「OrderedDict + 上限 + 丢最旧」提成公共实现，三个后端直接替换容器即可，
不需要改调用点（仍是 dict 接口）。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

#: 每个后端保留最近多少条收尾事实。与 `claude_agent_backend.MAX_KEPT_RESULTS` 同值。
MAX_KEPT_RESULTS = 256


class BoundedResultStore(OrderedDict):
    """插入即封顶的 dict 子类：超过上限丢最旧的一条。"""

    def __init__(self, max_kept: int = MAX_KEPT_RESULTS) -> None:
        super().__init__()
        self.max_kept = max(1, int(max_kept))

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_kept:
            self.popitem(last=False)


__all__ = ["MAX_KEPT_RESULTS", "BoundedResultStore"]
