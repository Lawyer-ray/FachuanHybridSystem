"""chat 子系统的**唯一**配置源（F8，2026-11-23 二轮审计）。

历史坑：同一个环境变量 `FACHUAN_AGENT_POOL_SIZE` 的解析曾在 `budget.py`（写字面量
`4`/`32`）和 `pool.py`（用常量）各写一份，栏数上限也有 `multi.MAX_ANSWERS` 与
`aggregate.MAX_CANDIDATES` 两份，值恰好相同、靠人肉同步——改一处就静默分叉，
`budget` 与 `pool` 会算出不同槽位数，调度错位且没有任何报错。

所有需要这些数值的模块一律 `from .config import ...`，不得再写第二份。
"""

from __future__ import annotations

import os

#: 进程池默认/上限（`FACHUAN_AGENT_POOL_SIZE`）。
DEFAULT_POOL_SIZE = 4
MAX_POOL_SIZE = 32

#: 多栏并答的栏数上限（成本线性增长，五栏并排在 UI 上已接近可读性极限）。
MAX_ANSWERS = 5


def resolve_pool_size() -> int:
    """解析进程池大小：环境变量 → 默认值，并夹在 [1, MAX_POOL_SIZE]。"""
    try:
        raw = os.environ.get("FACHUAN_AGENT_POOL_SIZE", "")
        size = int(raw) if raw.strip() else DEFAULT_POOL_SIZE
    except ValueError:
        size = DEFAULT_POOL_SIZE
    return max(1, min(size, MAX_POOL_SIZE))


__all__ = ["DEFAULT_POOL_SIZE", "MAX_ANSWERS", "MAX_POOL_SIZE", "resolve_pool_size"]
