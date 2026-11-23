"""agent 执行位预算：按「用途」分档，而不是所有请求抢同一个池。

## 为什么需要这个模块

现有的 `PiProcessPool` 只有一个全局信号量（`DEFAULT_POOL_SIZE = 4`）。当同一
会话要跑两个 agent 对比、或主答之外再挂一个审校时，这些运行会与**其他律师的
正常提问**抢同一批执行位——别人什么都没做错却要排队，甚至拿到
`agent 执行位已满` 的报错。

单人自测永远发现不了这件事（自己不会跟自己抢），但一上生产就是「开了对比功能
之后大家都变慢」。

## 设计：按角色分档，主答永不被抢占

```
全机执行位总量 (= FACHUAN_AGENT_POOL_SIZE)
├── primary  主答          —— 保证配额，任何情况下不被辅助用途抢占
└── aux      对比 / 审校   —— 可降级：满了就提示「本轮未做对比」，不阻塞主答
```

关键取舍：**aux 不是独立池，而是从总量里切出来的一块**。不做成「每用途一个
进程池」的原因——

- 独立池会让总进程数失控（N 个用途 × 各自的 size）；
- 配额要能随负载调整，而不是编译期写死。

因此本模块只做「准入判定」，不持有进程。真正的进程仍由 `PiProcessPool` 造，
只是「谁可以进去」由这里决定。

## 降级语义（这是本模块存在的真正价值）

| 用途 | 配额满时的行为 |
|:--|:--|
| `primary` | 排队等待（沿用原有 `queue_timeout` 语义），**不拒绝** |
| `aux` | **立即拒绝**，由调用方降级为「只跑主答」并提示用户 |

aux 立即拒绝而不是排队：对比/审校是增强能力，让它排队只会把用户拖住；
直接失败、前端显示「未做对比」远比「卡 60 秒然后超时」体验好。

## 与 Redis 的关系

本模块是**进程内**的准入计数，**不跨进程**。跨进程的总量控制仍由
`PiProcessPool._slot()` 里的 Redis 信号量负责。

这样分层的原因：跨进程一致性的粒度应该是「全机还能开几个进程」（由 pool 管），
而「这一次要不要跑辅助 agent」是单次请求内的决策，进程内计数足够且零开销。
两层叠加后：aux 先被本地配额挡住，挡不住的再进 pool 的全局信号量。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

logger = logging.getLogger(__name__)

#: 用途枚举
Purpose = Literal["primary", "aux"]

#: aux 默认可用的执行位比例（相对总量）。默认 1/4——
#: 总量 4 时 aux 只有 1 席，意味着「同一时刻只做一份对比/审校」。
#: 这个保守取值的原因：对比功能刚上线时不知道真实负载，宁可先紧后松。
DEFAULT_AUX_RATIO = 0.25

#: 环境变量覆盖要点：
#: - FACHUAN_AGENT_AUX_SLOTS 直接指定 aux 席位数（优先于比例）
#: - FACHUAN_AGENT_AUX_RATIO 按比例算（0 表示禁用 aux，所有对比请求降级）
_AUX_SLOTS_ENV = "FACHUAN_AGENT_AUX_SLOTS"
_AUX_RATIO_ENV = "FACHUAN_AGENT_AUX_RATIO"


def _total_slots() -> int:
    """全机执行位总量。

    F8（2026-11-23 二轮审计）：这里原先独立实现了 `FACHUAN_AGENT_POOL_SIZE` 的解析
    （字面量 4/32），与 `pool._resolve_pool_size` 是两份代码，改一处就静默分叉。
    现在统一走 `chat/config.resolve_pool_size` 单源。
    """
    from .config import resolve_pool_size

    return resolve_pool_size()


def aux_slots(total: int | None = None) -> int:
    """aux 可用席位数。0 表示对比/审校能力关闭（所有 aux 请求降级）。"""
    total = _total_slots() if total is None else total

    raw_slots = os.environ.get(_AUX_SLOTS_ENV, "").strip()
    if raw_slots:
        try:
            return max(0, min(int(raw_slots), total))
        except ValueError:
            logger.warning("%s 不是整数，回退按比例计算", _AUX_SLOTS_ENV)

    raw_ratio = os.environ.get(_AUX_RATIO_ENV, "").strip()
    ratio = DEFAULT_AUX_RATIO
    if raw_ratio:
        try:
            ratio = float(raw_ratio)
        except ValueError:
            logger.warning("%s 不是数字，用默认比例 %s", _AUX_RATIO_ENV, DEFAULT_AUX_RATIO)

    if ratio <= 0:
        return 0
    # 向下取整但至少留 1 席（除总量为 1 的情况：那时 aux 不给席位，
    # 否则唯一的执行位会被辅助用途吃掉，主答反而排队）
    if total <= 1:
        return 0
    return max(1, min(int(total * ratio), total - 1))


class _Budget:
    """进程内准入计数。每次 acquire 前 +1，退出时 -1。"""

    def __init__(self) -> None:
        self._aux_in_use = 0

    @property
    def aux_in_use(self) -> int:
        return self._aux_in_use

    def reset(self) -> None:
        """清空计数。仅供测试使用。"""
        self._aux_in_use = 0


_budget = _Budget()


class BudgetExceeded(RuntimeError):
    """辅助用途配额已满。调用方应降级为「只跑主答」而不是报错给用户。"""


@asynccontextmanager
async def reserve(purpose: Purpose = "primary") -> AsyncIterator[None]:
    """申请一个执行位。

    - `primary`：不做本地限制，直接放行（真正的并发控制交给 pool 的信号量）。
    - `aux`：先看 aux 席位是否还有空位，没有就立刻抛 `BudgetExceeded`。

    为什么 primary 完全不做本地计数：主答是产品的主路径，任何本地限流都可能
    把正常提问挡掉。它的并发语义应该与引入本模块之前**完全一致**——这是
    「本模块对现有行为零影响」的保证。
    """
    if purpose == "primary":
        yield
        return

    limit = aux_slots()
    if limit <= 0:
        raise BudgetExceeded("对比/审校能力已关闭（aux 席位为 0）")

    if _budget.aux_in_use >= limit:
        raise BudgetExceeded(f"辅助 agent 并发已满（{_budget.aux_in_use}/{limit}）")

    _budget._aux_in_use += 1
    try:
        yield
    finally:
        _budget._aux_in_use -= 1


def snapshot() -> dict[str, int]:
    """当前配额快照（供诊断接口与测试使用）。"""
    total = _total_slots()
    limit = aux_slots(total)
    return {
        "total_slots": total,
        "aux_slots": limit,
        "aux_in_use": _budget.aux_in_use,
        "primary_slots": total - limit,
    }
