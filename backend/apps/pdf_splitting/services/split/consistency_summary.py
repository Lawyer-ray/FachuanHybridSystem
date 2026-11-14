"""跨页一致性校对的**接入层**：调用判据、裁到可传输的体积、贴到分段上。

## 三件事，边界要清楚

1. **不加过滤**：可疑写法是判据层（`cross_page_consistency.py`）的判断结果，
   接入层一律照实透传。觉得误报多，要改的是判据，不是在这里按关键词挑掉——
   一旦在这里过滤，判据修好了也会被这层吃掉，问题变得不可见。
2. **只裁体积**：真卷宗上这项能出上千条（同一段文字多种写法 × 全本高频词，
   实测一份 164 页卷宗 1340 条）。整体灌进 `summary` 会把 job 详情响应撑到
   几 MB，前端也展示不过来。所以 summary 里只放最可疑的一批，并单独记下总数，
   让前端能说出「还有 N 条未显示」。这是**输出边界**，不是业务过滤。
3. **贴到段上**：某段的 Markdown 里出现了 variant，就把这条不一致写成一条
   中文提示放进该段的 `quality_flags`，前端在段行/正文面板直接显示，不必让
   律师自己去全量清单里找「这一页有没有问题」。

## 为什么挂在 summary 而不是拦流程

与页面质量同一个口径：这是**线索**不是结论（判据只说明「同一处有两种写法，
其中一种很可能是错的」，不判断哪个字对）。拦流程会让律师被启发式的误报挡住，
而他要的只是「这里可能有个错字，你看一眼」。
"""

from __future__ import annotations

from typing import Any

from .cross_page_consistency import Inconsistency, find_inconsistencies

#: 写进 summary 的条数上限。真实卷宗实测 1340 条，全量传输没有意义——
#: 前端是全本清单，律师看的是最可疑的前几十条；其余用 inconsistency_total 交代。
SUMMARY_INCONSISTENCY_LIMIT = 50

#: confidence 的排序口径（与前端 `draft/quality.sortInconsistencies` 一致）：
#: high 在前、medium 次之；判据层将来给别的等级时排在已知识别等级之后。
_CONFIDENCE_RANK = {"high": 0, "medium": 1}
_CONFIDENCE_UNKNOWN_RANK = 2


def detect_inconsistencies(pages: list[Any]) -> list[Inconsistency]:
    """``find_inconsistencies`` 的入口包装：把页描述符列表转成 ``{页号: 该页text}``。

    用 ``text``（取字原文）而不是 ``normalized_text``：归一化会吃掉空白，
    而判据层正是靠空白做「排版差异不算错字」的排除。喂归一化文本会把它变成
    一个更嘈杂的判据，看不出问题出在接入层。
    """
    pages_text = {int(getattr(page, "page_no", 0)): str(getattr(page, "text", "") or "") for page in pages}
    pages_text.pop(0, None)  # 没有页号的占位不进比对
    return find_inconsistencies(pages_text)


def pick_top_inconsistencies(items: list[Inconsistency], *, limit: int = SUMMARY_INCONSISTENCY_LIMIT) -> list[Any]:
    """按 (confidence, variant_count 降序) 取前 ``limit`` 条，转成 summary 用的字典。

    Args:
        items: 判据层原样返回的全部结果（**不要**在调用本函数前过滤）。
        limit: 只影响写进 summary 的条数，不影响 ``inconsistency_total``。

    Returns:
        ``[{canonical, variant, canonical_count, variant_count, pages, confidence}, ...]``
    """
    ordered = sorted(
        items,
        key=lambda item: (
            _CONFIDENCE_RANK.get(item.confidence, _CONFIDENCE_UNKNOWN_RANK),
            -item.variant_count,
            item.canonical,
            item.variant,
        ),
    )
    return [
        {
            "canonical": item.canonical,
            "variant": item.variant,
            "canonical_count": item.canonical_count,
            "variant_count": item.variant_count,
            "pages": list(item.pages),
            "confidence": item.confidence,
        }
        for item in ordered[: max(0, limit)]
    ]


def flags_for_markdown(markdown: str, items: list[Inconsistency]) -> list[str]:
    """某段 Markdown 命中的不一致 → 段级提示文案。

    文案只陈述事实和频次，不替律师判定对错：``疑似错字：受办人（全本 30 次写作
    "经办人" 178 次）``。数字来自判据层统计，接入层不写死任何具体数字。
    """
    if not markdown or not items:
        return []
    flags: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item.variant or item.variant not in markdown or item.variant in seen:
            continue
        seen.add(item.variant)
        flags.append(flag_text(item))
    return flags


def flag_text(item: Inconsistency) -> str:
    """单条不一致的段级提示文案。"""
    return (
        f"疑似错字：{item.variant}"
        f"（全本 {item.canonical_count} 次写作「{item.canonical}」，此写法 {item.variant_count} 次）"
    )


def attach_quality_flags_to_markdown(
    segments_md: list[dict[str, Any]],
    items: list[Inconsistency],
) -> list[dict[str, Any]]:
    """给 ``build_segments_markdown`` 的产物逐条补上 ``quality_flags``。

    在原有条目上就地补键（不改 markdown / positioned）：前端按
    ``segments_md.json`` 的 order 取它，与 content_md 同源同文件，不会错位。
    """
    for entry in segments_md:
        entry["quality_flags"] = flags_for_markdown(str(entry.get("markdown") or ""), items)
    return segments_md
