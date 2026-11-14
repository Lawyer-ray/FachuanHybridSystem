"""LLM 语义分段的**分批**执行（滑动重叠窗口）。

## 为什么不能简单按 N 页硬切

分段是**跨页语义**任务：「第 41 页是一张借条的开头」这个判断，需要看第 40 页
结尾是不是上一份材料的收尾。按 40 页硬切成 [1-40][41-80]，第 41 页的段首
没有左邻页上下文，模型很可能把一个跨批的段切成两段，或者把批首的续页
当成新段。

所以这里用**重叠窗口**：每批向后多看 `OVERLAP_PAGES` 页作为「右侧上下文」，
但**只采纳落在本批负责区间的分段**。重叠页只帮模型判断边界，不产出归属
别的批的段。

```
批1 负责 [1..40]，实际送 [1..48]（40 + 8 页尾巴当上下文）
批2 负责 [41..80]，实际送 [41..88]
...
```

## 边界如何确定

每批只保留 `page_start` 落在 `[自己的起点, 自己的终点]` 内的分段，并把
`page_end` 裁剪到本批终点。这样：

- 跨批的段会由**起点所在的那一批**完整产出（因为那批能看到右边的重叠页）；
- 不会重复、不会遗漏（`_validate_coverage` 那条完整覆盖校验仍照旧生效）。

## 降级（三层）

1. **单批重试**：一批失败先原地重试 `BATCH_RETRY` 次。LLM 返回非法 JSON 是
   **偶发**的（实测同一批连跑 3 次全成功，但任务里那次恰好抛了），一次抖动
   就丢掉 7 批里其他 6 批的成果太浪费。
2. **单批降级规则引擎**：重试仍失败时，只有**这一批**退回规则引擎分段。
   实测 164 页 7 批里很可能只有 1 批偶发失败，整轮退回规则引擎会让本来
   已经很好的 LLM 分段白白浪费。
3. **整轮降级**：仅当**全部批都失败**时，才算 LLM 完全不可用，整轮退回规则
   引擎（由 `detect_segments_with_fallback` 处理）。

⚠️ 关于「两套口径」的顾虑：早期设计曾经是「任一批失败即整轮降级」，理由是
混用会让段边界前后不一致。但真实代价是：一次偶发抖动就让 6/7 的 LLM 成果
作废，而且改用规则引擎后 164 页会切出远多于 82 段的碎片。权衡后选择
「单批降级」：边界可能在某几批略有差异，但总比整本退回规则好，且
`merge_batch_drafts` 的覆盖校验仍会兜住真正的缺口。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger("apps.pdf_splitting")

#: 每批负责的页数。
#:
#: 25 页的依据：实测 164 页整本一次会让 Django-Q 的 600s worker 超时把进程
#: 杀掉（实测某次 164 页任务跑到 499s 时被杀）。25 页一批，单批 LLM 调用约 1-3 分钟，
#: 加 OCR 总时长能稳稳落在限额内；同时批次不太碎，减少跨批边界判断错误的次数。
DEFAULT_SEGMENT_BATCH_PAGES = 25

#: 每批向后多看多少页当上下文。
#:
#: 8 页约等于一份典型短材料（借条/收据/回单）的长度：足够让模型判断
#: 「下一份材料从哪开始」，又不至于把批次总输入放大太多（32%）。
DEFAULT_SEGMENT_OVERLAP_PAGES = 8

#: 单批失败重试次数。
#:
#: LLM 返回非法 JSON 是偶发的：实测同一批（164 页卷宗的第 1 批）连跑 3 次
#: 全成功（12-15 段），但后台任务里那次恰好抛了。没有重试的话，一次抖动
#: 就会让这一批退回规则引擎，而「任一批失败即整轮降级」的旧策略更糟—
#: 一次抖动废掉 6/7 的 LLM 成果。
DEFAULT_BATCH_RETRY = 2

#: 分段批的并行度。
#:
#: 为什么必须并行：7 批串行时每批 80s 左右，累计 560s+，再加重试就顶到
#: Django-Q 的 600s worker 超时（实测 164 页任务分段阶段跑到 595s 被杀）。
#: 并行后墙钟约等于最慢那一批，总时长成倍下降。
#:
#: 取 4：LLM 服务通常能承受少量并发，且 7 批 / 4 并发 ≈ 2 轮，比全异步
#: 更不容易把对端打限流。
DEFAULT_SEGMENT_CONCURRENCY = 4


def plan_segment_windows(
    total_pages: int,
    *,
    size: int | None = None,
    overlap: int | None = None,
) -> list[tuple[int, int, int, int]]:
    """规划分批窗口。

    Returns:
        `[(own_start, own_end, win_start, win_end), ...]` —— 前两个是本批
        **负责**的页区间（1-based，闭区间），后两个是实际**送给模型**的区间
        （含右侧重叠上下文）。
    """
    size = max(1, size or DEFAULT_SEGMENT_BATCH_PAGES)
    overlap = max(0, overlap if overlap is not None else DEFAULT_SEGMENT_OVERLAP_PAGES)
    if total_pages <= 0:
        return []

    windows: list[tuple[int, int, int, int]] = []
    own_start = 1
    while own_start <= total_pages:
        own_end = min(own_start + size - 1, total_pages)
        # 最后一页之后没有上下文可给，win_end 自然收敛到 total_pages
        win_end = min(own_end + overlap, total_pages)
        windows.append((own_start, own_end, own_start, win_end))
        own_start = own_end + 1
    return windows


def merge_batch_drafts(
    *,
    batch_results: list[tuple[tuple[int, int, int, int], list[Any]]],
    total_pages: int,
) -> list[Any]:
    """把各批的分段合并成整本的分段列表。

    规则：
    - 只采纳 `page_start` 落在本批负责区间的段；
    - `page_end` 裁到本批负责终点（重叠区的段不算本批的）；
    - 按 page_start 排序后重新编号 order。

    合并后若出现空隙/重叠，交给上层既有的完整覆盖校验报错——这里不静默修补，
    宁可让规则引擎兜底，也不要产出一个「看起来完整但实际错位」的分段表。
    """
    collected: list[Any] = []

    for (own_start, own_end, _win_start, _win_end), drafts in batch_results:
        for draft in drafts:
            start = int(getattr(draft, "page_start", 0))
            end = int(getattr(draft, "page_end", 0))
            # 段起点不在本批负责区间 → 属于别的批，跳过（避免重复）
            if start < own_start or start > own_end:
                continue
            clipped_end = min(end, own_end)
            if clipped_end < start:
                continue
            if clipped_end != end:
                draft = _with_page_range(draft, start, clipped_end)
            collected.append(draft)

    collected.sort(key=lambda item: (int(getattr(item, "page_start", 0)), int(getattr(item, "page_end", 0))))
    merged = [_with_order(item, index) for index, item in enumerate(collected)]

    # 合并后覆盖是否连续完整——这里只记日志，判定留给上层的正式校验
    covered = sum(int(getattr(d, "page_end", 0)) - int(getattr(d, "page_start", 0)) + 1 for d in merged)
    if covered != total_pages:
        logger.warning(
            "pdf_split_segment_batch_coverage_mismatch",
            extra={"covered": covered, "total_pages": total_pages},
        )
    return merged


def _with_page_range(draft: Any, start: int, end: int) -> Any:
    """生成一个 page_start/page_end 被改写过的新 draft（不改原对象）。"""
    from dataclasses import replace

    try:
        return replace(draft, page_start=start, page_end=end)
    except TypeError:  # 非 dataclass（测试桩）→ 退化为浅拷贝改属性
        import copy

        clone = copy.copy(draft)
        clone.page_start = start
        clone.page_end = end
        return clone


def _renumber_page(page: Any, page_no: int) -> Any:
    """浅拷贝一份页描述、把 page_no 换成批内相对页号。

    只改 page_no：text/layout/top_candidates 等全部沿用，LLM 看到的正文不变，
    变的只是摘要里那个「第N页」标号。
    """
    from dataclasses import replace

    try:
        return replace(page, page_no=page_no)
    except TypeError:
        import copy

        clone = copy.copy(page)
        clone.page_no = page_no
        return clone


def _with_order(draft: Any, order: int) -> Any:
    from dataclasses import replace

    try:
        return replace(draft, order=order)
    except TypeError:
        import copy

        clone = copy.copy(draft)
        clone.order = order
        return clone


def _detect_with_retry(
    *,
    detector: Any,
    slice_pages: list[Any],
    template_key: str,
    retries: int,
) -> list[Any]:
    """单批带重试的 LLM 分段。最后一次仍失败则抛出。"""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            # detector 是注入的（Any）：显式收窄避免 no-any-return
            return list(detector.detect(slice_pages, template_key=template_key))
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                logger.warning(
                    "pdf_split_segment_batch_retry",
                    extra={"attempt": attempt + 1, "error": f"{type(exc).__name__}: {str(exc)[:120]}"},
                )
    assert last_error is not None
    raise last_error


def _rule_fallback_for_window(slice_pages: list[Any], template_key: str) -> list[Any]:
    """单批退回规则引擎分段（只影响这一批）。"""
    from .segment_detector import SegmentDetector

    return SegmentDetector().detect_segments(slice_pages, template_key=template_key)


def detect_in_batches(
    *,
    pages: list[Any],
    template_key: str,
    detector: Any,
    size: int | None = None,
    overlap: int | None = None,
    retries: int | None = None,
) -> list[Any]:
    """分批跑 LLM 分段并合并。

    降级策略见模块 docstring（单批重试 → 单批规则引擎 → 全失败才整轮降级）。
    只有**全部批都失败**时才抛异常，让上层整轮降级规则引擎。
    """
    total_pages = len(pages)
    windows = plan_segment_windows(total_pages, size=size, overlap=overlap)
    retries = DEFAULT_BATCH_RETRY if retries is None else max(0, retries)

    # 只有一批时不必走合并逻辑（保留原始行为与日志）
    if len(windows) <= 1:
        return list(detector.detect(pages, template_key=template_key))

    def run_one(window: tuple[int, int, int, int]) -> tuple[tuple[int, int, int, int], list[Any], str]:
        """跑一批，返回 (窗口, 已偏移的分段, 路径标识 llm/rule)。"""
        own_start, own_end, win_start, win_end = window
        # ★ 切片后必须把 page_no 重编号成 1..n 再喂给 LLM。
        #
        # 踩过的坑：digest 里用的是 `PageDescriptor.page_no`（全局页号），
        # 第二批判 26..58 就如实写「第26页」——LLM 于是返回 page_start=26，
        # 而 `parse_llm_segments(total_pages=len(切片))` 只有 33 页可用，
        # 26..58 一半落在范围外被丢弃，叠加外层 `+ offset` 还会二次偏移。
        # 结果就是「LLM 输出没有任何可用分段」→ 整轮降级规则引擎。
        raw_slice = pages[win_start - 1 : win_end]
        slice_pages = [_renumber_page(item, index + 1) for index, item in enumerate(raw_slice)]
        offset = win_start - 1

        try:
            drafts = _detect_with_retry(
                detector=detector,
                slice_pages=slice_pages,
                template_key=template_key,
                retries=retries,
            )
            path = "llm"
        except Exception:
            # 这一批 LLM 实在不行 → 只让这一批退回规则引擎，
            # 其他批的 LLM 成果照样保留（否则一次抖动废掉 6/7 的成果）。
            logger.exception(
                "pdf_split_segment_batch_fallback_rule",
                extra={"own_start": own_start, "own_end": own_end, "window": f"{win_start}-{win_end}"},
            )
            drafts = _rule_fallback_for_window(slice_pages, template_key)
            path = "rule"

        shifted = [
            _with_page_range(item, int(item.page_start) + offset, int(item.page_end) + offset) for item in drafts
        ]
        logger.info(
            "pdf_split_segment_batch_done",
            extra={
                "own": f"{own_start}-{own_end}",
                "window": f"{win_start}-{win_end}",
                "drafts": len(shifted),
                "path": path,
            },
        )
        return window, shifted, path

    # ★ 并行跑各批：分段批之间互相独立（各看各的窗口、各调各的 LLM），
    # 串行会让 7 批 × 80s ≈ 560s，再加上重试就顶到 Django-Q 的 600s 线
    # （实测 164 页任务分段阶段跑到 595s 后被杀）。并行把墙钟压到最慢那一批。
    results: list[tuple[tuple[int, int, int, int], list[Any]]] = []
    llm_ok = 0
    rule_used = 0
    workers = min(DEFAULT_SEGMENT_CONCURRENCY, len(windows))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdfsplit-seg") as pool:
        futures = [pool.submit(run_one, window) for window in windows]
        for future in as_completed(futures):
            window, shifted, path = future.result()
            results.append((window, shifted))
            if path == "llm":
                llm_ok += 1
            else:
                rule_used += 1

    # as_completed 打乱了顺序，合并前按窗口起点排回来（结果本身无序安全，排序只为日志/稳定性）
    results.sort(key=lambda item: item[0][0])

    # 全部都走了规则引擎 → LLM 实际不可用，让上层整轮降级（保持 summary 口径诚实）
    if llm_ok == 0:
        raise RuntimeError(f"全部 {len(windows)} 批 LLM 分段均失败，已整轮降级")

    if rule_used:
        logger.warning(
            "pdf_split_segment_partial_rule_fallback",
            extra={"llm_batches": llm_ok, "rule_batches": rule_used, "total_batches": len(windows)},
        )

    return merge_batch_drafts(batch_results=results, total_pages=total_pages)
