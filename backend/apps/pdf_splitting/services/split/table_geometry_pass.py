"""表格几何 pass 层：选候选页 → 抽子 PDF 批量送引擎（失败回退单页裁图）→ 配对 → 落产物。

## 这个文件只放什么 / 不许放什么

只放**要碰外部世界**的那一段：候选页挑选、子 PDF 切片与单页裁图渲染（fitz）、真实引擎
客户端（本层唯一碰网络的地方）、逐页配对与产物拼装、产物 → 定位映射
（``geometries_by_page_block``）与 ``summary.table_geometry`` 区块（``summary_block``）。

**不许放**坐标数学：像素→页面换算、行列聚类、结构硬闸、表↔块配对全部在纯数学层
``table_geometry.py``（本文件只调用它们），也不许放开关读取（``table_geometry_switches.py``）。
两条路径（子 PDF 批量 / 单页裁图）共用纯数学层的同一段对齐与配对代码，否则会得出两套格子。

## 为什么这些常量在这里

``SUMMARY_KEYS`` / ``_FULL_PAGE_CROP`` / 单次预算与页数上限（``DEFAULT_BUDGET_SECONDS`` /
``DEFAULT_MAX_PAGES`` / ``_FALLBACK_MAX_PAGES``）/ 回退裁图参数（``_FALLBACK_CROP_DPI`` /
``_CROP_MARGIN_RATIO``）都不是几何判定，而是**这一层的输入输出契约**：只被
``build_geometry_artifact`` 及其下游（产物、summary、回退路径）消费，纯数学层一个字都
用不到，所以跟着实现走、不跟着数学走。

## PP 没量到时的兜底：本地线条投影（L2，默认关）

``build_geometry_artifact`` 末尾的 ``_apply_local_lines`` 会在**开关开**且该页 PP 一张表也没配上时，
直接量页图上的墨线（``table_geometry_lines``，``engine="raster_lines"``）。三道门槛一起挡
（PP 成功页不跑 / 整表框原因属「PP 没量到」那一类 / 行列与 td 文本数能证明归属），
少一道都只能画出「很好看的错框」。默认关的理由见 ``table_geometry_switches``。

## 降级纪律

几何是**定位精度**的增强，不是正文的一部分：引擎/网络/PDF 任何失败都只记 reason、
整表框降级，绝不抛（reason 键见 ``table_geometry.REASON_*``）。
产物结构见 ``storage.table_geometry_json_path`` 的注释::

    {"engine": "pp_structure_v3", "generated_at": "...", "summary": {...},
     "pages": {"10": {"tables": {"2": {...}}, "skipped": {}}}}
"""

from __future__ import annotations

import logging
import math
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pymupdf as fitz

from .bbox import normalize_bbox, resolve_bbox_unit
from .md_table import grid_col_count as _grid_col_count
from .md_table import grid_row_count as _grid_row_count
from .md_table import parse_grid as _parse_grid
from .table_geometry import (
    _BOX_AXES,
    _RECT_PRECISION,
    _SIZE_AXES,
    PP_STRUCTURE_ENGINE,
    REASON_BATCH_FAILED,
    REASON_BUDGET_EXHAUSTED,
    REASON_EMPTY_CELLS,
    REASON_ENGINE_ERROR,
    REASON_GEOMETRY_INCONSISTENT,
    REASON_MATCHED,
    REASON_NO_COORDINATES,
    REASON_NO_TABLE_DETECTED,
    REASON_ORPHAN_PP_TABLE,
    REASON_PP_BOX_OUTSIDE_BLOCK,
    REASON_PP_SHAPE_MISMATCH,
    REASON_PSEUDO_TABLE,
    REASON_ROTATION,
    REASON_UNMATCHED_PP_TABLE,
    PageTableGeometry,
    TableCellBox,
    TableMatch,
    TableMeasureEngine,
    _as_floats,
    _clamp01,
    _length_of,
    _ocr_lines,
    _union_rect,
    _valid_pixel_rects,
    assign_cell_texts,
    block_table_html,
    build_cell_boxes,
    grid_shape,
    html_grid_shape,
    match_tables_to_blocks,
    measure_table_crop,
    structural_check,
)
from .table_geometry_lines import LOCAL_LINE_ENGINE, RasterGrid, cells_from_grid, detect_grid_from_png

logger = logging.getLogger("apps.pdf_splitting")


#: 批量路径失败后回退单页裁图的页数上限。
#:
#: 只回退前 6 页：单页裁图实测 7.2–32.5s/页（``facts/FACTS.md`` SF-16），
#: 22 页全跑要 158–715s，会把段阶段拖死。前 6 页是“先救最脏的”，
#: 剩下的记 ``batch_failed`` 并整表框。
_FALLBACK_MAX_PAGES = 6

#: 批量单次调用预算（秒）。实测 22 页子 PDF 101.67s / 6 页 13.76s（``facts/BATCH.md`` §0），
#: 150s 留 1.5× 余量；超时只影响本页的定位粒度，不影响正文。
DEFAULT_BUDGET_SECONDS = 150.0

#: 单次最多送多少页。22 是当前最大实测卷宗的候选页数（DESIGN §9.1），24 留一次余量。
DEFAULT_MAX_PAGES = 24

#: 回退裁图路径的渲染 DPI（与 ``ocr_handler`` 的 BALANCED 档一致）。
_FALLBACK_CROP_DPI = 200

#: 回退裁图时向表格块外扩的页边距（``facts/raw/collect_crop.py`` 同口径）。
_CROP_MARGIN_RATIO = 0.005

#: L2 兜底渲染整页的 DPI（与 ``table_geometry_lines`` 的阈值口径、eval 脚本同源）。
#:
#: 150dpi 下 1px ≈ 0.0008 页宽，线检测的像素级外扩（``REGION_PAD_PX=6``）≈ 0.005 页，
#: 正好与 ``_CROP_MARGIN_RATIO`` 同量级；再高只是变慢（纯 numpy 投影不吃分辨率）。
_LOCAL_LINES_RENDER_DPI = 150

#: 触发 L2 兜底的整表框原因：PP **没量到**（而不是「量到了但不可信/多余」）的那几类。
#:
#: ``pseudo_table`` / ``pp_shape_mismatch`` / ``unmatched_pp_table`` 等**不**在集合里：
#: 前者本来就不该画格，后者 PP 已经给出了表 —— 两个源在同一页各画一套格子比没有框更糟。
_LOCAL_LINES_TRIGGER_REASONS: frozenset[str] = frozenset(
    {
        REASON_NO_TABLE_DETECTED,
        REASON_PP_BOX_OUTSIDE_BLOCK,
        REASON_ENGINE_ERROR,
        REASON_BATCH_FAILED,
        REASON_GEOMETRY_INCONSISTENT,
    }
)

