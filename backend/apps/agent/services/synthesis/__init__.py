"""综合结论（B3）：MoA aggregator 的读候选、解析模型、落快照。

- ``store.py``：本轮各栏正文与模型名的读取、合成模型解析、``AgentSynthesis``
  的落库与回放（API 层不碰 ORM）；
- aggregator 本体（prompt 装配 / 一次调用 / 引用锚点）在
  ``services/chat/aggregate.py``。

本包只产出结论快照，**不**写 assistant 消息：转录里的 assistant 消息等于"某一栏
的回答"，凭空多一条会让律师以为多跑了一个 agent（见 ``models/synthesis.py``）。
"""

from __future__ import annotations
