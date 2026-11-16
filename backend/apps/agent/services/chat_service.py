"""兼容门面 —— 原 chat_service.py 已拆为 services/chat/ 子包。

实现迁至 ``chat/{pool,env,persist,stream,live_control}.py``；本模块仅转发
chat 包重导出的全部公开符号，使 ``from apps.agent.services.chat_service import X``
与 ``import apps.agent.services.chat_service as m; m.X`` 保持不变
（API / task_runner / subtask_runner / 测试仍按原路径取符号）。

注意：``_pool`` / ``_pool_lock`` 是 ``chat.pool`` 的模块级可变全局，经门面
重导出只是导入时的快照绑定——要重置进程池须直接改
``apps.agent.services.chat.pool._pool``（见测试桩清单）。
"""

from __future__ import annotations

from .chat import *  # noqa: F403
from .chat import __all__ as __all__