#: L2 判不出网格（页图上凑不出 ≥2 条竖线 + ≥2 条横线）。
#:
#: 这两个 reason **只进页级 ``diagnostics.l2``**，不进 ``summary.reason_counts``：那里的键是
#: PP 侧整表框的责任划分（覆盖率口径），掺进「本地线也没量到」会让「PP 漏了几块」失真。
REASON_RASTER_LINES_NO_GRID = "raster_lines_no_grid"

#: L2 量到了网格，但**文本归属证明不了**（行列数或 td 文本数与 MinerU HTML 网格不等）。
REASON_RASTER_LINES_NO_TEXT = "raster_lines_no_text"


class TableGeometryEngine(TableMeasureEngine, Protocol):
    """量**一批页**的引擎协议（PR-2 批量主路径）。

    ``measure_pdf`` 收子 PDF 字节，返回**逐页**的表结构：外层下标 = 送检页序
    （响应是 JSONL、一行 = 一页，见 ``facts/BATCH.md`` §1/§2）。返回项数与送检页数
    不等时调用方判「整批不可用」并回退单页裁图——**绝不**按序硬凑：错一页就整页格子
    画到别的页上，比没有框更糟。

    两条路径共用同一个 ``table_res_list`` 形状，所以对齐与配对只有一份代码。
    """

    def measure_pdf(self, pdf_bytes: bytes, *, page_count: int) -> list[list[dict[str, Any]]] | None: ...


# =====================================================================
# pass 层：选页 → 抽子 PDF 批量送 / 单页裁图兜底 → 配对 → 落产物
#
# 这一层会做 IO（读 PDF、调引擎、渲染裁图），坐标数学全部复用 ``table_geometry`` 的纯函数。
# 两条路径产出同一个 ``_TableCandidate`` 形状，配对与结构硬闸只有一份实现。
# =====================================================================


@dataclass(frozen=True)
class _CandidateBlock:
    """一个「值得量几何」的 table 块（候选判据见 ``_candidate_block``）。"""

    page_no: int
    block_index: int
    bbox: dict[str, float]
    html: str
    area: float


@dataclass(frozen=True)
class _CandidatePage:
    """一页的候选块 + 该页的排序权（候选块面积之和）。"""

    page_no: int
    blocks: tuple[_CandidateBlock, ...]
    area: float


@dataclass(frozen=True)
class _TableCandidate:
    """引擎量到的一张表，已换算成页面坐标（尚未与 MinerU 块配对）。"""

    index: int
    cells: tuple[TableCellBox, ...]
    rows: int
    cols: int
    pp_bbox: dict[str, float]
    text_source: str
    crop: tuple[float, float, float, float]
    crop_size: tuple[int, int]


def build_geometry_artifact(
    pages: Sequence[Any],
    *,
    pdf_path: Path,
    engine: TableGeometryEngine,
    bbox_backend: str,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    max_pages: int = DEFAULT_MAX_PAGES,
    local_lines_enabled: bool = False,
) -> dict[str, Any]:
    """几何 pass 的入口：候选表页 → 一次子 PDF 批量送 → 逐页配对 → 产物 dict。

    ``local_lines_enabled``：L2 本地线条兜底（默认 ``False`` = 今天的行为，一个字节都不多写）。
    开关的值由**调用方**从 ``table_geometry_switches.local_lines_enabled()`` 读了传进来 ——
    本模块不读开关（见模块 docstring）。

    ## 为什么是「子 PDF 批量」作为主路径

    单页裁图实测 7.2–32.5s/次，22 个候选页串行要 158–715s；把候选页拼成一个子 PDF
    一次送只要 **101.67s**（6 页 13.76s），便宜一个数量级（``facts/BATCH.md`` §0）。
    响应是 JSONL、**一行 = 一页、行序 = 送检页序**，所以整页送检时 ``crop`` 恒为
    ``(0,0,1,1)``、``crop_size`` 取该行的 ``prunedResult.width/height``，不需要裁图换算。

    ## 任何失败都只记 reason，不抛

    几何是**定位精度**的增强，不是正文的一部分：几何失败绝不能让分段失败。
    失败/超时/页数对齐不上 → 回退「前 6 页单页裁图」，其余页记 ``batch_failed``；
    页 ``/Rotate ≠ 0``、超 ``max_pages`` 的页整表框并留 reason。

    Returns:
        产物 dict（结构见 ``storage.table_geometry_json_path`` 的注释）::

            {"engine": "pp_structure_v3", "generated_at": "...", "summary": {...},
             "pages": {"10": {"tables": {"2": {...}}, "skipped": {}}}}
    """
    started = time.monotonic()
    unit = resolve_bbox_unit(bbox_backend)
    candidates = _candidate_pages(pages, unit=unit)
    artifact = _empty_artifact()
    summary = artifact["summary"]
    summary["pages_total"] = len(candidates)
    reasons: Counter[str] = Counter()
    processed: set[int] = set()

    if unit == "unknown" or not candidates:
        # 没有坐标系（本地 OCR / auto）就没有可比的块 bbox —— 不猜，也不写假几何
        summary["reason_counts"] = {REASON_NO_COORDINATES: 1} if unit == "unknown" else {}
        summary["duration_ms"] = _elapsed_ms(started)
        return artifact

    selected = candidates[:max_pages]
    summary["budget_exhausted"] = len(candidates) > max_pages
    for page in candidates[max_pages:]:
        _skip_page(artifact, page, reason=REASON_BUDGET_EXHAUSTED, reasons=reasons)

    rotations = _page_rotations(pdf_path, [page.page_no for page in selected])
    measurable: list[_CandidatePage] = []
    for page in selected:
        if rotations.get(page.page_no):
            # 旋转页的坐标无法在本仓内闭合验证（前端也不做旋转归一），按纪律整表框
            _skip_page(artifact, page, reason=REASON_ROTATION, reasons=reasons)
            continue
        measurable.append(page)

    if measurable:
        measured, failed, mode, exhausted = _measure_pages(
            measurable, pdf_path=pdf_path, engine=engine, budget_seconds=budget_seconds, started=started
        )
        summary["mode"] = mode
        summary["budget_exhausted"] = bool(summary["budget_exhausted"]) or exhausted
        for page in measurable:
            processed.add(page.page_no)
            _record_page(
                artifact,
                page,
                candidates=measured.get(page.page_no, []),
                failure_reason=failed.get(page.page_no),
                reasons=reasons,
            )
        if local_lines_enabled:
            # 配对全部落定后再跑 L2：它要看的正是「这一页/这一块到底有没有量到」
            _apply_local_lines(
                artifact,
                measurable,
                pdf_path=pdf_path,
                summary=summary,
                reasons=reasons,
                started=started,
                budget_seconds=budget_seconds,
            )

    _finish_summary(summary, artifact=artifact, reasons=reasons, processed=processed, started=started)
    return artifact


