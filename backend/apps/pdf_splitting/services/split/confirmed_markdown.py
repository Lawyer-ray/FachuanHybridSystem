"""确认后的分段 Markdown 重建：segments_md.json 的读写与按页区间重新配对。

从 ``services/job_service.py``（原 1177 行）外移的 11 个模块级函数：它们只吃
「存储目录 + 段列表 + pages.json」，不碰任务状态机，因此与 ``PdfSplitJobService``
解耦、单独成文件。``job_service`` 按**原路径** re-export，既有调用方
（``api`` 层 / MCP / 单测）照旧 ``from ...services.job_service import ...``。
本模块不 import ``job_service``，依赖方向单向：``job_service → confirmed_markdown``。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegment, PdfSplitSegmentType
from apps.pdf_splitting.services.storage import PdfSplitStorage
from apps.pdf_splitting.services.template_registry import get_segment_label

from .markdown_builder import load_segment_markdown_map

logger = logging.getLogger("apps.pdf_splitting")


# ↓↓ 由 PdfSplitJobService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _segment_display_label(segment: PdfSplitSegment) -> str:
    """片段展示名：LLM 的开放命名（借条 / 转账凭证等，超出模板枚举）记在
    filename 里、类型仍为 unrecognized——这里把文件名（去 .pdf）透出为
    segment_label，前端把它当类型胶囊展示；规则引擎的未识别段不受影响。"""
    if segment.segment_type == PdfSplitSegmentType.UNRECOGNIZED and str(segment.source_method or "").startswith("llm"):
        stem = re.sub(r"\.pdf$", "", segment.filename or "", flags=re.IGNORECASE).strip()
        if stem and not stem.startswith("未识别材料"):
            return stem
    return get_segment_label(segment.segment_type)


def load_segments_md(path: Path) -> dict[int, str]:
    """读分段 Markdown 产物（order → 正文）；文件缺失 / 损坏一律回空表——
    旧任务没有 md 产物，content_md 退化为空串，不阻断任务详情接口。

    实现在 ``split.markdown_builder.load_segment_markdown_map``，这里只转调：
    下载打包（``PdfSplitService``）也要按 order 取同一份正文，两份解析器必然
    漏改其中一份，而两边口径一旦劈叉就是「屏幕上的正文和下载的 md 不一样」。
    """
    return load_segment_markdown_map(path)


def load_segments_quality_flags(path: Path) -> dict[int, list[str]]:
    """读分段的质量标记（order → quality_flags）。

    与 ``load_segments_md`` / ``load_segments_positioned`` 同源同文件
    （``segments_md.json`` 每段条目的 ``quality_flags``）：段级提示与正文出自同一次
    一致性校对，分文件存迟早会对不上。旧任务没有该字段，或产物损坏时回空表——
    前端按「这一段没有质量提示」降级，不阻断任务详情接口。
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    result: dict[int, list[str]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        flags = item.get("quality_flags")
        if isinstance(flags, list):
            result[order] = [str(flag) for flag in flags if isinstance(flag, str) and flag]
    return result


def load_segments_positioned(path: Path) -> dict[int, list[dict[str, Any]]]:
    """读分段「可定位块」（order → positioned 列表）。

    与 ``load_segments_md`` 同源同文件（``segments_md.json`` 的 ``positioned``
    字段）：布局与正文来自同一次解析，分两个文件存迟早会对不上。
    旧任务没有该字段、或产物损坏时一律回空表——前端按「没有坐标」降级处理，
    不阻断任务详情接口。
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    result: dict[int, list[dict[str, Any]]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        positioned = item.get("positioned")
        if isinstance(positioned, list):
            result[order] = [b for b in positioned if isinstance(b, dict)]
    return result


def load_segments_page_spans(path: Path) -> dict[int, list[dict[str, Any]]]:
    """读分段的页锚点（order → ``page_spans``：``{page, start, end}``，md 字符偏移左闭右开）。

    与 ``load_segments_md`` 同源同文件：锚点是对**那一份** markdown 量出来的，
    分文件存迟早会对不上。旧任务没有该字段、或产物损坏时一律回空表——前端按
    「没有页锚点」降级（切/并段退回旧行为），不阻断任务详情接口。
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list):
        return {}
    result: dict[int, list[dict[str, Any]]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            order = int(item.get("order"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        spans = item.get("page_spans")
        if isinstance(spans, list):
            result[order] = [span for span in spans if isinstance(span, dict)]
    return result


def rebuild_confirmed_segments_md(storage: PdfSplitStorage, normalized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按用户确认后的页区间重算 segments_md 产物（confirm 专用）。

    ``bbox_backend`` 取**取字阶段落盘的实际平台**（``ocr_provider``），不是
    ``job.cloud_backend``：后者默认 "auto"，在 ``resolve_bbox_unit`` 里是 unknown，
    拿它当依据会让 positioned 恒空。旧任务没有这份摘要时留空串，坐标降级为不可用——
    与旧行为一致，但正文仍然正确。

    **表格几何也必须在这里读回来**（与分段阶段同口径）：不读的话，律师确认完分段
    再点格子，格子就退回整表框——“确认后反而变差”比一开始不准更难解释。
    """
    from apps.pdf_splitting.services.split import table_geometry_switches, two_stage

    raw_pages = two_stage.load_pages(storage)
    bbox_backend = str(two_stage.load_extract_summary(storage).get("ocr_provider") or "")
    previous = _read_segments_md_entries(storage.segments_md_path)
    geometry = two_stage.load_table_geometry(storage)
    return build_confirmed_segments_md(
        normalized,
        raw_pages,
        bbox_backend=bbox_backend,
        previous_entries=previous,
        table_geometry=geometry,
        legacy_uniform=table_geometry_switches.uniform_fallback_enabled(),
    )


def build_confirmed_segments_md(
    normalized: list[dict[str, Any]],
    raw_pages: list[dict[str, Any]],
    *,
    bbox_backend: str = "",
    previous_entries: list[dict[str, Any]] | None = None,
    table_geometry: dict[int, dict[int, Any]] | None = None,
    legacy_uniform: bool = False,
) -> list[dict[str, Any]]:
    """纯计算：确认后的段列表 + pages.json → 新的 segments_md 条目。

    走的是与 ``pipeline.analyze_pdf`` / ``service.segment_stage`` **同一条**重建路径
    （同一份 ``build_segments_markdown`` + 同一份一致性判据），所以「用户什么都没改
    直接确认」会得到与自动分段逐字相同的正文，而改过分段的会按新页区间重算。

    ``quality_flags`` 选择**重算**而不是沿用旧产物：判据只依赖 pages（与分段无关），
    重算能保证合并/拆分后的段拿到的是「这一段正文里真的出现了的」提示；沿用旧 flag
    则要把 flag 按页归属拆开，而 flag 本身不带页号，拆不了。
    """
    from apps.pdf_splitting.services.split.consistency_summary import (
        attach_quality_flags_to_markdown,
        detect_inconsistencies,
    )
    from apps.pdf_splitting.services.split.markdown_builder import build_segments_markdown
    from apps.pdf_splitting.services.split.split_models import SegmentDraft

    pages = _pages_from_payload(raw_pages)
    if not pages:
        return _realign_previous_md(normalized, previous_entries or [])

    drafts = [
        SegmentDraft(
            order=order,
            page_start=item["page_start"],
            page_end=item["page_end"],
            segment_type=item["segment_type"],
            filename=item["filename"],
            confidence=float(item.get("confidence") or 0.0),
            source_method=str(item.get("source_method") or "manual"),
            review_flag=str(item.get("review_flag") or PdfSplitReviewFlag.NORMAL),
        )
        for order, item in enumerate(normalized, start=1)
    ]
    return attach_quality_flags_to_markdown(
        build_segments_markdown(
            drafts,
            pages,
            bbox_backend=bbox_backend,
            table_geometry=table_geometry,
            legacy_uniform=legacy_uniform,
        ),
        detect_inconsistencies(pages),
    )


def _pages_from_payload(raw_pages: list[dict[str, Any]]) -> list[Any]:
    """pages.json → PageDescriptor；形状对不上（旧任务写过的老结构）时回空表。

    回空表而不是抛：调用方据此走「按页区间重新配对旧 md」的降级路径，
    正文宁可少一点也不能错位。
    """
    from apps.pdf_splitting.services.split.split_models import PageDescriptor

    try:
        return [PageDescriptor(**item) for item in raw_pages]
    except TypeError:
        logger.warning("pdf_split_confirm_pages_payload_unusable", extra={"pages": len(raw_pages)})
        return []


def _read_segments_md_entries(path: Path) -> list[dict[str, Any]]:
    """读 segments_md.json 的原始条目（降级配对要按页区间查，不能只按 order）。"""
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("pdf_split_segments_md_read_failed", extra={"path": str(path)})
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _entry_page_range(entry: dict[str, Any]) -> tuple[int, int]:
    """旧 md 条目的页区间；非法/缺失返回空区间 (0, -1)。"""
    try:
        start = int(entry.get("page_start"))  # type: ignore[arg-type]
        end = int(entry.get("page_end"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return (0, -1)
    return (start, end) if start >= 1 and end >= start else (0, -1)


def _realign_previous_md(
    normalized: list[dict[str, Any]], previous_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """pages.json 缺失/损坏时按**页区间重叠**把旧 md 配对到新 order。

    绝不能沿用旧 order：confirm 会重排、补洞、合并，旧 order 与新 order 对不上，
    照抄就是整体错位一格——那正是本函数要避免的失败模式。配不上的段留空串。

    页区间完全一致时整条沿用（正文/坐标/提示/页锚点都没变）；只是部分重叠时
    正文按页序拼接、坐标按页号过滤，但**页锚点必须丢**：它是按旧 md 字符串量出来的
    字符偏移，拼接后指向的位置已经不对，留着比没有更糟。
    """
    position_by_page: dict[int, int] = {}
    for position, old_entry in enumerate(previous_entries):
        start, end = _entry_page_range(old_entry)
        for page_no in range(start, end + 1):
            position_by_page.setdefault(page_no, position)

    results: list[dict[str, Any]] = []
    unmatched = 0
    partial = 0
    for order, item in enumerate(normalized, start=1):
        start, end = int(item["page_start"]), int(item["page_end"])
        positions = {position_by_page[no] for no in range(start, end + 1) if no in position_by_page}
        matched = [previous_entries[position] for position in sorted(positions)]
        entry: dict[str, Any] = {
            "order": order,
            "page_start": start,
            "page_end": end,
            "markdown": "\n\n".join(text for text in (str(m.get("markdown") or "") for m in matched) if text),
            "positioned": [],
            "quality_flags": [],
            "page_spans": [],
        }
        if not matched:
            unmatched += 1
        elif len(matched) == 1 and _entry_page_range(matched[0]) == (start, end):
            entry["positioned"] = matched[0].get("positioned") or []
            entry["quality_flags"] = matched[0].get("quality_flags") or []
            entry["page_spans"] = matched[0].get("page_spans") or []
        else:
            partial += 1
            entry["positioned"] = [
                block
                for source in matched
                for block in (source.get("positioned") or [])
                if isinstance(block, dict) and start <= int(block.get("page") or 0) <= end
            ]
            entry["quality_flags"] = list(
                {
                    flag: None
                    for source in matched
                    for flag in (source.get("quality_flags") or [])
                    if isinstance(flag, str) and flag
                }
            )
        results.append(entry)

    if unmatched or partial:
        logger.warning(
            "pdf_split_confirm_md_realigned",
            extra={"segments": len(results), "unmatched": unmatched, "partial": partial},
        )
    return results
