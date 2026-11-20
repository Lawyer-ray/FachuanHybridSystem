"""合同写入侧的契约类型（本文件冻结，父会话独占）。

三栏并答改同一份 docx 时，**任何一栏都不许直接落盘**。落盘的单位是这里定义的
``WritePatch``：一组"把这段原文换成那段"的候选改动。理由不是洁癖：

- ``rewrite_folder_file`` 要求 ``original`` 与文档**逐字一致**。第一栏写完之后，
  第二栏手里的 ``original`` 就已经失效——它会失败（看起来像模型笨），或者更糟：
  在别处撞上同一串字，改错位置。
- 三套 ``<w:ins>/<w:del>`` 叠在同一段上，Word 的"审阅"里就是一团乱麻，律师没法
  逐条接受/拒绝，等于把文件改坏了却看不出来。

所以流程改成：三栏各出 patch → 冲突检测 → 律师裁决 → **单点应用一次**。
``Decision`` 记录"采纳了谁、依据是什么"，它同时是律所要求的留痕与后续模型选型的
数据源。

硬规则：lane 只读本文件；字段增删改名必须与计划文档附录 A 和前端类型同一次对齐。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

#: patch 生命周期。``proposed`` 之后只能走 ``conflict`` / ``merged`` / ``rejected``，
#: ``applied`` 是终态（已经写进文档）。
PATCH_STATUSES: frozenset[str] = frozenset({"proposed", "conflict", "merged", "applied", "rejected"})

#: 冲突种类。``overlap_diff`` = 同一段原文被两种改法命中（互斥，必须人裁决）；
#: ``duplicate`` = 改法完全相同（去重即可）；``missing`` = 清单命中但三栏都没改（漏改）。
CONFLICT_KINDS: frozenset[str] = frozenset({"overlap_diff", "duplicate", "missing"})


@dataclass(frozen=True)
class WritePatch:
    """一栏提出的一处改写（**不落盘**）。"""

    patch_id: str
    session_id: str
    turn: int
    #: 产出它的后端（pi / dsh / openai-agents）；单栏时也记，便于回溯。
    agent_kind: str
    run_id: str
    owner_kind: Literal["contract", "case"]
    owner_id: int
    #: 绑定根下的 posix 相对路径（与 ``rewrite_folder_file`` 的 subpath 同口径）。
    subpath: str
    #: 逐字原文。定位与合并都靠它，**不许做任何归一化**（全角/空白差异只会导致误匹配）。
    original: str
    replacement: str
    #: 产出时文件的 mtime。应用前二次校验：律师在这期间动过文件就必须报冲突，
    #: 而不是把 patch 硬写到一个已经变了的文档上。
    base_mtime: float | None = None
    status: Literal["proposed", "conflict", "merged", "applied", "rejected"] = "proposed"
    created_at: datetime | None = None


@dataclass(frozen=True)
class PatchConflict:
    """一处冲突（同一 subpath 内的若干 patch）。"""

    subpath: str
    #: 条款坐标；B1 阶段没有条款切分，一律 ``None``（B4 才有）。
    clause_key: str | None
    kind: Literal["overlap_diff", "duplicate", "missing"]
    patch_ids: tuple[str, ...] = field(default_factory=tuple)
    #: 各 patch 的 ``original`` 在该 subpath 全文中的区间 ``(start, end)``。
    spans: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    #: 给律师看的一句话（"第 7.2 条有两种改法，A 主张…，B 主张…"）。
    summary: str = ""


@dataclass(frozen=True)
class Decision:
    """一次裁决（留痕主体）。

    ``dissent`` 保留但不展示：它是"三份里被否掉的意见"，将来做模型评估时比分数更值钱
    （能回答"这家在哪些条款上总是与最终稿不同"）。
    """

    decision_id: str
    session_id: str
    owner_kind: Literal["contract", "case"]
    owner_id: int
    subpath: str
    clause_key: str | None
    #: 采纳的 patch；律师自己改写时为空，改看 ``manual_text``。
    chosen_patch_id: str | None = None
    manual_text: str | None = None
    #: ``{"citations": [...], "rubric_ids": [...]}``——依据必须可回溯到材料与判定项。
    basis: dict = field(default_factory=dict)
    decided_by: int | None = None
    reason: str = ""
    dissent: tuple[dict, ...] = field(default_factory=tuple)
    decided_at: datetime | None = None