def geometries_by_page_block(artifact: Any) -> dict[int, dict[int, PageTableGeometry]]:
    """产物 → ``{页号: {block_index: PageTableGeometry}}``（``build_segments_markdown`` 的入参形态）。

    按 ``block_index`` 索引，而不是在定位层重算一次 IoU：配对是 pass 层的判断，
    产物已经把它钉死。在 markdown 层再配一次等于维护两套阈值，迟早给同一个块两个答案。

    ---- 坏产物（手改/旧版）一律逐条跳过
    """
    if not isinstance(artifact, dict):
        return {}
    pages = artifact.get("pages")
    if not isinstance(pages, dict):
        return {}

    result: dict[int, dict[int, PageTableGeometry]] = {}
    for page_key, page_payload in pages.items():
        page_no = _as_int(page_key)
        tables = page_payload.get("tables") if isinstance(page_payload, dict) else None
        if page_no is None or not isinstance(tables, dict):
            continue
        by_block: dict[int, PageTableGeometry] = {}
        for block_key, table_payload in tables.items():
            block_index = _as_int(block_key)
            geometry = _as_geometry(table_payload, page_no=page_no)
            if block_index is None or geometry is None:
                continue
            by_block[block_index] = geometry
        if by_block:
            result[page_no] = by_block
    return result


#: summary 里 ``table_geometry`` 区块的固定形状（关闭/缺产物时给零值，前端不用判 None）。
SUMMARY_KEYS: tuple[str, ...] = (
    "enabled",
    "mode",
    "engine",
    "pages_total",
    "pages_measured",
    "pages_failed",
    "pages_skipped",
    "reason_counts",
    "page_reason_counts",
    "duration_ms",
    "budget_exhausted",
    "cells_total",
    "tables_total",
    "cross_page_tables",
    "raster_lines_matched",
)


def summary_block(artifact: Any, *, enabled: bool) -> dict[str, Any]:
    """``summary.table_geometry`` 的拼装（三个调用点共用，避免口径漂移）。

    形状固定：即使开关关着、产物缺失，前端拿到的也是同一组键的零值 ——
    ``engine_disagreements`` 那次的经验（``service._dual_engine_summary``）：
    键时有时无会让前端为每种情况写一条分支。
    """
    block: dict[str, Any] = {
        "enabled": bool(enabled),
        "mode": "none",
        "engine": PP_STRUCTURE_ENGINE,
        "pages_total": 0,
        "pages_measured": 0,
        "pages_failed": 0,
        "pages_skipped": 0,
        "reason_counts": {},
        "page_reason_counts": {},
        "duration_ms": 0,
        "budget_exhausted": False,
        "cells_total": 0,
        "tables_total": 0,
        "cross_page_tables": 0,
        "raster_lines_matched": 0,
    }
    summary = artifact.get("summary") if isinstance(artifact, dict) else None
    if isinstance(summary, dict):
        block.update({key: summary[key] for key in SUMMARY_KEYS if key in summary and key != "enabled"})
    return block


# ── 真实引擎（本模块唯一碰网络的地方）────────────────────────────


def _table_payload(table: Any) -> dict[str, Any]:
    """``paddleocr_api_service.ParsedTableResult`` → 本模块认识的表结构。

    只搬运原样字段（像素框 + HTML + 行级 OCR），不做任何换算或过滤：换算在
    ``build_cell_boxes``/``assign_cell_texts``，过滤在解析层已经做过一遍。
    """
    image_size = table.image_size
    return {
        "cell_box_list": [list(box) for box in table.cell_boxes],
        "pred_html": table.html,
        "image_size": list(image_size) if image_size else None,
        "table_ocr_pred": {
            "rec_texts": list(table.texts),
            "rec_boxes": [list(box) for box in table.text_boxes],
        },
    }


class PaddleTableGeometryEngine:
    """把 ``PaddleOCRApiEngine(model="pp_structure_v3")`` 包成量表格的引擎。

    为什么复用 ``PaddleOCRApiEngine`` 而不是另写一个客户端：凭证池轮询/失败冷却/重试
    都在那里面（``dual_engine_runner`` 也是这么复用的，只换 model）。本类只做两件事：
    ① 把裁图/子 PDF 的字节递进去；② 把 ``ParsedTableResult`` 摊成纯 dict。

    ``measure``（单页裁图）与 ``measure_pdf``（批量）返回**同一种表的形状**，所以
    对齐与配对只有一份代码。
    """

    def __init__(self, *, api_engine: Any = None) -> None:
        self._api_engine = api_engine

    @property
    def engine(self) -> Any:
        """延迟构造真实引擎：只在真的要发请求时才去读配置。"""
        if self._api_engine is None:
            from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

            self._api_engine = PaddleOCRApiEngine(model=PP_STRUCTURE_ENGINE)
        return self._api_engine

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]] | None:
        result = self.engine.recognize_bytes(image_bytes, is_pdf=False)
        return [_table_payload(table) for table in result.tables]

    def measure_pdf(self, pdf_bytes: bytes, *, page_count: int) -> list[list[dict[str, Any]]] | None:
        result = self.engine.recognize_bytes(pdf_bytes, is_pdf=True, page_count=page_count)
        return [[_table_payload(table) for table in page] for page in result.table_pages]


# ── 选页 / 量测 / 兜底 ──────────────────────────────────────────


