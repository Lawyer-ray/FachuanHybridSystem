"""综合结论（B3）：把一轮多答收敛成一份可引用的合成稿。

- ``pipeline.py``：完整流水线——(可选)评审 → 组 prompt → 跑 agent → 核验引用 → 落库；
- ``jobs.py``：后台任务（幂等提交、心跳、取消、worker 入口），API 只提交与轮询；
- ``agent_runner.py``：交给指定 agent 运行时生成正文；
- ``verify.py``：威科核验，填 ``Synthesis.unverified``；
- ``store.py``：本轮候选与模型名的读取、``AgentSynthesis`` 快照与转录消息的落库与回放
  （API 层不碰 ORM）；
- ``control_flow.py``：「失败不阻断」的宽口径 except 必须放行的异常（取消等）。

prompt 装配用到的候选渲染与丢弃口径在 ``services/chat/aggregate.py``。
"""

from __future__ import annotations
