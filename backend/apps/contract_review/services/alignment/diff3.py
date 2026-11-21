"""自研三方合并（BASE / OURS / THEIRS），**只判文本区间冲突**。

## 为什么不用 merge3 / dulwich

两者都是 GPL（或 GPL 委托）授权，本项目不能引入；而且这里要的不是"能跑"，
是"冲突区间可解释"：律师看到的每一条 ``overlap_diff`` 都要能对回原文坐标。
所以按 diff3 的语义自己写，只依赖标准库 ``difflib``。

## 算法（约 80 行）

1. 用 ``SequenceMatcher.get_matching_blocks`` 求 BASE↔OURS、BASE↔THEIRS 的
   匹配块；
2. 在 **BASE 坐标**上取两组匹配块的交集，得到两边都原样保留的 *sync region*；
3. sync region 之间的 gap 四分类：

   | 条件 | 类别 |
   |:--|:--|
   | 两侧都与 BASE 相同 | ``same`` |
   | 只有 OURS 改 | ``a`` |
   | 只有 THEIRS 改 | ``b`` |
   | 两侧改动区间相交且不同 | ``conflict`` |

4. gap 里两侧都有改动时，再看各自相对 BASE 的 opcode 区间：**不相交（含相邻）
   就分别合并**。这一层是"相邻修改不误判冲突"的关键——只看 sync region 时，
   「OURS 改 c、THEIRS 改 d」会掉进同一个 gap，但两处改动在 BASE 坐标上并不
   重叠，硬判冲突会让律师白看一条。

## 边界（必须写在这里，否则下一个人一定会踩）

diff3 **只处理文本区间**。两句话文字不冲突、法律效果互斥（例如一处把付款期限
改成 10 天、另一处改成 15 天），这里看不出来，也**不许猜哪句更强**；这种情形
由 ``classify`` 标成待人工（``overlap_diff``/``manual``），交给律师裁决。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

#: gap 三分类 + 未改动。
MergeKind = Literal["same", "a", "b", "conflict"]

#: BASE 坐标上的冲突区间 ``[start, end)``；纯插入冲突时 ``start == end``。
ConflictSpan = tuple[int, int]

#: ``(base_start, base_end)``；``base_start == base_end`` 表示纯插入。
Edit = tuple[int, int, str]

#: ``(base_start, base_end, ours_start, ours_end, theirs_start, theirs_end)``。
SyncRegion = tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class MergeHunk:
    """一段合并结果。``base_*`` 是 BASE 坐标，另外两侧是对应文本。"""

    kind: MergeKind
    base_start: int
    base_end: int
    base_text: str
    ours_text: str
    theirs_text: str


@dataclass(frozen=True)
class MergeResult:
    hunks: tuple[MergeHunk, ...]
    conflicts: tuple[ConflictSpan, ...]
    #: ``None`` = 有冲突，不产出合并稿（不许悄悄挑一边）。
    merged_text: str | None

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def diff3(base: str, ours: str, theirs: str) -> MergeResult:
    """三方合并；``merged_text`` 仅在无冲突时非 ``None``。"""

    hunks = tuple(_merge_region(base, ours, theirs, base_offset=0))
    conflicts = tuple((hunk.base_start, hunk.base_end) for hunk in hunks if hunk.kind == "conflict")
    merged_text = None if conflicts else "".join(_chosen_text(hunk) for hunk in hunks)
    return MergeResult(hunks=hunks, conflicts=conflicts, merged_text=merged_text)


def _merge_region(base: str, ours: str, theirs: str, base_offset: int) -> list[MergeHunk]:
    """一个区域：先取 sync region，再逐 gap 分类。"""

    syncs = _sync_regions(base, ours, theirs)
    if not syncs:
        return _classify_whole(base, ours, theirs, base_offset)

    hunks: list[MergeHunk] = []
    base_pos = ours_pos = theirs_pos = 0
    for b_start, b_end, o_start, o_end, t_start, t_end in syncs:
        if b_start > base_pos or o_start > ours_pos or t_start > theirs_pos:
            hunks.extend(
                _classify_gap(
                    base[base_pos:b_start],
                    ours[ours_pos:o_start],
                    theirs[theirs_pos:t_start],
                    base_offset + base_pos,
                )
            )
        hunks.append(
            MergeHunk(
                kind="same",
                base_start=base_offset + b_start,
                base_end=base_offset + b_end,
                base_text=base[b_start:b_end],
                ours_text=ours[o_start:o_end],
                theirs_text=theirs[t_start:t_end],
            )
        )
        base_pos, ours_pos, theirs_pos = b_end, o_end, t_end

    if base_pos < len(base) or ours_pos < len(ours) or theirs_pos < len(theirs):
        hunks.extend(_classify_gap(base[base_pos:], ours[ours_pos:], theirs[theirs_pos:], base_offset + base_pos))
    return hunks


def _sync_regions(base: str, ours: str, theirs: str) -> list[SyncRegion]:
    """BASE 坐标上两组匹配块的**交集**（两边都原样保留的区间）。"""

    regions: list[SyncRegion] = []
    for b_start, o_start, size in _matching_blocks(base, ours):
        for b2_start, t_start, size2 in _matching_blocks(base, theirs):
            start = max(b_start, b2_start)
            end = min(b_start + size, b2_start + size2)
            if start >= end:
                continue
            regions.append(
                (
                    start,
                    end,
                    o_start + (start - b_start),
                    o_start + (end - b_start),
                    t_start + (start - b2_start),
                    t_start + (end - b2_start),
                )
            )

    regions.sort()
    merged: list[SyncRegion] = []
    for region in regions:
        if not merged:
            merged.append(region)
            continue
        prev = merged[-1]
        if region[0] > prev[1] or (region[0] == prev[1] and region[2] != prev[3]):
            merged.append(region)
            continue
        if region[0] == prev[1] and region[4] != prev[5]:
            merged.append(region)
            continue
        new_end = max(prev[1], region[1])
        if new_end > prev[1]:
            delta = new_end - prev[1]
            merged[-1] = (prev[0], new_end, prev[2], prev[3] + delta, prev[4], prev[5] + delta)
        # 被 prev 完全包含的区间不扩展（prev 已经覆盖它）
    return merged


def _matching_blocks(left: str, right: str) -> list[tuple[int, int, int]]:
    matcher = SequenceMatcher(a=left, b=right, autojunk=False)
    return [(block.a, block.b, block.size) for block in matcher.get_matching_blocks() if block.size]


def _classify_whole(base: str, ours: str, theirs: str, offset: int) -> list[MergeHunk]:
    """没有 sync region：能判的只有"谁没改/两边改成一样"，否则就是冲突。"""

    if ours == base and theirs == base:
        return [_hunk("same", base, ours, theirs, offset)]
    if ours == base:
        return [_hunk("b", base, ours, theirs, offset)]
    if theirs == base:
        return [_hunk("a", base, ours, theirs, offset)]
    if ours == theirs:
        return [_hunk("same", base, ours, theirs, offset)]
    return [_hunk("conflict", base, ours, theirs, offset)]


def _classify_gap(base: str, ours: str, theirs: str, offset: int) -> list[MergeHunk]:
    """gap 四分类；两侧都改时用 opcode 区间判断能否各改各的。"""

    if not base and not ours and not theirs:
        return []
    if ours == base and theirs == base:
        return [_hunk("same", base, ours, theirs, offset)]
    if ours == base:
        return [_hunk("b", base, ours, theirs, offset)]
    if theirs == base:
        return [_hunk("a", base, ours, theirs, offset)]
    if ours == theirs:
        return [_hunk("same", base, ours, theirs, offset)]

    merged = _merge_disjoint_edits(base, ours, theirs, offset)
    if merged is not None:
        return merged
    return [_hunk("conflict", base, ours, theirs, offset)]


def _merge_disjoint_edits(base: str, ours: str, theirs: str, offset: int) -> list[MergeHunk] | None:
    """两侧改动在 BASE 坐标上不相交 → 分别落成 ``a``/``b``；相交则返回 ``None``。"""

    our_edits = _edits(base, ours)
    their_edits = _edits(base, theirs)
    if _edits_conflict(our_edits, their_edits):
        return None

    by_start: dict[int, dict[str, list[Edit]]] = defaultdict(lambda: {"ours": [], "theirs": []})
    for edit in our_edits:
        by_start[edit[0]]["ours"].append(edit)
    for edit in their_edits:
        by_start[edit[0]]["theirs"].append(edit)

    hunks: list[MergeHunk] = []
    position = 0
    for start in sorted(by_start):
        if start < position:  # 同侧 opcode 不应重叠；真出现就按冲突处理
            return None
        if start > position:
            hunks.append(
                _hunk("same", base[position:start], base[position:start], base[position:start], offset + position)
            )
            position = start

        group = by_start[start]
        ours_insert = "".join(edit[2] for edit in group["ours"] if edit[0] == edit[1])
        theirs_insert = "".join(edit[2] for edit in group["theirs"] if edit[0] == edit[1])
        if ours_insert or theirs_insert:
            # 三个分支穷尽了 "两串相等 / 只有甲有 / 只有乙有"：
            # 走到 else 意味着两串都为空，而外层 if 已保证至少一个非空，
            # 所以不必再写 `else: return None`（CodeQL 会把它标成不可达）。
            kind: MergeKind = "same" if ours_insert == theirs_insert else ("a" if ours_insert else "b")
            hunks.append(
                MergeHunk(
                    kind=kind,
                    base_start=offset + position,
                    base_end=offset + position,
                    base_text="",
                    ours_text=ours_insert,
                    theirs_text=theirs_insert,
                )
            )

        ours_replace = [edit for edit in group["ours"] if edit[0] != edit[1]]
        theirs_replace = [edit for edit in group["theirs"] if edit[0] != edit[1]]
        if len(ours_replace) > 1 or len(theirs_replace) > 1:  # 同起点多个替换：按冲突处理
            return None
        if ours_replace and theirs_replace:
            if ours_replace[0] != theirs_replace[0]:
                return None
            edit = ours_replace[0]
            hunks.append(_hunk("same", base[edit[0] : edit[1]], edit[2], edit[2], offset + edit[0]))
            position = edit[1]
        elif ours_replace:
            edit = ours_replace[0]
            hunks.append(_hunk("a", base[edit[0] : edit[1]], edit[2], base[edit[0] : edit[1]], offset + edit[0]))
            position = edit[1]
        elif theirs_replace:
            edit = theirs_replace[0]
            hunks.append(_hunk("b", base[edit[0] : edit[1]], base[edit[0] : edit[1]], edit[2], offset + edit[0]))
            position = edit[1]

    if position < len(base):
        hunks.append(_hunk("same", base[position:], base[position:], base[position:], offset + position))
    return hunks


def _edits(base: str, other: str) -> list[Edit]:
    """``other`` 相对 ``base`` 的非 equal opcode：``(base_start, base_end, replacement)``。"""

    edits: list[Edit] = []
    matcher = SequenceMatcher(a=base, b=other, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits.append((i1, i2, other[j1:j2]))
    return edits


def _edits_conflict(our_edits: list[Edit], their_edits: list[Edit]) -> bool:
    """两侧改动区间相交且内容不同 → 冲突；同一位置的不同插入也算冲突。"""

    for a_start, a_end, a_text in our_edits:
        for b_start, b_end, b_text in their_edits:
            if a_start < b_end and b_start < a_end:
                if (a_start, a_end, a_text) != (b_start, b_end, b_text):
                    return True
                continue
            if a_start == a_end == b_start == b_end and a_text != b_text:
                return True
    return False


def _hunk(kind: MergeKind, base: str, ours: str, theirs: str, offset: int) -> MergeHunk:
    return MergeHunk(
        kind=kind,
        base_start=offset,
        base_end=offset + len(base),
        base_text=base,
        ours_text=ours,
        theirs_text=theirs,
    )


def _chosen_text(hunk: MergeHunk) -> str:
    return hunk.theirs_text if hunk.kind == "b" else hunk.ours_text


__all__ = ["ConflictSpan", "MergeHunk", "MergeKind", "MergeResult", "diff3"]
