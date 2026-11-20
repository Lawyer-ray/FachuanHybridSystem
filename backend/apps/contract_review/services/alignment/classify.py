"""三份 patch 按条款坐标对齐 → 互补 / 互斥 / 漏项。

## 判定顺序（硬）

| 情况 | 状态 | 产出 `PatchConflict` |
|:--|:--|:--|
| 不同条款各改各的；或同一条款内区间不交叠且改法相同 | ``complementary`` | 否 |
| 同一条款内区间相交、``replacement`` 不同 | ``overlap_diff`` | 是（互斥，律师裁决） |
| 同一条款内区间相交、``replacement`` 相同 | ``duplicate`` | 是（去重即可） |
| 清单里有这个条款，但三栏都没产出 patch | ``missing`` | 是（漏项） |
| **同一条款内区间不交叠、但三栏改法不同** | ``manual`` | 是（按 ``overlap_diff`` 交给律师，摘要写明待人工） |

最后一类是这张表里最容易被写错的：文本不冲突 **不等于** 法律效果不冲突。
一处把付款期限改成 10 天、另一处把同一份合同另一句的期限改成 15 天，字符区间
可以完全不相交，但两句话合起来是自相矛盾的。代码**没有能力**判断法律效果，
所以这里不许猜、也不许自动合并——只标 ``manual``，由律师确认。

对应地，``diff3`` 只处理文本区间；凡是它合并得了但可能法律互斥的，都停在
``manual`` 这一档。``manual`` 仍会包成 ``PatchConflict(kind="overlap_diff")``
送进冲突列表——契约只有三种 kind，不能因此让律师在 UI 上看不到这条待办；
摘要必须写明"待人工"，不允许写成"互斥"（代码并没有判定互斥）。

## 条款切不出来时

``clause_split`` 四级全不命中会标 ``aligned=False``。此时：

- 输出里的 ``clause_key`` 一律 ``None``（**不把行号伪装成条款坐标**）；
- 仍按**行**分组做区间冲突判断（同一行被两种改法命中仍然是真冲突）；
- 清单漏项无法按条款判定，写进 ``AlignmentReport.notes``，不伪造 missing。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from apps.contract_review.services.patch.conflict import patch_span, spans_overlap
from apps.contract_review.services.write_contracts import PatchConflict, WritePatch

from .clause_split import ClauseSpan, ClauseSplit, Granularity, split_clauses

#: 半开区间 ``[start, end)``（与 B1 的 ``patch_span`` 同口径）。
Span = tuple[int, int]

#: 对齐结论。``unlocated`` = 原文定位不到（应用阶段会单独报锚点缺失）。
OutcomeStatus = Literal["complementary", "overlap_diff", "duplicate", "missing", "manual", "unlocated"]

#: 需要律师动手的状态：互斥与"法律效果存疑"。
MANUAL_STATUSES: frozenset[str] = frozenset({"overlap_diff", "manual"})

#: 会变成 `PatchConflict` 的状态（契约只允许三种 kind；manual 按 overlap_diff 包装）。
_CONFLICT_STATUSES: frozenset[str] = frozenset({"overlap_diff", "duplicate", "missing", "manual"})

#: 粒度给律师看的中文名。
_UNIT_NAMES: dict[Granularity, str] = {
    "heading": "标题",
    "clause_number": "条款",
    "paragraph": "段落",
    "sentence": "句子",
    "line": "行",
}

#: 定位到的一段 patch：``(patch, 全文区间, 所属切分段)``。
LocatedPatch = tuple[WritePatch, Span, ClauseSpan | None]


@dataclass(frozen=True)
class ClauseOutcome:
    """一个条款（或切分段）的对齐结论。"""

    subpath: str
    #: 条款坐标；行级降级/跨段原文一律 ``None``。
    clause_key: str | None
    status: OutcomeStatus
    patch_ids: tuple[str, ...] = ()
    spans: tuple[Span, ...] = ()
    summary: str = ""

    @property
    def needs_manual(self) -> bool:
        return self.status in MANUAL_STATUSES


@dataclass(frozen=True)
class AlignmentReport:
    """一次三份 patch 对齐的完整结果。"""

    outcomes: tuple[ClauseOutcome, ...]
    conflicts: tuple[PatchConflict, ...]
    notes: tuple[str, ...] = ()

    def counts(self) -> dict[str, int]:
        """各状态计数；回归脚本的三类表直接取 ``complementary``/``overlap_diff``/``missing``。"""

        result: dict[str, int] = {}
        for outcome in self.outcomes:
            result[outcome.status] = result.get(outcome.status, 0) + 1
        return result


def classify_patches(
    patches: Sequence[WritePatch],
    texts: Mapping[str, str],
    checklist: Mapping[str, Sequence[str]] | None = None,
) -> AlignmentReport:
    """按 ``subpath`` + 条款坐标对齐 patch，返回结论与冲突列表。

    Args:
        patches: 三栏（或任意多栏）产出的候选改写。
        texts: ``subpath -> 全文``；缺某个 subpath 时该组 patch 全部记 ``unlocated``。
        checklist: ``subpath -> 条款 key 列表``（清单命中的条款）。key 必须与
            ``clause_split`` 切出来的 key 同拼写，否则会当成"文本中未找到"。

    Returns:
        确定性排序的报告；空 ``conflicts`` 表示没有互斥/重复/漏项。
    """

    grouped: dict[str, list[WritePatch]] = defaultdict(list)
    for patch in patches:
        grouped[patch.subpath].append(patch)
    checklists = {subpath: _dedupe(keys) for subpath, keys in (checklist or {}).items()}

    outcomes: list[ClauseOutcome] = []
    notes: list[str] = []
    for subpath in sorted(set(grouped) | set(checklists)):
        text = texts.get(subpath)
        if text is None:
            outcomes.extend(_missing_text_outcomes(subpath, grouped.get(subpath, ()), notes))
            continue
        split = split_clauses(text)
        located, unlocated = _locate(grouped.get(subpath, ()), text, split)
        for patch in unlocated:
            outcomes.append(
                ClauseOutcome(
                    subpath=subpath,
                    clause_key=None,
                    status="unlocated",
                    patch_ids=(patch.patch_id,),
                    summary=f"「{subpath}」中定位不到 patch 原文（应用阶段会报锚点缺失）",
                )
            )
        outcomes.extend(_classify_located(subpath, split, located))
        outcomes.extend(_missing_outcomes(subpath, split, checklists.get(subpath, ()), located, notes))

    outcomes.sort(key=_outcome_sort_key)
    conflicts = tuple(
        _conflict_of(outcome)
        for outcome in outcomes
        if outcome.status in _CONFLICT_STATUSES and (outcome.status != "manual" or len(outcome.patch_ids) >= 2)
    )
    return AlignmentReport(outcomes=tuple(outcomes), conflicts=conflicts, notes=tuple(notes))


def _locate(
    patches: Sequence[WritePatch], text: str, split: ClauseSplit
) -> tuple[list[LocatedPatch], list[WritePatch]]:
    located: list[LocatedPatch] = []
    unlocated: list[WritePatch] = []
    for patch in patches:
        span = patch_span(text, patch.original)
        if span is None:
            unlocated.append(patch)
            continue
        located.append((patch, span, _span_at(split, span)))
    return located, unlocated


def _span_at(split: ClauseSplit, span: Span) -> ClauseSpan | None:
    """包住 ``span`` 的切分段；跨段/越界返回 ``None``（不硬塞给最近的一段）。"""

    start, end = span
    for clause_span in split.spans:
        if clause_span.start <= start and end <= clause_span.end:
            return clause_span
    return None


def _classify_located(subpath: str, split: ClauseSplit, located: Sequence[LocatedPatch]) -> list[ClauseOutcome]:
    groups: dict[str, list[tuple[WritePatch, Span]]] = defaultdict(list)
    crossed: list[tuple[WritePatch, Span]] = []
    for patch, span, clause_span in located:
        if clause_span is None:
            crossed.append((patch, span))
        else:
            groups[clause_span.key].append((patch, span))

    outcomes: list[ClauseOutcome] = []
    for key, items in groups.items():
        clause_key = key if split.aligned else None
        outcomes.extend(_classify_group(subpath, clause_key, items, split.granularity))
    for patch, span in crossed:
        outcomes.append(
            ClauseOutcome(
                subpath=subpath,
                clause_key=None,
                status="manual",
                patch_ids=(patch.patch_id,),
                spans=(span,),
                summary=f"patch 原文跨{_UNIT_NAMES[split.granularity]}边界，无法归属单一坐标，待人工",
            )
        )
    return outcomes


def _classify_group(
    subpath: str,
    clause_key: str | None,
    items: Sequence[tuple[WritePatch, Span]],
    granularity: Granularity,
) -> list[ClauseOutcome]:
    label = _label(clause_key, granularity)
    if len(items) == 1:
        patch, span = items[0]
        return [
            ClauseOutcome(
                subpath=subpath,
                clause_key=clause_key,
                status="complementary",
                patch_ids=(patch.patch_id,),
                spans=(span,),
                summary=f"{label}只有一栏改写（互补）",
            )
        ]

    outcomes: list[ClauseOutcome] = []
    singles: list[tuple[WritePatch, Span]] = []
    for component in _overlap_components(items):
        if len(component) < 2:
            singles.extend(component)
            continue
        ordered = sorted(component, key=lambda item: (item[1], item[0].patch_id))
        patch_ids = tuple(patch.patch_id for patch, _span in ordered)
        spans = tuple(span for _patch, span in ordered)
        replacements = {patch.replacement for patch, _span in ordered}
        if len(replacements) == 1:
            outcomes.append(
                ClauseOutcome(
                    subpath=subpath,
                    clause_key=clause_key,
                    status="duplicate",
                    patch_ids=patch_ids,
                    spans=spans,
                    summary=f"{label}有 {len(ordered)} 份完全相同的改写，可直接去重",
                )
            )
        else:
            outcomes.append(
                ClauseOutcome(
                    subpath=subpath,
                    clause_key=clause_key,
                    status="overlap_diff",
                    patch_ids=patch_ids,
                    spans=spans,
                    summary=f"{label}有 {len(ordered)} 份改写落在同一段原文上（互斥，需律师裁决）",
                )
            )

    if singles:
        ordered = sorted(singles, key=lambda item: (item[1], item[0].patch_id))
        patch_ids = tuple(patch.patch_id for patch, _span in ordered)
        spans = tuple(span for _patch, span in ordered)
        replacements = {patch.replacement for patch, _span in ordered}
        if len(replacements) > 1:
            outcomes.append(
                ClauseOutcome(
                    subpath=subpath,
                    clause_key=clause_key,
                    status="manual",
                    patch_ids=patch_ids,
                    spans=spans,
                    summary=(f"{label}内有 {len(ordered)} 处互不交叠的改写，但法律效果是否互斥无法由代码判断，待人工"),
                )
            )
        else:
            outcomes.append(
                ClauseOutcome(
                    subpath=subpath,
                    clause_key=clause_key,
                    status="complementary",
                    patch_ids=patch_ids,
                    spans=spans,
                    summary=f"{label}内多处改写区间不交叠且改法相同（互补）",
                )
            )
    return outcomes


def _overlap_components(items: Sequence[tuple[WritePatch, Span]]) -> list[list[tuple[WritePatch, Span]]]:
    """区间相交的连通分量；三份两两相交是一次冲突，不是两条。"""

    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            if spans_overlap(items[left][1], items[right][1]):
                root_left, root_right = find(left), find(right)
                if root_left != root_right:
                    parent[root_right] = root_left

    components: dict[int, list[tuple[WritePatch, Span]]] = defaultdict(list)
    for index, item in enumerate(items):
        components[find(index)].append(item)
    return [sorted(members, key=lambda item: (item[1], item[0].patch_id)) for members in components.values()]


def _missing_outcomes(
    subpath: str,
    split: ClauseSplit,
    checklist: Sequence[str],
    located: Sequence[LocatedPatch],
    notes: list[str],
) -> list[ClauseOutcome]:
    if not checklist:
        return []
    if not split.aligned:
        notes.append(f"「{subpath}」切分降级到行级，清单漏项无法按条款判定")
        return []

    patched_keys = {clause_span.key for _patch, _span, clause_span in located if clause_span is not None}
    split_keys = {span.key for span in split.spans}
    outcomes: list[ClauseOutcome] = []
    for key in checklist:
        if key in patched_keys:
            continue
        if key in split_keys:
            summary = f"「{key}」在清单中命中，但三栏都没有产出 patch（漏项）"
        else:
            summary = f"清单条款「{key}」在文本中未找到，且没有 patch（漏项）"
        outcomes.append(
            ClauseOutcome(
                subpath=subpath,
                clause_key=key,
                status="missing",
                summary=summary,
            )
        )
    return outcomes


def _missing_text_outcomes(subpath: str, patches: Sequence[WritePatch], notes: list[str]) -> list[ClauseOutcome]:
    notes.append(f"「{subpath}」全文缺失，条款切分与清单漏项都无法判定")
    return [
        ClauseOutcome(
            subpath=subpath,
            clause_key=None,
            status="unlocated",
            patch_ids=(patch.patch_id,),
            summary=f"「{subpath}」全文缺失，无法定位 patch 原文",
        )
        for patch in patches
    ]


def _conflict_of(outcome: ClauseOutcome) -> PatchConflict:
    # ``manual`` 没有独立 kind：用 ``overlap_diff`` 送进律师待办，摘要写明"待人工"。
    raw_kind = "overlap_diff" if outcome.status == "manual" else outcome.status
    kind = cast(Literal["overlap_diff", "duplicate", "missing"], raw_kind)
    return PatchConflict(
        subpath=outcome.subpath,
        clause_key=outcome.clause_key,
        kind=kind,
        patch_ids=outcome.patch_ids,
        spans=outcome.spans,
        summary=outcome.summary,
    )


def _label(clause_key: str | None, granularity: Granularity) -> str:
    if clause_key is not None:
        return f"「{clause_key}」"
    return f"（{_UNIT_NAMES[granularity]}级坐标未知）"


def _outcome_sort_key(outcome: ClauseOutcome) -> tuple[str, int, str, str, tuple[str, ...]]:
    first_start = min((span[0] for span in outcome.spans), default=-1)
    return (outcome.subpath, first_start, outcome.clause_key or "", outcome.status, outcome.patch_ids)


def _dedupe(keys: Sequence[str]) -> tuple[str, ...]:
    """保序去重（清单里同一 key 出现两次不该算两条漏项）。"""

    return tuple(dict.fromkeys(key for key in keys if key))


__all__ = ["AlignmentReport", "ClauseOutcome", "MANUAL_STATUSES", "OutcomeStatus", "classify_patches"]