def _candidate_pages(pages: Sequence[Any], *, unit: str) -> list[_CandidatePage]:
    """候选表页（按表块面积降序）：表块高 ≥ 0.18 且 HTML ``<tr>`` ≥ 2。

    判据与 ``markdown_builder._TABLE_SPLIT_MIN_HEIGHT_RATIO`` **是同一个数**：候选页
    比拆格门槛宽或窄，都会出现「量了却不拆」或「要拆却没量」的漂移。用局部 import
    引那一个常量：import 方向保持定位层（``markdown_builder``）→ 纯数学层，pass 层
    不在模块级反向拖入定位层的导入链。
    """
    if unit == "unknown":
        return []
    grouped: dict[int, list[_CandidateBlock]] = {}
    for page in pages:
        layout = getattr(page, "layout", None)
        page_no = getattr(page, "page_no", None)
        if not isinstance(layout, dict) or not isinstance(page_no, int):
            continue
        blocks = layout.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block_index, block in enumerate(blocks):
            candidate = _candidate_block(block, page_no=page_no, block_index=block_index, layout=layout, unit=unit)
            if candidate is not None:
                grouped.setdefault(page_no, []).append(candidate)
    pages_out = [
        _CandidatePage(page_no=page_no, blocks=tuple(blocks), area=sum(block.area for block in blocks))
        for page_no, blocks in grouped.items()
    ]
    return sorted(pages_out, key=lambda page: (-page.area, page.page_no))


def _candidate_block(
    block: Any, *, page_no: int, block_index: int, layout: dict[str, Any], unit: str
) -> _CandidateBlock | None:
    """一个版面块 → 候选（不是 table / HTML 行数 < 2 / 不够高 / 无 bbox 都不算）。"""
    from .markdown_builder import _TABLE_SPLIT_MIN_HEIGHT_RATIO

    if not isinstance(block, dict) or str(block.get("type") or "").strip().lower() != "table":
        return None
    html = block_table_html(block)
    if _grid_row_count(html) < 2:
        return None
    rect = normalize_bbox(
        block.get("bbox"), unit=unit, page_width=layout.get("width"), page_height=layout.get("height")
    )
    if rect is None or float(rect["h"]) < _TABLE_SPLIT_MIN_HEIGHT_RATIO:
        return None
    bbox = {"x": float(rect["x"]), "y": float(rect["y"]), "w": float(rect["w"]), "h": float(rect["h"])}
    return _CandidateBlock(
        page_no=page_no,
        block_index=block_index,
        bbox=bbox,
        html=html,
        area=bbox["w"] * bbox["h"],
    )


def _measure_pages(
    pages: Sequence[_CandidatePage],
    *,
    pdf_path: Path,
    engine: TableGeometryEngine,
    budget_seconds: float,
    started: float,
) -> tuple[dict[int, list[_TableCandidate]], dict[int, str], str, bool]:
    """量这些页：先批量，批量不可用再回退前 6 页单页裁图。

    Returns:
        ``(页号 → 表, 页号 → 失败原因, mode, budget_exhausted)``。
        ``mode`` 取 ``"batch"``（一次子 PDF 送成）或 ``"per_page"``（回退了单页裁图）。
    """
    page_numbers = [page.page_no for page in pages]
    batch = _measure_batch(pdf_path, page_numbers=page_numbers, engine=engine)
    if batch is None:
        return _measure_pages_one_by_one(
            pages, pdf_path=pdf_path, engine=engine, budget_seconds=budget_seconds, started=started
        )
    measured: dict[int, list[_TableCandidate]] = {}
    failures: dict[int, str] = {}
    for page_no, tables in zip(page_numbers, batch, strict=True):
        candidates, failure = _candidates_from_tables(tables, page_no=page_no)
        measured[page_no] = candidates
        if failure is not None:
            failures[page_no] = failure
    return measured, failures, "batch", False


def _measure_pages_one_by_one(
    pages: Sequence[_CandidatePage],
    *,
    pdf_path: Path,
    engine: TableMeasureEngine,
    budget_seconds: float,
    started: float,
) -> tuple[dict[int, list[_TableCandidate]], dict[int, str], str, bool]:
    """单页裁图兜底：只跑前 ``_FALLBACK_MAX_PAGES`` 页，且预算用完就停。"""
    measured: dict[int, list[_TableCandidate]] = {}
    failed: dict[int, str] = {}
    budget_exhausted = False
    for index, page in enumerate(pages):
        if index >= _FALLBACK_MAX_PAGES:
            failed[page.page_no] = REASON_BATCH_FAILED
            continue
        if _remaining_seconds(started=started, budget_seconds=budget_seconds) <= 0:
            budget_exhausted = True
            failed[page.page_no] = REASON_BUDGET_EXHAUSTED
            continue
        geometry = _measure_page_crop(pdf_path, page=page, engine=engine)
        if geometry is None:
            # 裁图路径把「引擎报错」与「引擎不出表」都降级成 None（PR-1 语义）；
            # 这里按「这一页没有可用表」处理，块的 reason 由伪表判据再分一次。
            measured[page.page_no] = []
            continue
        measured[page.page_no] = _candidates_from_geometry(geometry)
    return measured, failed, "per_page", budget_exhausted


def _measure_batch(
    pdf_path: Path, *, page_numbers: Sequence[int], engine: TableGeometryEngine
) -> list[list[dict[str, Any]]] | None:
    """子 PDF 一次送；任何失败/对齐不上都返回 ``None``（调用方回退单页裁图）。"""
    try:
        pdf_bytes = _slice_pdf(pdf_path, page_numbers)
    except (RuntimeError, ValueError, OSError):
        logger.warning("pdf_split_table_geometry_slice_failed", extra={"pdf_path": pdf_path.as_posix()})
        return None
    try:
        response = engine.measure_pdf(pdf_bytes, page_count=len(page_numbers))
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        logger.warning(
            "pdf_split_table_geometry_batch_failed",
            extra={"pages": len(page_numbers), "error": str(exc)},
        )
        return None
    if not isinstance(response, list) or len(response) != len(page_numbers):
        # 行数 ≠ 送检页数 ⇒ 行序对齐不成立。按序硬凑会把 A 页的格子画到 B 页上。
        logger.warning(
            "pdf_split_table_geometry_batch_unaligned",
            extra={"pages": len(page_numbers), "rows": _length_of(response)},
        )
        return None
    return [[table for table in page if isinstance(table, dict)] for page in response]


def _slice_pdf(pdf_path: Path, page_numbers: Sequence[int]) -> bytes:
    """只含这些页的子 PDF，**按传入页序**（页序就是服务端 JSONL 的行序）。"""
    target = fitz.open()
    try:
        with fitz.open(pdf_path) as source:
            for page_no in page_numbers:
                target.insert_pdf(source, from_page=page_no - 1, to_page=page_no - 1)
        return target.tobytes()  # type: ignore[no-any-return]
    finally:
        target.close()


def _page_rotations(pdf_path: Path, page_numbers: Sequence[int]) -> dict[int, int]:
    """各页的 ``/Rotate``；读不到就按 0 处理（不因为读不到旋转就放弃整批几何）。"""
    try:
        with fitz.open(pdf_path) as doc:
            return {
                page_no: int(doc[page_no - 1].rotation or 0)
                for page_no in page_numbers
                if 1 <= page_no <= int(doc.page_count)
            }
    except (RuntimeError, ValueError, OSError):
        logger.warning("pdf_split_table_geometry_rotation_unreadable", extra={"pdf_path": pdf_path.as_posix()})
        return {}


