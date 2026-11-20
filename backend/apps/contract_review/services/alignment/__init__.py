"""B4 对齐与合并：条款切分 → 三方合并 → 冲突分类 → 裁决留痕。

四个文件各有唯一职责，别互相塞：

- ``clause_split``：纯文本切分（四级降级；切不出来就诚实标行级）；
- ``diff3``：纯文本三方合并（只判区间冲突，不猜法律效果）；
- ``classify``：按条款坐标把多栏 patch 分成互补/互斥/漏项/待人工；
- ``decision``：`Decision` 落库与回读（append-only，dissent 保留不展示）。

``decision`` 依赖 Django 模型，其余三个不碰数据库；回归脚本只 ``django.setup()``
（不连库）跑切分与分类，所以**不要**把 Django import 塞进 ``clause_split``/``diff3``。
"""

from __future__ import annotations

from .classify import AlignmentReport, ClauseOutcome, classify_patches
from .clause_split import ClauseSpan, ClauseSplit, Granularity, split_clauses
from .decision import load_decision, new_decision_id, record_decision, to_decision
from .diff3 import MergeHunk, MergeResult, diff3
from .models import ContractDecision, DecisionOwnerKind

__all__ = [
    "AlignmentReport",
    "ClauseOutcome",
    "ClauseSpan",
    "ClauseSplit",
    "ContractDecision",
    "DecisionOwnerKind",
    "Granularity",
    "MergeHunk",
    "MergeResult",
    "classify_patches",
    "diff3",
    "load_decision",
    "new_decision_id",
    "record_decision",
    "split_clauses",
    "to_decision",
]
