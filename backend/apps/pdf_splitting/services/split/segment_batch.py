"""LLM 语义分段的**分批**执行（滑动重叠窗口）。

## 为什么不能简单按 N 页硬切

分段是**跨页语义**任务：「第 41 页是一张借条的开头」这个判断，需要看第 40 页
结尾是不是上一份材料的收尾。按 40 页硬切成 [1-40][41-80]，第 41 页的段首
没有左邻页上下文，模型很可能把一个跨批的段切成两段，或者把批首的续页
当成新段。

所以这里用**重叠窗口**：每批向前多看 `OVERLAP_PAGES` 页当「左侧上下文」、
向后多看同样页数当「右侧上下文」，但**只采纳落在本批负责区间的分段**。
重叠页只帮模型判断边界，不产出归属别的批的段。

```
批1 负责 [1..25]，实际送 [1..33]（无左邻，8 页尾巴当上下文）
批2 负责 [26..50]，实际送 [18..58]（8 页左上下文 + 8 页右上下文）
...
```

左上下文是后补的：只有右上下文时，批 N+1 的首页（如全局第 26 页）在
prompt 里前面**没有任何页**，模型看不到第 25 页的收尾/未收尾信号，只能
把批首续页当新材料开头。164 页 = 6 个批界 = 6 个结构性错切点，而续页合并
兜底只救「同类型 + 条款序号推进」的合同，流水/发票/聊天记录没有条款号，
永不合并。prompt 里会把左上下文页标成「上下文页」并明确要求不为它们产出分段。

## 边界如何确定

每批只保留 `page_start` 落在 `[自己的起点, 自己的终点]` 内的分段，并把
`page_end` 裁剪到本批终点。这样：

- 跨批的段会由**起点所在的那一批**完整产出（因为那批能看到右边的重叠页）；
- 不会重复、不会遗漏。

⚠️ 覆盖校验的现状：`merge_batch_drafts` 发现覆盖页数与总页数不符时**只记
warning**，没有正式的校验函数会拦下它（早期注释提到的 `_validate_coverage`
并不存在）。实际整覆盖靠每批内部的 gap 补片间接保证。

## 降级（三层）

1. **单批重试**：一批失败先原地重试 `BATCH_RETRY` 次。LLM 返回非法 JSON 是
   **偶发**的（实测同一批连跑 3 次全成功，但任务里那次恰好抛了），一次抖动
   就丢掉 7 批里其他 6 批的成果太浪费。**≤25 页的单批路径同样走重试**——
   否则小卷宗一次抖动就整轮降级，反而比大卷宗更脆弱。
2. **单批降级规则引擎**：重试仍失败时，只有**这一批**退回规则引擎分段。
   实测 164 页 7 批里很可能只有 1 批偶发失败，整轮退回规则引擎会让本来
   已经很好的 LLM 分段白白浪费。
3. **整轮降级**：仅当**全部批都失败**时，才算 LLM 完全不可用，整轮退回规则
   引擎（由 `detect_segments_with_fallback` 处理）。

⚠️ 关于「两套口径」的顾虑：早期设计曾经是「任一批失败即整轮降级」，理由是
混用会让段边界前后不一致。但真实代价是：一次偶发抖动就让 6/7 的 LLM 成果
作废，而且改用规则引擎后 164 页会切出远多于 82 段的碎片。权衡后选择
「单批降级」：边界可能在某几批略有差异，但总比整本退回规则好。

降级口径必须诚实：`stats` 回传 llm/rule 批数，调用方据此写 summary，
不能在只有 6/7 批走 LLM 时仍宣称整轮 `segment_backend=llm`。

## 批级落盘续跑

`checkpoint_path` 非空时，每批完成即把该批结果写盘；重跑先读盘跳过已完成
批。worker 被 Django-Q 超时杀掉时，已付过费的 LLM 成果不再重付。
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from .split_models import SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")

#: 每批负责的页数。
#:
#: 25 页的依据：实测 164 页整本一次会让 Django-Q 的 600s worker 超时把进程
#: 杀掉（实测某次 164 页任务跑到 499s 时被杀）。25 页一批，单批 LLM 调用约 1-3 分钟，
#: 加 OCR 总时长能稳稳落在限额内；同时批次不太碎，减少跨批边界判断错误的次数。
DEFAULT_SEGMENT_BATCH_PAGES = 25

#: 每批向前/向后各多看多少页当上下文。
#:
#: 8 页约等于一份典型短材料（借条/收据/回单）的长度：足够让模型判断
#: 「上一份材料在哪收尾、下一份从哪开始」，又不至于把批次总输入放大太多。
#: 左右都加后单批窗口从 33 页涨到 41 页（+24%）。
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
        （含左右两侧重叠上下文）。
    """
    size = max(1, size or DEFAULT_SEGMENT_BATCH_PAGES)
    overlap = max(0, overlap if overlap is not None else DEFAULT_SEGMENT_OVERLAP_PAGES)
    if total_pages <= 0:
        return []

    windows: list[tuple[int, int, int, int]] = []
    own_start = 1
    while own_start <= total_pages:
        own_end = min(own_start + size - 1, total_pages)
        # 批首必须有左邻页：否则模型看不到上一批的收尾信号，会把续页当新材料开头。
        # 第一批没有左邻，win_start 自然收敛到 1；最后一页之后没有右上下文可给。
        win_start = max(1, own_start - overlap)
        win_end = min(own_end + overlap, total_pages)
        windows.append((own_start, own_end, win_start, win_end))
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

    合并后若出现空隙/重叠，这里**只记 warning、不静默修补**：上层并没有一道
    正式的完整覆盖校验会拦下它（见模块 docstring），实际整覆盖靠每批内部的
    gap 补片间接保证。宁可留下可观测的缺口日志，也不要产出一个「看起来完整
    但实际错位」的分段表。
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
    变的只是摘要里那个「第N页」标号。左上下文页与负责页一起从 1 连续编号，
    所以外层偏移仍是 `win_start - 1`。
    """
    try:
        return replace(page, page_no=page_no)
    except TypeError:
        import copy

        clone = copy.copy(page)
        clone.page_no = page_no
        return clone


def _with_order(draft: Any, order: int) -> Any:
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
    context_pages: int = 0,
) -> list[Any]:
    """单批带重试的 LLM 分段。最后一次仍失败则抛出。

    `context_pages` 只在非 0 时传给 detector：detector 协议的基础签名是
    `detect(pages, *, template_key)`，左上下文标注是分批路径的扩展参数，
    整本一次调用（没有上下文页）时不该要求实现方接受它。
    """
    options: dict[str, Any] = {"template_key": template_key}
    if context_pages:
        options["context_pages"] = context_pages
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            # detector 是注入的（Any）：显式收窄避免 no-any-return
            return list(detector.detect(slice_pages, **options))
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
    stats: dict[str, Any] | None = None,
    checkpoint_path: Path | None = None,
) -> list[Any]:
    """分批跑 LLM 分段并合并。

    降级策略见模块 docstring（单批重试 → 单批规则引擎 → 全失败才整轮降级）。
    只有**全部批都失败**时才抛异常，让上层整轮降级规则引擎。

    Args:
        stats: 调用方传入的空 dict，本函数填入诚实的批次口径
            `{"total_batches", "llm_batches", "rule_batches", "single_batch"}`，
            另附 `"resumed_batches"`（从 checkpoint 复用的批数）与
            `"boundary_reviews"`（二审给出结论的边界数）。返回值仍是 list。
            整轮失败抛异常前也会填好，调用方能据此写「全部降级」而不是空口径。
        checkpoint_path: 批级落盘路径。每批完成即写盘，重跑先读盘跳过已完成批。
    """
    total_pages = len(pages)
    batch_size = max(1, size or DEFAULT_SEGMENT_BATCH_PAGES)
    batch_overlap = max(0, overlap if overlap is not None else DEFAULT_SEGMENT_OVERLAP_PAGES)
    windows = plan_segment_windows(total_pages, size=batch_size, overlap=batch_overlap)
    retries = DEFAULT_BATCH_RETRY if retries is None else max(0, retries)

    def report(*, llm: int, rule: int, single: bool, resumed: int = 0, reviews: int = 0) -> None:
        if stats is None:
            return
        stats.update(
            {
                "total_batches": len(windows),
                "llm_batches": llm,
                "rule_batches": rule,
                "single_batch": single,
                "resumed_batches": resumed,
                "boundary_reviews": reviews,
            }
        )

    # 只有一批时不必走合并逻辑。重试同样要有：小卷宗一次非法 JSON 就整轮
    # 降级，反而比大卷宗更脆弱（大卷宗只损失一批）。
    if len(windows) <= 1:
        report(llm=0, rule=0, single=True)
        drafts = _detect_with_retry(
            detector=detector,
            slice_pages=pages,
            template_key=template_key,
            retries=retries,
        )
        reviewed, reviews = _review_boundaries(drafts, pages=pages, windows=windows, detector=detector)
        report(llm=1, rule=0, single=True, reviews=reviews)
        return reviewed

    done = _load_checkpoint(
        checkpoint_path,
        template_key=template_key,
        total_pages=total_pages,
        size=batch_size,
        overlap=batch_overlap,
    )
    resumed = len(done)
    lock = threading.Lock()

    def run_one(window: tuple[int, int, int, int]) -> tuple[tuple[int, int, int, int], list[Any], str]:
        """跑一批，返回 (窗口, 已偏移的分段, 路径标识 llm/rule)。"""
        cached = done.get(window)
        if cached is not None:
            logger.info(
                "pdf_split_segment_batch_resumed",
                extra={"window": f"{window[2]}-{window[3]}", "drafts": len(cached[1]), "path": cached[0]},
            )
            return window, cached[1], cached[0]

        own_start, own_end, win_start, win_end = window
        # ★ 切片后必须把 page_no 重编号成 1..n 再喂给 LLM。
        #
        # 踩过的坑：digest 里用的是 `PageDescriptor.page_no`（全局页号），
        # 第二批判 26..58 就如实写「第26页」——LLM 于是返回 page_start=26，
        # 而 `parse_llm_segments(total_pages=len(切片))` 只有 33 页可用，
        # 26..58 一半落在范围外被丢弃，叠加外层 `+ offset` 还会二次偏移。
        # 结果就是「LLM 输出没有任何可用分段」→ 整轮降级规则引擎。
        #
        # 左上下文页与负责页一起从 1 连续编号，所以 offset 仍是 win_start - 1。
        raw_slice = pages[win_start - 1 : win_end]
        slice_pages = [_renumber_page(item, index + 1) for index, item in enumerate(raw_slice)]
        left_context = own_start - win_start

        try:
            drafts = _detect_with_retry(
                detector=detector,
                slice_pages=slice_pages,
                template_key=template_key,
                retries=retries,
                context_pages=left_context,
            )
            path = "llm"
            offset = win_start - 1
        except Exception:
            # 这一批 LLM 实在不行 → 只让这一批退回规则引擎，
            # 其他批的 LLM 成果照样保留（否则一次抖动废掉 6/7 的成果）。
            logger.exception(
                "pdf_split_segment_batch_fallback_rule",
                extra={"own_start": own_start, "own_end": own_end, "window": f"{win_start}-{win_end}"},
            )
            # ★ 规则引擎只喂**负责区间**，且重新从 1 编号。
            #
            # 两个原因：① 它按 `pages[page_no - 1]` 取页、按 `total_pages=len(pages)`
            # 补 gap，页号必须是从 1 起的连续区间，带左上下文的切片会让它取错页；
            # ② 若把左上下文页一起喂进去，它产出的首段起点落在上下文区，会被
            # merge_batch_drafts 按「只采纳 own 区间」丢掉，负责区间的开头几页
            # 就成了覆盖缺口（加左上下文后实测踩中）。
            own_pages = [_renumber_page(item, index + 1) for index, item in enumerate(pages[own_start - 1 : own_end])]
            drafts = _rule_fallback_for_window(own_pages, template_key)
            path = "rule"
            offset = own_start - 1

        shifted = [
            _with_page_range(item, int(item.page_start) + offset, int(item.page_end) + offset) for item in drafts
        ]
        logger.info(
            "pdf_split_segment_batch_done",
            extra={
                "own": f"{own_start}-{own_end}",
                "window": f"{win_start}-{win_end}",
                "left_context": left_context,
                "drafts": len(shifted),
                "path": path,
            },
        )
        # 每批完成即落盘：worker 被杀后重跑不再重付这一批的 LLM 费。
        # 写盘失败只记 warning——checkpoint 是省钱优化，不该让它弄挂任务。
        with lock:
            done[window] = (path, shifted)
            _save_checkpoint(
                checkpoint_path,
                template_key=template_key,
                total_pages=total_pages,
                size=batch_size,
                overlap=batch_overlap,
                done=done,
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
        report(llm=0, rule=rule_used, single=False, resumed=resumed)
        raise RuntimeError(f"全部 {len(windows)} 批 LLM 分段均失败，已整轮降级")

    if rule_used:
        logger.warning(
            "pdf_split_segment_partial_rule_fallback",
            extra={"llm_batches": llm_ok, "rule_batches": rule_used, "total_batches": len(windows)},
        )

    merged = merge_batch_drafts(batch_results=results, total_pages=total_pages)
    reviewed, reviews = _review_boundaries(merged, pages=pages, windows=windows, detector=detector)
    report(llm=llm_ok, rule=rule_used, single=False, resumed=resumed, reviews=reviews)
    return reviewed


# ── 边界二审编排（判据与改边界的纯函数在 segment_merge）──────────────


def _review_boundaries(
    drafts: list[Any],
    *,
    pages: list[Any],
    windows: list[tuple[int, int, int, int]],
    detector: Any,
) -> tuple[list[Any], int]:
    """对疑点边界做有界二审，返回 (改过的分段, 拿到结论的边界数)。

    detector 没有 `review_boundary` 能力时**整段跳过**：注入的桩 detector
    只实现 detect，不该因为分段就触发真实 LLM 调用。
    """
    from .segment_merge import (
        MAX_BOUNDARY_REVIEWS,
        apply_boundary_verdict,
        collect_boundary_suspects,
        mark_unverified_boundaries,
    )

    reviewer = getattr(detector, "review_boundary", None)
    if reviewer is None or len(drafts) <= 1:
        return drafts, 0

    suspects = collect_boundary_suspects(drafts, batch_start_pages={window[0] for window in windows[1:]})
    if not suspects:
        return drafts, 0

    chosen = suspects[:MAX_BOUNDARY_REVIEWS]
    text_by_page = {int(page.page_no): str(getattr(page, "text", "") or "") for page in pages}
    verdicts = _run_boundary_reviews(reviewer, chosen, text_by_page)

    result = drafts
    reviews = 0
    unverified = set(suspects[MAX_BOUNDARY_REVIEWS:])
    for boundary in chosen:
        action = verdicts.get(boundary)
        if action is None:
            unverified.add(boundary)
            continue
        reviews += 1
        result = apply_boundary_verdict(result, boundary_page=boundary, action=action)
    return mark_unverified_boundaries(result, boundary_pages=unverified), reviews


def _run_boundary_reviews(
    reviewer: Any,
    boundaries: list[int],
    text_by_page: dict[int, str],
) -> dict[int, str | None]:
    """并行跑二审（墙钟约等于一次），任何异常都记为 None = 未复核。"""
    verdicts: dict[int, str | None] = {}
    workers = min(DEFAULT_SEGMENT_CONCURRENCY, len(boundaries))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pdfsplit-review") as pool:
        futures = {
            pool.submit(
                reviewer,
                left_page=boundary - 1,
                right_page=boundary,
                left_text=text_by_page.get(boundary - 1, ""),
                right_text=text_by_page.get(boundary, ""),
            ): boundary
            for boundary in boundaries
        }
        for future in as_completed(futures):
            boundary = futures[future]
            try:
                verdicts[boundary] = future.result()
            except Exception as exc:
                logger.warning(
                    "pdf_split_boundary_review_error",
                    extra={"boundary_page": boundary, "error": f"{type(exc).__name__}: {str(exc)[:120]}"},
                )
                verdicts[boundary] = None
    return verdicts


# ── 批级 checkpoint（落盘 / 读回）─────────────────────────────────

_CHECKPOINT_VERSION = 1


def _draft_to_dict(draft: Any) -> dict[str, Any]:
    return {
        "order": int(getattr(draft, "order", 0)),
        "page_start": int(draft.page_start),
        "page_end": int(draft.page_end),
        "segment_type": str(getattr(draft, "segment_type", "unrecognized")),
        "filename": str(getattr(draft, "filename", "")),
        "confidence": float(getattr(draft, "confidence", 0.0)),
        "source_method": str(getattr(draft, "source_method", "llm")),
        "review_flag": str(getattr(draft, "review_flag", "normal")),
    }


def _draft_from_dict(item: Any) -> SegmentDraft | None:
    """从落盘字典还原 SegmentDraft；形状不对返回 None（该批按未完成处理）。"""
    if not isinstance(item, dict):
        return None
    try:
        start, end = int(item["page_start"]), int(item["page_end"])
        if start < 1 or end < start:
            return None
        return SegmentDraft(
            order=int(item.get("order", 0)),
            page_start=start,
            page_end=end,
            segment_type=str(item.get("segment_type") or "unrecognized"),
            filename=str(item.get("filename") or ""),
            confidence=float(item.get("confidence", 0.0)),
            source_method=str(item.get("source_method") or "llm"),
            review_flag=str(item.get("review_flag") or "normal"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _checkpoint_fingerprint(*, template_key: str, total_pages: int, size: int, overlap: int) -> dict[str, Any]:
    return {
        "version": _CHECKPOINT_VERSION,
        "template_key": template_key,
        "total_pages": total_pages,
        "size": size,
        "overlap": overlap,
    }


def _load_checkpoint(
    path: Path | None,
    *,
    template_key: str,
    total_pages: int,
    size: int,
    overlap: int,
) -> dict[tuple[int, int, int, int], tuple[str, list[Any]]]:
    """读回已完成批。文件缺失 / 损坏 / 参数不一致一律按「无 checkpoint」处理。

    参数（模板 / 总页数 / 批大小 / 重叠）进了指纹：换了参数窗口就变了，
    旧批结果不能拿来用，否则会拼出错位的分段表。
    """
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "pdf_split_segment_checkpoint_unreadable",
            extra={"path": str(path), "error": f"{type(exc).__name__}: {str(exc)[:120]}"},
        )
        return {}
    expected = _checkpoint_fingerprint(template_key=template_key, total_pages=total_pages, size=size, overlap=overlap)
    if not isinstance(payload, dict) or any(payload.get(key) != value for key, value in expected.items()):
        logger.warning("pdf_split_segment_checkpoint_stale", extra={"path": str(path)})
        return {}

    done: dict[tuple[int, int, int, int], tuple[str, list[Any]]] = {}
    for item in payload.get("batches") or []:
        parsed = _parse_checkpoint_batch(item)
        if parsed is not None:
            done[parsed[0]] = (parsed[1], parsed[2])
    logger.info("pdf_split_segment_checkpoint_loaded", extra={"path": str(path), "batches": len(done)})
    return done


def _parse_checkpoint_batch(item: Any) -> tuple[tuple[int, int, int, int], str, list[Any]] | None:
    if not isinstance(item, dict):
        return None
    window = item.get("window")
    path = item.get("path")
    if not isinstance(window, (list, tuple)) or len(window) != 4 or path not in ("llm", "rule"):
        return None
    try:
        key = (int(window[0]), int(window[1]), int(window[2]), int(window[3]))
    except (TypeError, ValueError):
        return None
    raw_drafts = item.get("drafts")
    if not isinstance(raw_drafts, list) or not raw_drafts:
        return None
    drafts = [_draft_from_dict(raw) for raw in raw_drafts]
    if any(draft is None for draft in drafts):
        return None
    return key, str(path), [draft for draft in drafts if draft is not None]


def _save_checkpoint(
    path: Path | None,
    *,
    template_key: str,
    total_pages: int,
    size: int,
    overlap: int,
    done: dict[tuple[int, int, int, int], tuple[str, list[Any]]],
) -> None:
    """整份重写 + 原子替换：读到半截文件的概率比增量追加低得多。

    调用方持锁，所以临时文件名不会撞。批数 ≤ 40（1000 页 / 25），整份重写
    的代价可以忽略，换来的是「任何时刻盘上都是一份完整可用的 checkpoint」。
    """
    if path is None:
        return
    payload = _checkpoint_fingerprint(template_key=template_key, total_pages=total_pages, size=size, overlap=overlap)
    payload["batches"] = [
        {"window": list(window), "path": path_kind, "drafts": [_draft_to_dict(d) for d in drafts]}
        for window, (path_kind, drafts) in sorted(done.items())
    ]
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning(
            "pdf_split_segment_checkpoint_write_failed",
            extra={"path": str(path), "error": f"{type(exc).__name__}: {str(exc)[:120]}"},
        )