def _measure_page_crop(pdf_path: Path, *, page: _CandidatePage, engine: TableMeasureEngine) -> PageTableGeometry | None:
    """单页兜底：本页候选块的并集裁出来送一次（复用 PR-1 的 ``measure_table_crop``）。"""
    crop = _union_crop(page.blocks)
    try:
        with fitz.open(pdf_path) as doc:
            page_obj = doc[page.page_no - 1]
            page_rect = page_obj.rect
            clip = fitz.Rect(
                crop[0] * page_rect.width,
                crop[1] * page_rect.height,
                crop[2] * page_rect.width,
                crop[3] * page_rect.height,
            )
            scale = _FALLBACK_CROP_DPI / 72
            pixmap = page_obj.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
            image_bytes = pixmap.tobytes("png")
            crop_size = (int(pixmap.width), int(pixmap.height))
    except (RuntimeError, ValueError, OSError, IndexError):
        logger.warning("pdf_split_table_geometry_crop_render_failed", extra={"page": page.page_no})
        return None
    return measure_table_crop(image_bytes, page_no=page.page_no, crop=crop, engine=engine, crop_size=crop_size)


def _union_crop(blocks: Sequence[_CandidateBlock]) -> tuple[float, float, float, float]:
    """候选块的并集 + 外扩 0.005 页/边（同 ``facts/raw/collect_crop.py``），夹到 0–1。"""
    left = min(block.bbox["x"] for block in blocks) - _CROP_MARGIN_RATIO
    top = min(block.bbox["y"] for block in blocks) - _CROP_MARGIN_RATIO
    right = max(block.bbox["x"] + block.bbox["w"] for block in blocks) + _CROP_MARGIN_RATIO
    bottom = max(block.bbox["y"] + block.bbox["h"] for block in blocks) + _CROP_MARGIN_RATIO
    return (_clamp01(left), _clamp01(top), _clamp01(right), _clamp01(bottom))


def _candidates_from_tables(
    tables: Sequence[dict[str, Any]], *, page_no: int
) -> tuple[list[_TableCandidate], str | None]:
    """一页的引擎表 → ``(候选表, 第一个失败原因)``；整页一张也建不出来时原因才有意义。"""
    candidates: list[_TableCandidate] = []
    failure: str | None = None
    for table in tables:
        candidate, reason = _table_candidate(table, page_no=page_no, index=len(candidates))
        if candidate is None:
            failure = failure or reason
            continue
        candidates.append(candidate)
    return candidates, (failure if not candidates else None)


def _table_candidate(table: dict[str, Any], *, page_no: int, index: int) -> tuple[_TableCandidate | None, str | None]:
    """一张引擎表 → 页面坐标的候选（整页送检，``crop`` 恒为 ``(0,0,1,1)``）。"""
    crop_size = _as_size(table.get("image_size"))
    if crop_size is None:
        # 没有该页的栅格尺寸就无法把裁图像素换算成页面坐标 —— 宁可整表框也不猜
        logger.warning("pdf_split_table_geometry_no_crop_size", extra={"page": page_no})
        return None, REASON_ENGINE_ERROR
    # 引擎返回值不可能有静态类型：形状由 build_cell_boxes 内部逐项校验（非法项直接丢）
    raw_boxes: Any = table.get("cell_box_list")
    expected_rows, expected_cols = html_grid_shape(table.get("pred_html"))
    cells = build_cell_boxes(
        raw_boxes,
        crop=_FULL_PAGE_CROP,
        crop_size=crop_size,
        expected_cols=expected_cols,
        expected_rows=expected_rows,
    )
    if not cells:
        # 有合法框却产不出格子 = 行列聚类判了“不可信”（见 build_cell_boxes）；
        # 一个合法框都没有才是真正的 empty_cells。两种原因必须分开报：
        # 前者要评估几何算法，后者要评估引擎召回。
        has_boxes = bool(_valid_pixel_rects(raw_boxes))
        return None, REASON_GEOMETRY_INCONSISTENT if has_boxes else REASON_EMPTY_CELLS
    cells, text_source = assign_cell_texts(
        cells, lines=_ocr_lines(table.get("table_ocr_pred")), crop=_FULL_PAGE_CROP, crop_size=crop_size
    )
    rows, cols = grid_shape(cells)
    return (
        _TableCandidate(
            index=index,
            cells=cells,
            rows=rows,
            cols=cols,
            pp_bbox=_union_rect(cells),
            text_source=text_source,
            crop=_FULL_PAGE_CROP,
            crop_size=crop_size,
        ),
        None,
    )


def _candidates_from_geometry(geometry: PageTableGeometry) -> list[_TableCandidate]:
    """单页兜底路径：``measure_table_crop`` 已给出页面坐标，这里只补派生 bbox。"""
    return [
        _TableCandidate(
            index=0,
            cells=geometry.cells,
            rows=geometry.rows,
            cols=geometry.cols,
            pp_bbox=_union_rect(geometry.cells),
            text_source=str(geometry.diagnostics.get("text_source") or "none"),
            crop=geometry.crop,
            crop_size=_as_size(geometry.diagnostics.get("crop_size")) or (0, 0),
        )
    ]


# ── 逐页配对与产物条目 ──────────────────────────────────────────


