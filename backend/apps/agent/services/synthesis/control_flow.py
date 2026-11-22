"""综合链路里「失败不阻断」的宽口径 except 必须放行的异常。

综合链路有好几处"这一步失败了也别拖垮整份结论"的降级（前置评审、引用核验、写转录）。
它们用 ``except BaseException`` 兜住杂乱的失败面，但下面这几类**不是失败**，是控制流：

- ``asyncio.CancelledError``：用户点了取消 / 任务超时被截停。吞掉它等于取消无效——
  评审、综合、核验照样跑完、照样花钱；
- ``KeyboardInterrupt`` / ``SystemExit``：进程要退出；
- ``GeneratorExit``：生成器被关闭。

写法固定为先 ``except MUST_PROPAGATE: raise``，再 ``except BaseException``。
``tests/ci/structure/test_synthesis_cancellation_propagates.py`` 会逐个检查。
"""

from __future__ import annotations

import asyncio

MUST_PROPAGATE: tuple[type[BaseException], ...] = (
    asyncio.CancelledError,
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
)

__all__ = ["MUST_PROPAGATE"]
