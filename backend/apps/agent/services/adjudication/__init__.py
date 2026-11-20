"""多答裁决的**跨 lane 契约**包（父会话独占，其它 lane 只读）。

本包只放类型与常量，**不放任何实现**。理由：

- 多 agent 并行施工时，最贵的失败不是写错逻辑，而是同一个概念被几家各写一个形状
  （``score`` 一家用 int 一家用 float、``criteria_met`` 一家用 ``"yes"`` 一家用 ``True``），
  集成时才发现对不上，得把三份都改一遍。
- 所以形状先在这里冻结，各 lane 只允许 import，不允许改签名。要改 → 停下向父会话提
  「契约变更请求」，由父会话改本文件并通知全体。

设计与来源见 ``docs/04-计划/活跃/adjudication-agent-assignments.md`` 附录 A。
"""

from .contracts import (
    CRITERIA_UNSCORED_REASONS,
    REVIEW_STAGES,
    CriteriaVerdict,
    EquivalenceCluster,
    FusedHit,
    LaneReview,
    Review,
)

__all__ = [
    "CRITERIA_UNSCORED_REASONS",
    "REVIEW_STAGES",
    "CriteriaVerdict",
    "EquivalenceCluster",
    "FusedHit",
    "LaneReview",
    "Review",
]