def _record_page(
    artifact: dict[str, Any],
    page: _CandidatePage,
    *,
    candidates: Sequence[_TableCandidate],
    failure_reason: str | None,
    reasons: Counter[str],
) -> None:
    """一页的配对结果写进产物：配上的进 ``tables``，配不上的进 ``skipped``（带 reason）。"""
    if not candidates:
        # 引擎这一页一张表都没给出：区分「真表被漏检」(no_table_detected) 与「伪表」(pseudo_table)
        no_table_skipped: dict[str, str] = {}
        for block in page.blocks:
            reason = failure_reason or _no_table_reason(block)
            no_table_skipped[str(block.block_index)] = reason
            reasons[reason] += 1
        artifact["pages"][str(page.page_no)] = {"tables": {}, "skipped": no_table_skipped}
        return

    matches = match_tables_to_blocks(
        [block.bbox for block in page.blocks],
        [candidate.pp_bbox for candidate in candidates],
        # 候选列表的位置 ≠ 版面块下标：p10 的表格是版面第 3 块（下标 2），候选列表里却是第 1 个
        block_indices=[block.block_index for block in page.blocks],
    )
    if matches.orphan_tables:
        # 裁图外/误检的 PP 表：不造成错框，但必须计数（静默丢表＝事后无从解释）
        reasons[REASON_ORPHAN_PP_TABLE] += len(matches.orphan_tables)
        logger.warning(
            "pdf_split_table_geometry_orphan_pp_table",
            extra={"page": page.page_no, "tables": list(matches.orphan_tables)},
        )

    tables: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for block in page.blocks:
        match = matches.by_block.get(block.block_index) or TableMatch(
            block_index=block.block_index, table_index=None, iou=0.0, margin=0.0, reason=REASON_UNMATCHED_PP_TABLE
        )
        table_index = match.table_index
        if table_index is None:
            skipped[str(block.block_index)] = match.reason
            reasons[match.reason] += 1
            continue
        reason = _table_reject_reason(candidates[table_index], block)
        if reason is not None:
            skipped[str(block.block_index)] = reason
            reasons[reason] += 1
            continue
        tables[str(block.block_index)] = _table_entry(candidates[table_index], match=match, block=block)
    artifact["pages"][str(page.page_no)] = {"tables": tables, "skipped": skipped}


def _table_reject_reason(candidate: _TableCandidate, block: _CandidateBlock) -> str | None:
    """配上的表在这个块上能不能用 → 整表框原因（``None`` = 能用）。

    三种原因责任方不同，分开记：列数对不上 ``pp_shape_mismatch``、PP 框越界
    ``pp_box_outside_block``、格位重叠 ``geometry_inconsistent``。
    """
    html_cols = _grid_col_count(_parse_grid(block.html))
    if candidate.cols != html_cols:
        # 列数只能来自几何本身；对不上说明这张 PP 表不是这个块（或裂得对不齐），
        # 拿它定位会把格子横向整体铺错。
        logger.warning(
            "pdf_split_table_geometry_columns_mismatch",
            extra={"page": block.page_no, "block": block.block_index, "cols": candidate.cols, "html_cols": html_cols},
        )
        return REASON_PP_SHAPE_MISMATCH
    return structural_check(candidate.cells, block_bbox=block.bbox)


def _table_entry(
    candidate: _TableCandidate, *, match: TableMatch, block: _CandidateBlock, engine: str | None = None
) -> dict[str, Any]:
    """一张配上块的表 → 产物条目（含派生 bbox、配对结果、诊断）。

    ``engine`` 只由 L2 填（``raster_lines``）：PP 条目不带这个键，所以开关关着时产物
    与今天逐字节相同；两源事后必须能分开统计（失败模式完全不同）。
    """
    html_rows = _grid_row_count(block.html)
    html_cols = _grid_col_count(_parse_grid(block.html))
    entry: dict[str, Any] = {
        "rows": candidate.rows,
        "cols": candidate.cols,
        "cells": [_cell_payload(cell) for cell in candidate.cells],
        "crop": [round(value, _RECT_PRECISION) for value in candidate.crop],
        "block_index": block.block_index,
        "pp_bbox": candidate.pp_bbox,
        "match": {
            "block_index": match.block_index,
            "table_index": match.table_index,
            "iou": match.iou,
            "margin": match.margin,
            "reason": match.reason,
        },
        "diagnostics": {
            "text_source": candidate.text_source,
            "cell_count": len(candidate.cells),
            "crop_size": [candidate.crop_size[0], candidate.crop_size[1]],
            "html_row_count": html_rows,
            "html_col_count": html_cols,
            # 行列数与本页 HTML 不一致 = 跨页逻辑表（p10 的 MinerU 多出物理在 p11 的那一行）：
            # 定位只用几何里的行（本页可见），正文不变。
            "cross_page": (candidate.rows != html_rows) or (candidate.cols != html_cols),
        },
    }
    if engine is not None:
        entry["engine"] = engine
    return entry


def _cell_payload(cell: TableCellBox) -> dict[str, Any]:
    return {
        "text": cell.text,
        "row": cell.row,
        "col": cell.col,
        "row_span": cell.row_span,
        "col_span": cell.col_span,
        "rect": dict(cell.rect),
    }


def _skip_page(artifact: dict[str, Any], page: _CandidatePage, *, reason: str, reasons: Counter[str]) -> None:
    """整页不量（旋转/超上限）：每个候选块都留一条 reason。"""
    for block in page.blocks:
        reasons[reason] += 1
    artifact["pages"][str(page.page_no)] = {
        "tables": {},
        "skipped": {str(block.block_index): reason for block in page.blocks},
    }


def _no_table_reason(block: _CandidateBlock) -> str:
    """引擎没出表时，这张块是「真表被漏检」还是「伪表」（DESIGN §8 的判定顺序）。

    判据复用 ``markdown_builder._SPLIT_MAX_CELL_AREA_RATIO``（0.04）：实测伪表 p29
    单格占页 10.9%，真表最大 1.61%（``facts/FACTS.md`` SF-15），两侧各 ≥2.5× 余量。
    两者行为相同（都整表框），但决策不同：前者是覆盖率缺口，后者本来就不该画格。
    """
    from .markdown_builder import _SPLIT_MAX_CELL_AREA_RATIO

    positions = _grid_row_count(block.html) * _grid_col_count(_parse_grid(block.html))
    if positions <= 0:
        return REASON_PSEUDO_TABLE
    return REASON_PSEUDO_TABLE if block.area / positions > _SPLIT_MAX_CELL_AREA_RATIO else REASON_NO_TABLE_DETECTED


# ── PP 没量到时的兜底：本地线条投影（L2，默认关）─────────────────


