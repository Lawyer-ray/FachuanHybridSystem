"""同一 subpath 内多份 patch 的冲突分类（B1 的判据只有"改到同一段"）。

## 三类，判定顺序是硬的

| 情况 | 结论 | 后果 |
|:--|:--|:--|
| `original` 区间不相交 | 互补 | 可以一次性合并应用（各改各的） |
| 相交且 `replacement` **相同** | `duplicate` | 去重即可，不需要律师裁决 |
| 相交且 `replacement` 不同 | `overlap_diff` | **互斥**，必须律师裁决；不许自动挑一个 |

## 为什么区间要落在"subpath 全文"上

只看 `original` 字符串是否相等，会把"两份 patch 改的是同一段"漏成"两份都改了
文件"——例如 A 的 `original` 是"乙方应于三十日内付款"，B 的是"于三十日内付款"，
字符串不相等却**互相包含**，落笔时后一个必然踩坏前一个。只有把 `original`
放回全文算出区间、再判区间是否相交，才抓得住这种包含关系。

B1 阶段没有条款切分（`clause_key` 一律 `None`，见冻结契约 `PatchConflict`），
所以"同一段"只能按字符区间近似——这对"同一份 docx 被三栏同时改"这个场景足够：
真正危险的是**同一处原文被两种改法命中**，那正是区间相交。

## 同一段原文在全文里出现多次

取**首次出现**。合同里同一句话重复出现极少，重复时也应该由律师把 `original`
拉长到唯一（与 `direct_edit_service.locate_paragraph` 同口径）。代价写在这里而
不是藏起来：真出现重复时，两份改不同位置的 patch 会被判成"相交"，需要律师
多看一眼；反过来（按"最后一次出现"或随机匹配）会静默改错位置。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Literal

from apps.contract_review.services.write_contracts import PatchConflict, WritePatch

#: 区间用半开区间 ``[start, end)``：相邻两段（A 的结尾正好是 B 的开头）不算相交。
Span = tuple[int, int]


def patch_span(text: str, original: str) -> Span | None:
    """`original` 在 subpath 全文中的区间（首次出现；找不到返回 ``None``）。"""
    if not original:
        return None
    start = text.find(original)
    if start < 0:
        return None
    return start, start + len(original)


def spans_overlap(left: Span, right: Span) -> bool:
    """两个半开区间是否相交（相接不算）。"""
    return left[0] < right[1] and right[0] < left[1]


def detect_conflicts(
    patches: Sequence[WritePatch],
    texts: Mapping[str, str],
) -> list[PatchConflict]:
    """按 subpath 分组做冲突分类。

    Args:
        patches: 同一轮（或同一份草案区）里的候选改写。
        texts: ``subpath -> 全文``。缺某个 subpath 时该组一律算"定位不到"，
            **不产出冲突**——定位不到的 patch 在应用阶段会单独报错，把它混进
            冲突列表会让律师以为自己要裁决一个根本没发生的事。

    Returns:
        冲突列表（确定性排序：subpath → 起始偏移 → patch_ids）。空列表表示
        "全是互补/单条"，可以直接应用。
    """
    conflicts: list[PatchConflict] = []
    for subpath, group in _group_by_subpath(patches).items():
        text = texts.get(subpath, "")
        located = _located(group, text)
        for component in _overlap_components(located):
            if len(component) < 2:
                continue
            conflicts.append(_conflict_of(subpath, component))
    conflicts.sort(key=_sort_key)
    return conflicts


def _group_by_subpath(patches: Sequence[WritePatch]) -> dict[str, list[WritePatch]]:
    grouped: dict[str, list[WritePatch]] = defaultdict(list)
    for patch in patches:
        grouped[patch.subpath].append(patch)
    return dict(grouped)


def _located(group: Sequence[WritePatch], text: str) -> list[tuple[WritePatch, Span]]:
    """能定位到全文区间的 patch（含区间），保持入参顺序。"""
    located: list[tuple[WritePatch, Span]] = []
    for patch in group:
        span = patch_span(text, patch.original)
        if span is not None:
            located.append((patch, span))
    return located


def _overlap_components(located: Sequence[tuple[WritePatch, Span]]) -> list[list[tuple[WritePatch, Span]]]:
    """把"区间相交"关系求连通分量（并查集）。

    三份 patch 两两判断即可：A 与 B 相交、B 与 C 相交，则 A/B/C 是**一个**冲突
    （同一段原文被三种改法命中，律师要一次裁决完），而不是两条两两冲突——
    后者会让前端把同一处画两遍。
    """
    parent = {patch.patch_id: patch.patch_id for patch, _span in located}

    def _find(pid: str) -> str:
        root = pid
        while parent[root] != root:
            root = parent[root]
        while parent[pid] != root:  # 路径压缩
            parent[pid], pid = root, parent[pid]
        return root

    for index, (left, left_span) in enumerate(located):
        for right, right_span in located[index + 1 :]:
            if spans_overlap(left_span, right_span):
                parent[_find(left.patch_id)] = _find(right.patch_id)

    components: dict[str, list[tuple[WritePatch, Span]]] = defaultdict(list)
    for patch, span in located:
        components[_find(patch.patch_id)].append((patch, span))
    return [sorted(members, key=lambda item: item[1]) for members in components.values()]


def _conflict_of(subpath: str, component: Sequence[tuple[WritePatch, Span]]) -> PatchConflict:
    """一个相交分量 → `PatchConflict`（同改法=duplicate，不同改法=overlap_diff）。"""
    ordered = sorted(component, key=lambda item: item[0].patch_id)
    replacements = {patch.replacement for patch, _span in ordered}
    kind: Literal["overlap_diff", "duplicate"] = "duplicate" if len(replacements) == 1 else "overlap_diff"
    return PatchConflict(
        subpath=subpath,
        clause_key=None,
        kind=kind,
        patch_ids=tuple(patch.patch_id for patch, _span in ordered),
        spans=tuple(_span for _patch, _span in ordered),
        summary=_summary(subpath, kind, len(ordered)),
    )


def _summary(subpath: str, kind: str, count: int) -> str:
    if kind == "duplicate":
        return f"「{subpath}」有 {count} 份完全相同的改写，可直接去重"
    return f"「{subpath}」有 {count} 份改写落在同一段原文上（互斥，需律师裁决）"


def _sort_key(conflict: PatchConflict) -> tuple[str, int, tuple[str, ...]]:
    return conflict.subpath, min((span[0] for span in conflict.spans), default=0), conflict.patch_ids


__all__ = ["detect_conflicts", "patch_span", "spans_overlap"]