def _apply_local_lines(
    artifact: dict[str, Any],
    pages: Sequence[_CandidatePage],
    *,
    pdf_path: Path,
    summary: dict[str, Any],
    reasons: Counter[str],
    started: float,
    budget_seconds: float,
) -> None:
    """PP 一张表也没量到的页：退到本地线条（L2），能证明文本归属才换成格子。

    ## 三道门槛（缺一条都只是「画得很好看的错框」）

    1. 该页 ``tables`` 为空 —— PP 已经量到的页**绝不**跑 L2：两个源在同一页各画一套格子，
       用户看到的绿框会随引擎可用性漂移；
    2. 该块的整表框原因 ∈ ``_LOCAL_LINES_TRIGGER_REASONS``（真表被漏检/引擎坏掉那一类），
       且块 bbox 可用（退化矩形不猜）；
    3. 量到的行×列 == MinerU HTML 展开后的行×列，且 td 文本数 == 行×列 → 否则不出格子：
       L2 没有 ``pred_html``，证明不了「第 N 个文本属于第 N 格」时，空文本格子会让右栏
       出现空白块，比整表框更糟。

    预算/页数上限沿用 PP 侧那一套（``started`` 是 pass 入口的时刻，``max_pages`` 已在上游卡过）。
    """
    matched = 0
    for page in pages:
        payload = artifact["pages"].get(str(page.page_no))
        if payload is None or payload["tables"]:
            continue
        skipped = payload["skipped"]
        targets = [
            block for block in page.blocks if skipped.get(str(block.block_index)) in _LOCAL_LINES_TRIGGER_REASONS
        ]
        if not targets:
            continue
        if _remaining_seconds(started=started, budget_seconds=budget_seconds) <= 0:
            _record_l2_diagnostics(payload, targets, reason=REASON_BUDGET_EXHAUSTED)
            continue
        image_bytes = _render_page_image(pdf_path, page_no=page.page_no)
        if image_bytes is None:
            _record_l2_diagnostics(payload, targets, reason=REASON_RASTER_LINES_NO_GRID)
            continue
        # 整页图只渲染/解码一次，同页多块共用这一张（每块重渲 = 白等 0.1–0.3s/块）
        matched += _local_lines_blocks(payload, targets, image_bytes=image_bytes, reasons=reasons)
    summary["raster_lines_matched"] = matched


def _local_lines_blocks(
    payload: dict[str, Any], blocks: Sequence[_CandidateBlock], *, image_bytes: bytes, reasons: Counter[str]
) -> int:
    """在这几个块上量本地线网格：量到且文本可证就换成格子，否则只留页级诊断。

    Returns:
        换成格子（并撤回原先整表框原因）的块数。
    """
    diagnostics: dict[str, Any] = {}
    matched = 0
    for block in blocks:
        key = str(block.block_index)
        region = _block_region(block)
        if region is None:
            diagnostics[key] = {"reason": REASON_RASTER_LINES_NO_GRID}
            continue
        grid = detect_grid_from_png(image_bytes, region=region)
        if grid is None:
            diagnostics[key] = {"reason": REASON_RASTER_LINES_NO_GRID}
            continue
        detail: dict[str, Any] = {
            "col_lines": grid.diagnostics.get("col_lines"),
            "row_lines": grid.diagnostics.get("row_lines"),
        }
        html_rows, html_cols, texts = _html_grid(block)
        if (grid.rows, grid.cols) != (html_rows, html_cols) or len(texts) != html_rows * html_cols:
            diagnostics[key] = {
                "reason": REASON_RASTER_LINES_NO_TEXT,
                **detail,
                "grid": [grid.rows, grid.cols],
                "html_grid": [html_rows, html_cols],
                "html_texts": len(texts),
            }
            continue
        geometry = cells_from_grid(grid, page_no=block.page_no, texts=texts)
        payload["tables"][key] = _raster_lines_entry(geometry, block=block, grid=grid)
        _uncount_reason(reasons, payload["skipped"].pop(key, None))
        matched += 1
    if diagnostics:
        payload.setdefault("diagnostics", {})["l2"] = diagnostics
    return matched


def _record_l2_diagnostics(payload: dict[str, Any], blocks: Sequence[_CandidateBlock], *, reason: str) -> None:
    """整块放弃（图渲染失败 / 预算用完）时给每个块留一条页级诊断（不进 summary.reason_counts）。"""
    payload.setdefault("diagnostics", {})["l2"] = {str(block.block_index): {"reason": reason} for block in blocks}


def _raster_lines_entry(geometry: PageTableGeometry, *, block: _CandidateBlock, grid: RasterGrid) -> dict[str, Any]:
    """L2 量到的网格 → 产物条目（与 PP 条目同形：多一个 ``engine`` 与 ``diagnostics.l2``）。"""
    candidate = _TableCandidate(
        index=0,
        cells=geometry.cells,
        rows=geometry.rows,
        cols=geometry.cols,
        pp_bbox=geometry.pp_bbox or block.bbox,
        text_source=str(geometry.diagnostics.get("text_source") or "none"),
        crop=geometry.crop,
        crop_size=_as_size(grid.diagnostics.get("image_size")) or (0, 0),
    )
    # 配对是自证的：网格就是从这块的 bbox 里量出来的，没有第二张表可配
    match = TableMatch(block_index=block.block_index, table_index=None, iou=0.0, margin=0.0, reason=REASON_MATCHED)
    entry = _table_entry(candidate, match=match, block=block, engine=LOCAL_LINE_ENGINE)
    entry["diagnostics"]["l2"] = {
        "col_lines": grid.diagnostics.get("col_lines"),
        "row_lines": grid.diagnostics.get("row_lines"),
        "reason": grid.diagnostics.get("reason"),
    }
    return entry


def _html_grid(block: _CandidateBlock) -> tuple[int, int, list[str]]:
    """块 HTML 展开后的 ``(rows, cols, td 文本)``（``parse_grid`` 已按 rowspan/colspan 占位）。

    ``rows * cols`` 是**真实格位数**，``len(texts)`` 是 ``<td>`` 个数：两者相等才说明
    没有合并单元格，此时 ``texts`` 的先后顺序就是 row-major 的格位顺序。不等时调用方
    只能放弃（有合并单元格时展开后的 td 数 < 格位数，按下标贴必定错位）。
    """
    grid = _parse_grid(block.html)
    return _grid_row_count(block.html), _grid_col_count(grid), [text for _row, _col, _rs, _cs, text in grid]


def _block_region(block: _CandidateBlock) -> tuple[float, float, float, float] | None:
    """块 bbox → 页面归一化区域 ``(x0, y0, x1, y1)``；退化矩形返回 ``None``。

    外扩由 L2 自己按像素做（``table_geometry_lines.REGION_PAD_PX=6``，同 ``_union_crop``
    的 0.005 页同量级），这里只负责把 ``{x,y,w,h}`` 换成两角坐标并夹到页内。
    """
    left, top = _clamp01(block.bbox["x"]), _clamp01(block.bbox["y"])
    right, bottom = _clamp01(block.bbox["x"] + block.bbox["w"]), _clamp01(block.bbox["y"] + block.bbox["h"])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _render_page_image(pdf_path: Path, *, page_no: int) -> bytes | None:
    """整页 150dpi **灰度** PNG 字节（L2 的输入）；渲染不出来返回 ``None``。

    返回字节而不是数组：``detect_grid_from_png`` 自己解成灰度，本层不必引入 numpy。
    同页多块必须复用同一份（见 ``_apply_local_lines``）。
    """
    scale = _LOCAL_LINES_RENDER_DPI / 72
    try:
        with fitz.open(pdf_path) as doc:
            pixmap = doc[page_no - 1].get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY)
            return pixmap.tobytes("png")  # type: ignore[no-any-return]
    except (RuntimeError, ValueError, OSError, IndexError):
        logger.warning("pdf_split_table_geometry_page_render_failed", extra={"page": page_no})
        return None


def _uncount_reason(reasons: Counter[str], reason: str | None) -> None:
    """L2 换上格子后撤回该块先前的整表框原因（保持 ``sum(reason_counts) == len(skipped)``）。"""
    if reason is None:
        return
    reasons[reason] -= 1
    if reasons[reason] <= 0:
        del reasons[reason]


# ── 产物与摘要的零碎 ────────────────────────────────────────────


def _empty_artifact() -> dict[str, Any]:
    return {
        "engine": PP_STRUCTURE_ENGINE,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "mode": "none",
            "pages_total": 0,
            "pages_measured": 0,
            "pages_failed": 0,
            "pages_skipped": 0,
            "reason_counts": {},
            "page_reason_counts": {},
            "duration_ms": 0,
            "budget_exhausted": False,
            "cells_total": 0,
            "tables_total": 0,
            "cross_page_tables": 0,
            "raster_lines_matched": 0,
        },
        "pages": {},
    }


def _finish_summary(
    summary: dict[str, Any],
    *,
    artifact: dict[str, Any],
    reasons: Counter[str],
    processed: set[int],
    started: float,
) -> None:
    """把逐页产物回填进 summary：数字必须与 ``pages`` 一一对得上（对不上就是统计 bug）。"""
    entries = [entry for page in artifact["pages"].values() for entry in page["tables"].values()]
    measured_pages = {int(key) for key, page in artifact["pages"].items() if page["tables"]}
    summary["tables_total"] = len(entries)
    summary["cells_total"] = sum(len(entry["cells"]) for entry in entries)
    summary["cross_page_tables"] = sum(1 for entry in entries if entry["diagnostics"]["cross_page"])
    summary["pages_measured"] = len(measured_pages)
    summary["pages_skipped"] = summary["pages_total"] - len(processed)
    summary["pages_failed"] = len(processed - measured_pages)
    summary["reason_counts"] = dict(sorted(reasons.items()))
    # 页级计数：``reason_counts`` 数是**整表框个数**（一页两块可以两个原因），
    # 而“每个失败页都有原因”这条只能用页级口径验 —— 两者单位不同，不能相加对比。
    summary["page_reason_counts"] = _page_reason_counts(artifact, processed=processed)
    summary["duration_ms"] = _elapsed_ms(started)


def _page_reason_counts(artifact: dict[str, Any], *, processed: set[int]) -> dict[str, int]:
    """每个**失败页**记一条原因（取该页版面下标最小的那个块的 reason），供口径校验用。"""
    counts: Counter[str] = Counter()
    for key, page in artifact["pages"].items():
        page_no = _as_int(key)
        if page_no is None or page_no not in processed or page["tables"]:
            continue
        skipped = page["skipped"]
        if not skipped:
            continue
        # 取版面下标最小的那个块的 reason：同一页两块可能原因不同，页级只记最靠前的一条
        first_block = min(skipped, key=lambda item: _block_sort_key(item))
        counts[skipped[first_block]] += 1
    return dict(sorted(counts.items()))


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _remaining_seconds(*, started: float, budget_seconds: float) -> float:
    return float(budget_seconds) - (time.monotonic() - started)


def _as_size(raw: Any) -> tuple[int, int] | None:
    """``[width, height]`` → 正整数对；缺失/非法返回 ``None``。"""
    values = _as_floats(raw, axes=_SIZE_AXES)
    if values is None or values[0] <= 0 or values[1] <= 0:
        return None
    return (int(values[0]), int(values[1]))


def _block_sort_key(raw: Any) -> int:
    """版面块下标的排序键（``"2"`` 按 2 排，脏键排最后）。"""
    value = _as_int(raw)
    return value if value is not None else sys.maxsize


def _as_int(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _as_float(raw: Any) -> float | None:
    """单个数值；转不了或不是有限数返回 ``None``。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _as_geometry(payload: Any, *, page_no: int) -> PageTableGeometry | None:
    """产物条目 → ``PageTableGeometry``；坏条目（缺 cells/行列）返回 ``None``。"""
    if not isinstance(payload, dict):
        return None
    cells = tuple(cell for cell in (_as_cell_box(item) for item in payload.get("cells") or []) if cell is not None)
    rows = _as_int(payload.get("rows"))
    cols = _as_int(payload.get("cols"))
    if not cells or rows is None or cols is None:
        return None
    crop = _as_floats(payload.get("crop"), axes=_BOX_AXES)
    diagnostics = payload.get("diagnostics")
    engine = payload.get("engine")
    return PageTableGeometry(
        page_no=page_no,
        engine=engine if isinstance(engine, str) and engine else PP_STRUCTURE_ENGINE,
        rows=rows,
        cols=cols,
        cells=cells,
        crop=(crop[0], crop[1], crop[2], crop[3]) if crop is not None else _FULL_PAGE_CROP,
        diagnostics=dict(diagnostics) if isinstance(diagnostics, dict) else {},
        pp_bbox=payload.get("pp_bbox") if isinstance(payload.get("pp_bbox"), dict) else None,
        match=payload.get("match") if isinstance(payload.get("match"), dict) else None,
    )


def _as_cell_box(payload: Any) -> TableCellBox | None:
    """产物里的一个格子 → ``TableCellBox``；字段缺失/类型不对返回 ``None``。"""
    if not isinstance(payload, dict):
        return None
    rect = payload.get("rect")
    row, col = _as_int(payload.get("row")), _as_int(payload.get("col"))
    if not isinstance(rect, dict) or row is None or col is None:
        return None
    values = {key: _as_float(rect.get(key)) for key in ("x", "y", "w", "h")}
    if any(value is None for value in values.values()):
        return None
    return TableCellBox(
        text=str(payload.get("text") or ""),
        row=row,
        col=col,
        row_span=max(1, _as_int(payload.get("row_span")) or 1),
        col_span=max(1, _as_int(payload.get("col_span")) or 1),
        rect={key: value for key, value in values.items() if value is not None},
    )


#: 整页送检时的裁图区域：批量路径不需要裁图换算，恒为整页。
_FULL_PAGE_CROP: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
