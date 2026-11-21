"""表格格子几何：把 OCR **量到**的像素框换成页面归一化矩形与真实行列网格。

## 这是量出来的几何，不是推算出来的

改造前，格子框是「表格 bbox ÷ 行列数」均分推出来的（``markdown_builder.py:376-377``），
列宽不等时整块框会指到隔壁列（p10 的「件数」列偏 **0.185 页宽 ≈ 110pt**）。
本模块的输入是引擎**实测**的每条表格线围出来的格子，不做任何均分假设。

## 数据来源与坐标口径

- 来源：PP-StructureV3 响应 ``result["layoutParsingResults"][i]["prunedResult"]["table_res_list"][j]``
  的 ``cell_box_list``（每个格子 ``[x0, y0, x1, y1]``），量纲是**同一 ``prunedResult`` 的
  ``width``/``height``**，也就是「送进引擎那张**裁图**」的像素坐标，不是页面坐标。
- 裁图 → 页面的换算与既有 ``ocr_handler._rescale_region_blocks()``（``ocr_handler.py:201-223``）
  同一数学，只是这里用归一化版::

      x = cx0 + (px / crop_w_px) * (cx1 - cx0)
      y = cy0 + (py / crop_h_px) * (cy1 - cy0)

  ``(cx0, cy0, cx1, cy1)`` 必须是**裁图时实际用的**归一化区域，不能假定等于表格 bbox：
  p10 两者差 0.026 页宽（＝列边界容差 0.004 的 6 倍）。所以它随
  ``PageTableGeometry.crop`` 一起落进产物，事后可复算。
- 产物口径：页面归一化 0–1 的 ``{"x","y","w","h"}``，与 ``bbox.normalize_bbox`` /
  ``api/pdf_splitting_api.PositionedRectOut`` 同口径（前端 ``left: x*100%``）。

## 纪律：宁可少画一个框，也不能画错一个框

量不到、量不准、参数不成立 → 返回 ``None`` / 空元组并 ``logger.warning``，
**绝不**编一个默认坐标（同 ``bbox.py:31-33``）。调用方拿到空就退回整表框。

## 两层，不要混

| 层 | 内容 | 能不能做 IO |
|:--|:--|:--|
| 数学/判定（本文件上半） | ``map_pixel_rect`` / ``build_cell_boxes`` / ``assign_cell_texts`` / ``structural_check`` / ``match_tables_to_blocks`` / ``grid_shape`` | **不能**（不读 DB/settings、不写文件、不连网；引擎由调用方注入） |
| pass（本文件下半，PR-2 新增） | ``build_geometry_artifact`` / ``PaddleTableGeometryEngine`` / 开关读取 | 能（抽子 PDF、调引擎、渲染裁图） |

pass 层只负责「谁去量、怎么兜底」，坐标数学一律复用上半层的纯函数：两条路径
（子 PDF 批量 / 单页裁图）共用同一段对齐与配对代码，否则两条路径会得出两套格子。
"""

from __future__ import annotations

import bisect
import logging
import math
import re
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any, Protocol

import pymupdf as fitz

from .bbox import normalize_bbox, resolve_bbox_unit
from .md_table import grid_col_count as _grid_col_count
from .md_table import grid_row_count as _grid_row_count
from .md_table import parse_grid as _parse_grid

logger = logging.getLogger("apps.pdf_splitting")

#: 归一化矩形保留的小数位。与 ``bbox.normalize_bbox`` 一致：0.0001 远小于一个像素，
#: 但能避免 ``0.04`` 被算成 ``0.03999999999999998``。
_RECT_PRECISION = 4

#: 一个像素框 / 一个裁框的坐标个数（x0, y0, x1, y1）。
_BOX_AXES = 4

#: 裁图尺寸的个数（width, height）。
_SIZE_AXES = 2

#: 边界线聚类容差（占裁图宽/高的比例）。
#:
#: 1% 的裁图 ≈ 16px（p10 裁图 1555×1660）：足够吸收 cell 边的 1–3px 抖动，
#: 又远小于最窄列宽（p10 最窄列 ≈ 81px），不会把相邻两列并成一条线。
DEFAULT_EDGE_TOL_RATIO = 0.01

#: 格子与 ``pred_html`` 对齐用的开标签计数（``<td`` / ``<th``）。
_CELL_TAG_RE = re.compile(r"<t[dh][\s>]", re.IGNORECASE)

#: ``PageTableGeometry.engine`` 的取值之一，也是本模块唯一支持的量测来源。
PP_STRUCTURE_ENGINE = "pp_structure_v3"

#: 结构硬闸：格子超出所属表块 bbox 的容忍度（页宽/页高的比例）。
#:
#: 取 1.5%：实测像素→页面换算误差量级是 0.0007–0.003 页宽（p16 0.00069 / p10 0.00295，
#: ``facts/FACTS.md`` SF-6/SF-8），1.5% 是它的 5 倍以上；而真正的「坐标错位」——框指到
#: 隔壁表或整页——差出量是 0.1–1.0 页。两侧差一个数量级，不会两头都靠得住。
STRUCT_TOLERANCE_RATIO = 0.015

#: 列/行聚类的「紧致度」上限：簇内最大抖动 ≤ 相邻簇心最小间距的这个比例。
#:
#: 为什么需要：固定容差（裁图宽的 1%）在密度不同的表上一定会错——
#: 22 页真实批量样本上，46 行×8 列那种表行高只有 26px（< 1% 裁图高 16.8px），
#: 相邻行边界被并成一条 → 同一（row, col）出现大量重复格位（实测 48 / 73 个）。
#: 改成「按 HTML 给的列数量聚到 K 簇 + 校验簇内抖动」：
#:
#: | 表 | 簇内抖动 / 最小间距 |
#: |:--|--:|
#: | 结构规整的 14 张（p10/p13/p16/p17/p20#0/p43/p44/p92/p93…） | 0.00–0.14 |
#: | 勉强可用（p11 / p20#1） | 0.66 / 0.65 |
#: | 盒子错乱的 p54 / p71 / p72 | 1.17 / 1.13 / 14.81 |
#:
#: 0.7 落在这两组之间，两侧都有余量。
_AXIS_SPREAD_RATIO_MAX = 0.7

#: 行首合并上限：簇间间隙 ≤ 该值就并成一行（防止一行被拆成两行）。
#:
#: 取值是「格子高度的 20 分位 × 这个比例」：中位数会被 rowspan 格拉高
#: （p27 的 8 个格里有一半是 3~4 行高的大框，中位高 410px，而真实行高 ≈200px），
#: 20 分位才是真实行高。
_ROW_GAP_RATIO = 0.5

#: 重复格位允许被丢弃的比例；超过就说明网格本身不可信（整表框）。
#:
#: 重复格位不是“数据问题”而是“行列推断错了”的证据，所以先**修复**（丢掉重的那格，
#: 少画一个格子总比整表退回好），只有大面积重复才说明聚类真的崩了。
_DUPLICATE_DROP_MAX_RATIO = 0.2

#: 表级配对阈值（DESIGN §9.2）。
#:
#: 依据（全实测）：同页多表的 MinerU 块互不相交（p16/p20 互 IoU = 0.0000），
#: 而正确配对的 IoU 仍在 0.97 以上 —— 0.5 两侧各留 ≥0.5 余量；
#: margin 0.3 则是用「p 的最好块 − 次好块」把「两块都像」的暖昧情形挡在外面。
_TABLE_MATCH_IOU_MIN = 0.5
_TABLE_MATCH_IOU_MARGIN = 0.3

#: 第二个配对信号：**表块几乎完全落在 PP 表框里**时的包含度阈值。
#:
#: 为什么不能只看 IoU：PP 有时只框对了一半（把签名栏、下一段正文也塞进同一张表，
#: 实测 p11/p27/p35：块本身 97% 在 PP 表框内，但 PP 框的高度是块的 2 倍 → IoU 只有
#: 0.35–0.44 → 记成 ``unmatched_pp_table``，看不出**是谁**的问题）。
#: 加上这条后这类页会被配上，接着由结构闸门记 ``pp_box_outside_block`` —— 责任方
#: 一眼可辨；且格子仍然**不会**被画出来（越界就是整表框）。
_TABLE_MATCH_CONTAINMENT_MIN = 0.8

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

# ── 整表框原因（诊断契约；每一条都进产物 ``skipped`` 与 summary ``reason_counts``）──
REASON_MATCHED = "matched"
REASON_UNMATCHED_PP_TABLE = "unmatched_pp_table"
REASON_MERGED_PP_TABLE = "merged_pp_table"
REASON_SPLIT_PP_TABLE = "split_pp_table"
REASON_ORPHAN_PP_TABLE = "orphan_pp_table"
REASON_NO_TABLE_DETECTED = "no_table_detected"
REASON_PSEUDO_TABLE = "pseudo_table"
REASON_GEOMETRY_INCONSISTENT = "geometry_inconsistent"
#: PP 画的格子超出所属 MinerU 表块 bbox 太多 —— **PP 侧**的问题（框铺到了别的版面区域）。
REASON_PP_BOX_OUTSIDE_BLOCK = "pp_box_outside_block"
#: PP 的列数与 MinerU HTML 网格的列数不一致 —— **两侧对不上**，没法把文字对到格子上。
REASON_PP_SHAPE_MISMATCH = "pp_shape_mismatch"
REASON_EMPTY_CELLS = "empty_cells"
REASON_ENGINE_ERROR = "engine_error"
REASON_BATCH_FAILED = "batch_failed"
REASON_BUDGET_EXHAUSTED = "budget_exhausted"
REASON_ROTATION = "rotation"
REASON_NO_COORDINATES = "no_coordinates"


@dataclass(frozen=True)
class TableCellBox:
    """一个格子：在页面上的矩形 + 它在网格里的位置。

    ``rect`` 是页面归一化坐标 ``{"x","y","w","h"}``（0–1），不是引擎的裁图像素。
    ``row``/``col`` 从 0 起，``row_span``/``col_span`` 由框的长宽相对中位格推得
    （见 ``build_cell_boxes``）。
    """

    text: str
    row: int
    col: int
    row_span: int
    col_span: int
    rect: dict[str, float]


@dataclass(frozen=True)
class PageTableGeometry:
    """一页里「量到的一张表」。

    ``crop`` 是裁图在页面上的归一化区域 ``(cx0, cy0, cx1, cy1)``。它**必须**是裁图时
    实际用的区域：换成表格 bbox 会让列边界偏出容差，而产物的可复算性全靠它。
    批量路径送的是整页，所以 ``crop`` 恒为 ``(0, 0, 1, 1)``。

    ``pp_bbox`` 是由该表 ``cell_box_list`` 派生的页面归一化外接框。供应商的
    ``table_res_list[i]`` **没有表级 bbox**（``facts/FACTS.md`` SF-20），同页多表
    （p16/p20）只能靠它与本页 MinerU 块做 IoU 配对，所以必须落盘否则事后无法复算。

    ``match`` 是配对结果 ``{block_index, table_index, iou, margin, reason}``。
    """

    page_no: int
    engine: str
    rows: int
    cols: int
    cells: tuple[TableCellBox, ...]
    crop: tuple[float, float, float, float]
    diagnostics: dict[str, Any]
    pp_bbox: dict[str, float] | None = None
    match: dict[str, Any] | None = None


class TableMeasureEngine(Protocol):
    """量**一张裁图**的引擎协议（DESIGN §3「可测性 / 注入」）。

    ``measure`` 收裁图 PNG 字节，返回 PP-StructureV3 意义上的 ``table_res_list``
    （每项含 ``cell_box_list`` 与 ``pred_html``）；量不到返回 ``None`` 或空列表。
    单测注入 fake，不连网络。
    """

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]] | None: ...


class TableGeometryEngine(TableMeasureEngine, Protocol):
    """量**一批页**的引擎协议（PR-2 批量主路径）。

    ``measure_pdf`` 收子 PDF 字节，返回**逐页**的表结构：外层下标 = 送检页序
    （响应是 JSONL、一行 = 一页，见 ``facts/BATCH.md`` §1/§2）。返回项数与送检页数
    不等时调用方判「整批不可用」并回退单页裁图——**绝不**按序硬凑：错一页就整页格子
    画到别的页上，比没有框更糟。

    两条路径共用同一个 ``table_res_list`` 形状，所以对齐与配对只有一份代码。
    """

    def measure_pdf(self, pdf_bytes: bytes, *, page_count: int) -> list[list[dict[str, Any]]] | None: ...


def map_pixel_rect(
    rect_px: Sequence[float], *, crop: tuple[float, float, float, float], crop_size: tuple[int, int]
) -> dict[str, float] | None:
    """裁图像素矩形 → 页面归一化矩形 ``{"x","y","w","h"}``。

    换算公式与 ``ocr_handler._rescale_region_blocks()`` 同一数学（归一化版）：
    先按裁图宽高放大到裁图区域尺寸，再平移到裁图在页面上的起点，最后夹到 0–1。

    返回 ``None`` 的情形（一律不编坐标）：

    - ``rect_px`` 不是「至少 4 个有限数字」的序列，或含 NaN/inf；
    - 退化框（``x1 <= x0`` 或 ``y1 <= y0``）。**不排序**：反序的框说明调用方拿错了
      坐标系，顺手排个序会把它伪装成合法框；
    - 裁框退化（宽/高为 0）或裁图尺寸非正/缺失——除零会算成 inf/nan，把整层 SVG 弄坏。
    """
    frame = _validated_frame(crop, crop_size)
    if frame is None:
        return None
    coords = _as_floats(rect_px, axes=_BOX_AXES)
    if coords is None:
        return None
    x0, y0, x1, y1 = coords
    if x1 <= x0 or y1 <= y0:
        return None

    cx0, cy0, cx1, cy1, crop_w_px, crop_h_px = frame
    left = _clamp01(cx0 + (x0 / crop_w_px) * (cx1 - cx0))
    right = _clamp01(cx0 + (x1 / crop_w_px) * (cx1 - cx0))
    top = _clamp01(cy0 + (y0 / crop_h_px) * (cy1 - cy0))
    bottom = _clamp01(cy0 + (y1 / crop_h_px) * (cy1 - cy0))
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        # 整个框被夹到裁图边上：没有可视意义，按「没有坐标」处理
        return None
    return {
        "x": round(left, _RECT_PRECISION),
        "y": round(top, _RECT_PRECISION),
        "w": round(width, _RECT_PRECISION),
        "h": round(height, _RECT_PRECISION),
    }


def build_cell_boxes(
    cell_boxes: Sequence[Sequence[float]],
    *,
    crop: tuple[float, float, float, float],
    crop_size: tuple[int, int],
    edge_tol_ratio: float = DEFAULT_EDGE_TOL_RATIO,
    expected_cols: int | None = None,
    expected_rows: int | None = None,
) -> tuple[TableCellBox, ...]:
    """像素框序列 → 带行列位置的格子，row-major 输出（文本全部为空串）。

    ## 行列怎么推

    1. **列**：拿每个框的 ``x0`` 聚成边界线。给了 ``expected_cols``（引擎自己的
       ``pred_html`` 算出的列数）就**聚到正好 K 簇**（相邻最小间隙优先合并），
       再校验「簇内抖动 ≤ 相邻簇心最小间距 × ``_AXIS_SPREAD_RATIO_MAX``」；
       不达标就整表不可信（返回空）。没给 ``expected_cols`` 时退回固定容差聚类。
    2. **行**：拿 ``y0`` 聚类，并合并「间隙 ≤ 格子高 20 分位 × 0.5」的相邻簇；
       给了 ``expected_rows`` 时**最多**只并到这个数量（跨页续表的本页行数可以少于
       HTML 行数，所以只做上限、不做下限）。
    3. ``col``/``row`` = 最近的簇心；``col_span``/``row_span`` = 框的另一边隔了几条线。
    4. 按 ``(row, col)`` 排序，重复格位只留面积最大的那一个（见下）。

    ## 为什么不能再用固定容差

    22 页真实批量样本：46 行 × 8 列的表行高只有 26px，比「裁图高 × 1% = 16.8px」
    还窄，相邻行边界被并成一条 → 同一 ``(row, col)`` 出现 48 / 73 个重复格位，
    整张表被退回。反过来 p27 这种 4 列表，两行的左边界差 12px（略大于 11.9px 容差）
    就会被拆成两条线 → 列数翻倍。**容差不可能只靠一个比例同时满足这两种表**，
    所以改成用引擎自己的 HTML 形状当约束，并用「簇内抖动/簇间距」这只尺子验收。

    ## 重复格位：先修复，再考虑整表框

    行列推到同一个格位，说明聚类把两行（或两列）并成了一条。处理办法是丢掉重复里
    面积更小的那个格子：**少画一个格子**远好于整表退回整表框，也绝不错画。
    只有重复比例超过 ``_DUPLICATE_DROP_MAX_RATIO`` 才判几何不可信（返回空）。

    ## 为什么没有 ``texts`` 参数（PR-2 拆掉的）

    ``cell_box_list`` 的顺序**不是契约**：单页裁图样本（p10/p16/p22）碰巧是 row-major，
    而批量送整页的样本（p71/p72/p54/p20）“同一行带内 x0 逆序”都会出现
    （``facts/BATCH.md`` §3）。按下标把 ``<td>`` 文本 zip 到格子上，在批量路径上
    就是把文字贴错格——那是 §0.2 意义上的「假成功」。

    文本改由 ``assign_cell_texts`` **按几何归属**填（文本框中心落在哪个格），
    与顺序无关。

    量不到几何（裁框/裁图尺寸不成立、没有合法框、行列不可信）→ 返回空元组 + ``logger.warning``。
    """
    frame = _validated_frame(crop, crop_size)
    if frame is None:
        logger.warning("表格几何: 裁图参数不可用（crop=%r, crop_size=%r），不产出格子", crop, crop_size)
        return ()

    pixel_rects = _valid_pixel_rects(cell_boxes)
    if not pixel_rects:
        logger.warning("表格几何: 没有合法的 cell_box（原始项数 %s），不产出格子", _length_of(cell_boxes))
        return ()

    ratio = _tol_ratio(edge_tol_ratio)
    columns = _column_axis(pixel_rects, frame=frame, ratio=ratio, expected_cols=expected_cols)
    if columns is None:
        return ()
    rows = _row_axis(pixel_rects, frame=frame, ratio=ratio, expected_rows=expected_rows)

    built: list[tuple[int, int, TableCellBox]] = []
    for x0, y0, x1, y1 in pixel_rects:
        rect = map_pixel_rect((x0, y0, x1, y1), crop=crop, crop_size=crop_size)
        if rect is None:
            continue
        built.append(
            (
                rows.index(y0),
                columns.index(x0),
                TableCellBox(
                    text="",
                    row=rows.index(y0),
                    col=columns.index(x0),
                    row_span=rows.span(y0, y1),
                    col_span=columns.span(x0, x1),
                    rect=rect,
                ),
            )
        )
    if not built:
        logger.warning("表格几何: 所有 cell_box 都无法换算成页面坐标（crop=%r），不产出格子", crop)
        return ()

    cells = _drop_duplicate_positions(built, raw_count=len(pixel_rects))
    if cells is None:
        return ()
    return cells


class _Axis(Protocol):
    """一维格位轴：``index`` 给格位下标，``span`` 给框跨了几个格位。"""

    def index(self, value: float) -> int: ...

    def span(self, start: float, end: float) -> int: ...


@dataclass(frozen=True)
class _BandAxis:
    """簇心模式（列：聚到 K 簇之后）——用相邻簇心的**中点**当分界。

    为什么中点：一格很宽的框（p27 实测有 x1 越过邻列 90px 的）用“最近的簇心”判
    span 会多跨一列；中点分界不会。
    """

    centres: tuple[float, ...]

    def index(self, value: float) -> int:
        borders = tuple((self.centres[index] + self.centres[index + 1]) / 2 for index in range(len(self.centres) - 1))
        return bisect.bisect_right(borders, value)

    def span(self, start: float, end: float) -> int:
        return max(1, self.index(end) - self.index(start))


@dataclass(frozen=True)
class _LineAxis:
    """边界线模式（没有 HTML 形状时沿用 PR-1 行为）：下标是“最近的边界线”。"""

    lines: tuple[float, ...]

    def index(self, value: float) -> int:
        return _edge_index(self.lines, value)

    def span(self, start: float, end: float) -> int:
        return max(1, self.index(end) - self.index(start))


def _column_axis(
    pixel_rects: Sequence[tuple[float, float, float, float]],
    *,
    frame: tuple[float, float, float, float, float, float],
    ratio: float,
    expected_cols: int | None,
) -> _Axis | None:
    """列轴；``None`` = 结构不可信（调用方整表框）。

    有 ``expected_cols``（引擎 ``pred_html`` 的列数）时：把**左边界** ``x0`` 聚到正好
    K 簇，再用中点做分界。为什么只用 ``x0``、不用 ``x1``：真实批量样本里框的
    右边界很不稳（p27 有两格的 x1 越过邻列 90px），而左边界是列的真实起点，稳定得多。
    没给 ``expected_cols`` 时退回固定容差聚类边界线（PR-1 行为，供没有 HTML 的调用方用）。
    """
    if expected_cols is None or expected_cols < 1:
        values = [rect[0] for rect in pixel_rects] + [rect[2] for rect in pixel_rects]
        return _LineAxis(tuple(_cluster_edges(values, tol=ratio * frame[4])))
    # 用**去重**后的起点值聚类：K 比真实列数还大时（PP 的 HTML 多报了列），
    # 拿重复值去“聚到 K 簇”会把同一列的框拆成两簇（实测 min_gap=0 → 误判不可信）
    groups = _merge_to_k(sorted({rect[0] for rect in pixel_rects}), k=max(2, expected_cols))
    quality = _axis_quality(groups)
    if quality is None or quality > _AXIS_SPREAD_RATIO_MAX:
        logger.warning(
            "表格几何: 列聚类不可信（簇内抖动/簇间距=%s，期望列数=%s），本表整表框",
            "n/a" if quality is None else round(quality, 2),
            expected_cols,
        )
        return None
    return _BandAxis(tuple(sum(group) / len(group) for group in groups))


def _row_axis(
    pixel_rects: Sequence[tuple[float, float, float, float]],
    *,
    frame: tuple[float, float, float, float, float, float],
    ratio: float,
    expected_rows: int | None,
) -> _Axis:
    """行轴：按「格子高 20 分位 × ``_ROW_GAP_RATIO``」合并，行数只做**上限**。

    上限而非等值：跨页续表的本页可见行数可以少于 HTML 行数（p10 HTML 7 行、
    本页真实 6 行），强行凑到 7 行会把一行劈成两行。
    """
    if expected_rows is None or expected_rows < 1:
        values = [rect[1] for rect in pixel_rects] + [rect[3] for rect in pixel_rects]
        return _LineAxis(tuple(_cluster_edges(values, tol=ratio * frame[5])))
    cap = _row_merge_cap([rect[3] - rect[1] for rect in pixel_rects])
    groups = _merge_by_gap(sorted({rect[1] for rect in pixel_rects}), cap=cap, max_groups=max(2, expected_rows))
    return _BandAxis(tuple(sum(group) / len(group) for group in groups))


def _row_merge_cap(heights: Sequence[float]) -> float:
    """行首合并上限：格子高的 20 分位 × ``_ROW_GAP_RATIO``（中位数会被 rowspan 拉高）。"""
    ordered = sorted(height for height in heights if height > 0)
    if not ordered:
        return 0.0
    return ordered[int(len(ordered) * 0.2)] * _ROW_GAP_RATIO


def _merge_to_k(ordered: Sequence[float], *, k: int) -> list[list[float]]:
    """升序值 → 正好 ``k`` 簇（每次合并相邻间隙最小的两簇）。"""
    groups: list[list[float]] = [[value] for value in ordered]
    while len(groups) > k:
        gap, position = min((groups[index + 1][0] - groups[index][-1], index) for index in range(len(groups) - 1))
        if gap < 0:  # pragma: no cover - 输入已排序，负间隙不可能出现
            break
        groups[position] = groups[position] + groups[position + 1]
        del groups[position + 1]
    return groups


def _merge_by_gap(ordered: Sequence[float], *, cap: float, max_groups: int) -> list[list[float]]:
    """升序值按间隙合并：间隙 ≤ ``cap`` 且簇数仍大于 ``max_groups`` 才并。"""
    groups: list[list[float]] = [[value] for value in ordered]
    while len(groups) > 1 and len(groups) > max_groups:
        gap, position = min((groups[index + 1][0] - groups[index][-1], index) for index in range(len(groups) - 1))
        if gap > cap:
            break
        groups[position] = groups[position] + groups[position + 1]
        del groups[position + 1]
    return groups


def _axis_quality(groups: Sequence[Sequence[float]]) -> float | None:
    """一维聚类的「簇内抖动 / 相邻簇心最小间距」；不足两簇时返回 ``None``（无法评估）。"""
    centres = [sum(group) / len(group) for group in groups]
    gaps = [centres[index + 1] - centres[index] for index in range(len(centres) - 1)]
    min_gap = min(gaps) if gaps else 0.0
    if min_gap <= 0:
        return None
    spread = max(max(group) - min(group) for group in groups)
    return spread / min_gap


def _drop_duplicate_positions(
    built: Sequence[tuple[int, int, TableCellBox]], *, raw_count: int
) -> tuple[TableCellBox, ...] | None:
    """排序 + 去重：同一 ``(row, col)`` 只留面积最大的格；重复过多则判不可信（``None``）。

    重复格位是「两行（或两列）被聚成了一条线」的证据，丢掉多出来的那个格子
    （少画一个框）远好于整表退回整表框；但大面积重复说明聚类本身崩了，不能再画。
    """
    ordered = sorted(built, key=lambda item: (item[0], item[1], -(item[2].rect["w"] * item[2].rect["h"])))
    seen: set[tuple[int, int]] = set()
    kept: list[TableCellBox] = []
    for row, col, cell in ordered:
        if (row, col) in seen:
            continue
        seen.add((row, col))
        kept.append(cell)
    dropped = max(0, raw_count - len(kept))
    if dropped and dropped > raw_count * _DUPLICATE_DROP_MAX_RATIO:
        logger.warning(
            "表格几何: %d/%d 个格子与别的格子同格位（超过 %d%%），行列推断不可信，本表整表框",
            dropped,
            raw_count,
            int(_DUPLICATE_DROP_MAX_RATIO * 100),
        )
        return None
    if dropped:
        logger.warning("表格几何: %d 个格子与别的格子同格位，已丢弃（宁少画不错画）", dropped)
    return tuple(kept)


def grid_shape(cells: Sequence[TableCellBox]) -> tuple[int, int]:
    """``(rows, cols)`` = ``(max(row + row_span), max(col + col_span))``；空集合为 ``(0, 0)``。"""
    if not cells:
        return (0, 0)
    return (
        max(cell.row + cell.row_span for cell in cells),
        max(cell.col + cell.col_span for cell in cells),
    )


def assign_cell_texts(
    cells: Sequence[TableCellBox],
    *,
    lines: Sequence[tuple[str, Sequence[float]]],
    crop: tuple[float, float, float, float],
    crop_size: tuple[int, int],
) -> tuple[tuple[TableCellBox, ...], str]:
    """按**几何归属**把行级 OCR 文本填进格子，返回 ``(格子, text_source)``。

    ``lines`` 是 ``table_ocr_pred`` 的 ``(rec_texts, rec_boxes)`` 对，顺序任意。

    ## 两点必须同时成立

    1. **不按下标**：``cell_box_list`` 与 ``rec_boxes`` 是两套独立顺序，
       批量路径上前者已实测不是 row-major（``facts/BATCH.md`` §3），但不能假定后者就稳定；
       归属只问一句「这个文本框的中心落在哪个格子里」。
    2. **不猜**：落不进任何格子的文本直接丢弃（多出来的多半是跨格/单元格溢出
       的文字碎片）；重叠时取面积最小的格（嵌套表/伪表的表征）。

    格内多行文本按 ``(y, x)`` 再拼接（阅读顺序）。拼接不加分隔符：``rec_texts``
    本就是“按行切开的同一句话”（实测 p10 第 10 条是「定申请表》，因第三人提交的材料不完整，」），
    插空格会把词的中间栽开。

    ``text_source``：有可用文本框时为 ``"table_ocr_pred"``；缺失/不可映射时为 ``"none"``
    （格子文本留空）。**绝不**回退到“按下标 zip”。
    """
    if not cells:
        return ((), "none")
    grouped: dict[int, list[tuple[float, float, str]]] = {}
    for text, box in lines:
        line_rect = map_pixel_rect(box, crop=crop, crop_size=crop_size)
        if line_rect is None:
            continue
        centre = (line_rect["x"] + line_rect["w"] / 2, line_rect["y"] + line_rect["h"] / 2)
        index = _containing_cell(cells, centre)
        if index is None:
            continue
        grouped.setdefault(index, []).append((centre[1], centre[0], text.strip()))
    if not grouped:
        return (tuple(cells), "none")

    filled: list[TableCellBox] = []
    for index, cell in enumerate(cells):
        parts = [text for _y, _x, text in sorted(grouped.get(index, [])) if text]
        filled.append(replace(cell, text="".join(parts)) if parts else cell)
    return (tuple(filled), "table_ocr_pred")


def structural_check(
    cells: Sequence[TableCellBox],
    *,
    block_bbox: dict[str, float],
    tolerance_ratio: float = STRUCT_TOLERANCE_RATIO,
) -> str | None:
    """结构硬闸：几何不能用就返回原因（``None`` = 通过）；命中即整表框，不再谈精度。

    两个原因键**故意分开**，因为责任方不同、下一步该查的地方也不同：

    1. ``geometry_inconsistent``（**我们**的问题）：两个格子占同一格位（含 span 占位）。
       行/列是聚类推出来的，推错一格就会重叠 → 要评估聚类参数。
    2. ``pp_box_outside_block``（**PP** 的问题）：格子超出所属表块 bbox 超过
       ``STRUCT_TOLERANCE_RATIO``。实测 p11/p27/p35 就是这种：PP 的格框虚高到页面
       下半部（把签名栏也框进去了），而 MinerU 的 bbox 是对的 → 要评估引擎画框。
    """
    occupied: set[tuple[int, int]] = set()
    for cell in cells:
        positions = {
            (cell.row + drow, cell.col + dcol) for drow, dcol in product(range(cell.row_span), range(cell.col_span))
        }
        if occupied & positions:
            logger.warning("表格几何: 格位重叠（row=%s, col=%s），行列推断不可信", cell.row, cell.col)
            return REASON_GEOMETRY_INCONSISTENT
        occupied |= positions
    if not _inside_block(cells, block_bbox=block_bbox, tolerance=_tol_ratio(tolerance_ratio)):
        logger.warning(
            "pdf_split_table_geometry_pp_box_outside_block",
            extra={"block": {key: round(value, 3) for key, value in block_bbox.items()}},
        )
        return REASON_PP_BOX_OUTSIDE_BLOCK
    return None


@dataclass(frozen=True)
class TableMatch:
    """一个 MinerU ``table`` 块与它配上的 PP 表（或配不上的原因）。

    ``block_index`` 是**版面块下标**（``layout.blocks`` 里的位置），不是候选列表位置。
    """

    block_index: int
    table_index: int | None
    iou: float
    margin: float
    reason: str


@dataclass(frozen=True)
class TableMatches:
    """一页的配对结果。

    ``by_block`` 每个候选块一条（含配不上的，带原因）；``orphan_tables`` 是没配给任何块的
    PP 表下标（多为裁图外/误检），只计数不进产物——它们是“多出来的”，不造成错框。
    """

    by_block: dict[int, TableMatch]
    orphan_tables: tuple[int, ...] = ()


def match_tables_to_blocks(
    block_bboxes: Sequence[dict[str, float]],
    table_bboxes: Sequence[dict[str, float]],
    *,
    block_indices: Sequence[int] | None = None,
    iou_min: float = _TABLE_MATCH_IOU_MIN,
    iou_margin: float = _TABLE_MATCH_IOU_MARGIN,
) -> TableMatches:
    """本页 MinerU ``table`` 块 ↔ PP 派生的表框：IoU 一对一贪心配对（纯函数）。

    为什么必须配对：``table_res_list`` 是一个**列表**（p16/p20 各 2 张表），
    而它**没有表级 bbox**，只有一堆 cell 框。不配对的话，把 A 表的格子画到 B 表上
    比不画框更糟（与均分编造同类错误）。

    ## ``block_indices``：两个下标空间不能混用

    ``block_bboxes`` 的顺序是“候选块列表的位置”，而调用方真正关心的是**版面块下标**
    （``layout.blocks`` 里的位置）—— 两者不是一个东西：p10 的表格是版面的第 3 块，
    在候选列表里却是第 1 个。混用的后果是配上了也查不到（实测把 p10 等 12 个块全记成
    ``unmatched_pp_table``，因为 ``by_block[0]`` 对不上 ``block_index=2``）。
    所以这里收一个显式映射，返回值里的 ``block_index`` 一律是**调用方的标识**。

    判定顺序（DESIGN §9.2）：

    1. 两两算 IoU，只留 ``IoU ≥ iou_min`` 的强候选；
    2. 一张 PP 表强命中多个块 → 这些块全标 ``merged_pp_table``（PP 把上下两表合成了一张）；
    3. 一个块强命中多张 PP 表 → 该块标 ``split_pp_table``（PP 把一张表切碎了）；
    4. 一张表的最好块 − 次好块 不足 ``iou_margin`` → 这张表作废（暖昧不配），块记 ``unmatched_pp_table``；
    5. 其余块照旧配，配上的记 ``matched``。
    """
    indices = list(block_indices) if block_indices is not None else list(range(len(block_bboxes)))
    if len(indices) != len(block_bboxes):
        raise ValueError(f"block_indices({len(indices)}) 与 block_bboxes({len(block_bboxes)}) 长度不等")

    ious = [[_pair_score(block, table, iou_min=iou_min) for table in table_bboxes] for block in block_bboxes]
    hits_by_table = _strong_hits_by_table(ious, iou_min=iou_min)
    merged_positions = {
        block_position for hits in hits_by_table.values() if len(hits) > 1 for _iou_value, block_position in hits
    }
    # 已判 merged 的表不参与后面的配对：它不属于任何**单个**块
    unambiguous = {table: hits[0] for table, hits in hits_by_table.items() if len(hits) == 1}
    hits_by_block: dict[int, list[tuple[float, int]]] = {}
    for table_index, (iou_value, block_position) in unambiguous.items():
        if block_position in merged_positions:
            continue
        hits_by_block.setdefault(block_position, []).append((iou_value, table_index))

    by_block: dict[int, TableMatch] = {}
    matched_tables: set[int] = set()
    for block_position, hits in hits_by_block.items():
        block_index = indices[block_position]
        if len(hits) > 1:
            by_block[block_index] = TableMatch(block_index, None, max(hits)[0], 0.0, REASON_SPLIT_PP_TABLE)
            continue
        iou_value, table_index = hits[0]
        margin = _margin_of(ious, table_index=table_index, best=iou_value)
        if margin < iou_margin:
            continue  # 不划入 matched：留给下面的 unmatched 分支
        by_block[block_index] = TableMatch(block_index, table_index, iou_value, margin, REASON_MATCHED)
        matched_tables.add(table_index)

    for block_position, block_index in enumerate(indices):
        if block_index in by_block:
            continue
        if block_position in merged_positions:
            by_block[block_index] = TableMatch(block_index, None, 0.0, 0.0, REASON_MERGED_PP_TABLE)
            continue
        by_block[block_index] = TableMatch(block_index, None, 0.0, 0.0, REASON_UNMATCHED_PP_TABLE)

    orphans = tuple(index for index in range(len(table_bboxes)) if index not in matched_tables)
    return TableMatches(by_block=by_block, orphan_tables=orphans)


def measure_table_crop(
    image_bytes: bytes,
    *,
    page_no: int,
    crop: tuple[float, float, float, float],
    engine: TableMeasureEngine,
    crop_size: tuple[int, int],
) -> PageTableGeometry | None:
    """把一张裁图交给引擎量，得到 ``PageTableGeometry``；量不到返回 ``None``。

    为什么 ``crop_size`` 要显式传：引擎返回的 ``cell_box_list`` 是**送进去那张图**的
    像素坐标，只给 ``image_bytes`` 就得先解码图片才知道尺寸（引入 PIL/cv2 依赖），
    而且拿不到尺寸时无法判断「引擎返回的是不是同一张图的坐标系」。

    降级（都只记 ``logger.warning``，不抛）：引擎失败/返回空、条目形状不对、
    没有合法 cell_box、``cell_box_list`` **多于** ``pred_html`` 的 ``<td>`` 数
    （结果自相矛盾）、``pred_html`` 缺失（形状无从约束）。

    ⚠️ 「数量必须严格相等」这道闸门已放宽（2026-11-21 实测）：退化框被过滤、
    以及 PP 输出 rowspan/colspan 时，``<td>`` 数本来就不等于格位数，严格相等会把
    真表整张跳过。顺序不再有消费方（行列靠几何聚类、文本按几何归属），
    剩下的上界（框数不得多于渲染格数）与几何层的三道闸门就够了。
    """
    frame = _validated_frame(crop, crop_size)
    if frame is None:
        logger.warning(
            "表格几何: 裁图参数不可用（crop=%r, crop_size=%r, page=%s），按整表框降级", crop, crop_size, page_no
        )
        return None

    tables = _measure_safely(engine, image_bytes, page_no=page_no)
    entries = [item for item in tables if isinstance(item, dict)]
    if not entries:
        logger.warning("表格几何: 引擎没有返回可用的表格（page=%s），本页按整表框降级", page_no)
        return None
    if len(entries) > 1:
        logger.warning("表格几何: 引擎返回了 %d 张表，只量第一张（page=%s）", len(entries), page_no)

    table = entries[0]
    # 引擎返回值不可能有静态类型：形状由 build_cell_boxes 内部逐项校验（非法项直接丢）
    raw_boxes: Any = table.get("cell_box_list")
    html_value = table.get("pred_html")
    html_text = html_value if isinstance(html_value, str) else ""
    expected_cells = _count_html_cells(html_text)
    if not expected_cells:
        logger.warning("表格几何: pred_html 缺失，格子顺序无从核对（page=%s），按整表框降级", page_no)
        return None

    expected_rows, expected_cols = html_grid_shape(html_text)
    cells = build_cell_boxes(
        raw_boxes,
        crop=crop,
        crop_size=crop_size,
        expected_cols=expected_cols,
        expected_rows=expected_rows,
    )
    if not cells:
        return None
    if len(_valid_pixel_rects(raw_boxes)) > expected_cells:
        # 与解析层同一条上界：框（去重前）比渲染格多 = 这张表的结果自相矛盾
        logger.warning(
            "表格几何: cell_box_list(%d) 多于 pred_html 的 <td>(%d)（page=%s），结果自相矛盾，按整表框降级",
            len(_valid_pixel_rects(raw_boxes)),
            expected_cells,
            page_no,
        )
        return None

    rows, cols = grid_shape(cells)
    return PageTableGeometry(
        page_no=page_no,
        engine=PP_STRUCTURE_ENGINE,
        rows=rows,
        cols=cols,
        cells=cells,
        crop=(frame[0], frame[1], frame[2], frame[3]),
        diagnostics={
            "cell_count": len(cells),
            "dropped_cells": _length_of(raw_boxes) - len(cells),
            "html_cell_count": expected_cells,
            "table_count": len(entries),
            "crop_size": [int(frame[4]), int(frame[5])],
        },
    )


def _measure_safely(engine: TableMeasureEngine, image_bytes: bytes, *, page_no: int) -> list[Any]:
    """调引擎（超时/凭证/5xx 都在这里），失败按「量不到」降级而不是把主链路弄挂。"""
    try:
        tables = engine.measure(image_bytes)
    except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
        # 引擎是外部依赖（超时/凭证/5xx）：量不到就退回整表框，不能把主链路弄挂
        logger.warning("表格几何: 引擎量测失败（page=%s）: %s", page_no, exc)
        return []
    if not isinstance(tables, list):
        return []
    return tables


def _validated_frame(crop: Any, crop_size: Any) -> tuple[float, float, float, float, float, float] | None:
    """校验裁框与裁图尺寸，返回 ``(cx0, cy0, cx1, cy1, crop_w_px, crop_h_px)``。

    不成立返回 ``None``（调用方据此给 None/空，而不是拿 0 去除）。
    """
    crop_values = _as_floats(crop, axes=_BOX_AXES)
    size_values = _as_floats(crop_size, axes=_SIZE_AXES)
    if crop_values is None or size_values is None:
        return None
    cx0, cy0, cx1, cy1 = crop_values
    crop_w_px, crop_h_px = size_values
    if cx1 <= cx0 or cy1 <= cy0 or crop_w_px <= 0 or crop_h_px <= 0:
        return None
    return cx0, cy0, cx1, cy1, crop_w_px, crop_h_px


def _as_floats(raw: Any, *, axes: int) -> tuple[float, ...] | None:
    """任意形状的坐标串 → 恰好 ``axes`` 个有限浮点数；转不了返回 ``None``。

    只认「扁平的数字序列」：``cell_box_list`` 之外没有别的合法来源，四点四边形/字符串
    一律当脏数据（``bbox._to_floats`` 那层替其他后端处理多边形，这里不做）。
    """
    if not isinstance(raw, (list, tuple)) or len(raw) < axes:
        return None
    values: list[float] = []
    for item in raw[:axes]:
        try:
            number = float(item)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        values.append(number)
    return tuple(values)


def _valid_pixel_rects(raw: Any) -> list[tuple[float, float, float, float]]:
    """``cell_box_list`` → 合法像素框（**保持原序**，顺序是「与 <td> 同序」的前提）。"""
    if not isinstance(raw, (list, tuple)):
        return []
    rects: list[tuple[float, float, float, float]] = []
    for item in raw:
        coords = _as_floats(item, axes=_BOX_AXES)
        if coords is None:
            continue
        x0, y0, x1, y1 = coords
        if x1 <= x0 or y1 <= y0:
            continue
        rects.append((x0, y0, x1, y1))
    return rects


def _cluster_edges(values: Sequence[float], *, tol: float) -> list[float]:
    """把贴近的边界值聚成一条边界线，返回各线中心（升序）。

    以**簇内首个值**为锚点比较，不做链式传递（``value - 上一个值``）：链式聚类会
    让连续的小抖动一路接龙，把两条真实边界并成一条。宁可多留一条线，也不并。
    """
    ordered = sorted(values)
    if not ordered:
        return []
    groups: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - groups[-1][0] <= tol:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _edge_index(edges: Sequence[float], value: float) -> int:
    """值 → 最近的边界线下标（``edges`` 升序，二分查找；不做内层线性扫描）。"""
    if not edges:
        return 0
    position = bisect.bisect_left(edges, value)
    if position <= 0:
        return 0
    if position >= len(edges):
        return len(edges) - 1
    before, after = edges[position - 1], edges[position]
    return position - 1 if (value - before) <= (after - value) else position


def _tol_ratio(edge_tol_ratio: float) -> float:
    """聚类容差比例：非有限或非正数（除零/负容差会让聚类退化）时回落到默认值。"""
    value = float(edge_tol_ratio)
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_EDGE_TOL_RATIO
    return value


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def _length_of(raw: Any) -> int:
    """序列长度；不是序列返回 0（只用于日志与 diagnostics，不参与判定）。"""
    return len(raw) if isinstance(raw, (list, tuple)) else 0


def _count_html_cells(html_text: str) -> int:
    """``pred_html`` 里的单元格数（``<td``/``<th`` 开标签计数）。

    口径必须与 ``paddleocr_api_service.parse_table_results`` 一致：两处都用「数量相等」
    判断「``cell_box_list`` 与 ``<td>`` 同序」这条实测结论是否还成立。
    不 import 那边的实现是为了让本模块保持「零 Django / 零 settings」的纯函数属性。
    """
    if not html_text:
        return 0
    return len(_CELL_TAG_RE.findall(html_text))


def _warn_duplicate_positions(cells: Sequence[TableCellBox]) -> None:
    """多个格子落到同一 ``(row, col)``：行列推断多半失败了，留痕（不悄悄丢数据）。"""
    counts = Counter((cell.row, cell.col) for cell in cells)
    duplicated = sorted(position for position, count in counts.items() if count > 1)
    if not duplicated:
        return
    logger.warning("表格几何: %d 个格子落到重复格位 %s，行列推断可能失败", len(cells) - len(counts), duplicated)


def _containing_cell(cells: Sequence[TableCellBox], centre: tuple[float, float]) -> int | None:
    """中心点落在哪个格子里；重叠时取面积最小的那个，没命中返回 ``None``。"""
    hits = [
        (cell.rect["w"] * cell.rect["h"], index)
        for index, cell in enumerate(cells)
        if cell.rect["x"] <= centre[0] <= cell.rect["x"] + cell.rect["w"]
        and cell.rect["y"] <= centre[1] <= cell.rect["y"] + cell.rect["h"]
    ]
    if not hits:
        return None
    return min(hits)[1]


def _inside_block(cells: Sequence[TableCellBox], *, block_bbox: dict[str, float], tolerance: float) -> bool:
    """每个格子是否都在表块 bbox 内（四边各放宽 ``tolerance``）。"""
    left = float(block_bbox["x"]) - tolerance
    top = float(block_bbox["y"]) - tolerance
    right = float(block_bbox["x"]) + float(block_bbox["w"]) + tolerance
    bottom = float(block_bbox["y"]) + float(block_bbox["h"]) + tolerance
    return all(
        left <= cell.rect["x"]
        and cell.rect["x"] + cell.rect["w"] <= right
        and top <= cell.rect["y"]
        and cell.rect["y"] + cell.rect["h"] <= bottom
        for cell in cells
    )


def _iou(first: dict[str, float], second: dict[str, float]) -> float:
    """两个归一化矩形的交并比（0–1）；无重叠或退化时为 0。"""
    left = max(float(first["x"]), float(second["x"]))
    top = max(float(first["y"]), float(second["y"]))
    right = min(float(first["x"]) + float(first["w"]), float(second["x"]) + float(second["w"]))
    bottom = min(float(first["y"]) + float(first["h"]), float(second["y"]) + float(second["h"]))
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = float(first["w"]) * float(first["h"]) + float(second["w"]) * float(second["h"]) - intersection
    return round(intersection / union, _RECT_PRECISION) if union > 0 else 0.0


def _strong_hits_by_table(ious: Sequence[Sequence[float]], *, iou_min: float) -> dict[int, list[tuple[float, int]]]:
    """``IoU ≥ iou_min`` 的候选，按表分组并按 IoU 降序（表下标 → [(iou, 块下标)]）。"""
    hits: dict[int, list[tuple[float, int]]] = {}
    for block_index, row in enumerate(ious):
        for table_index, iou_value in enumerate(row):
            if iou_value < iou_min:
                continue
            hits.setdefault(table_index, []).append((iou_value, block_index))
    return {table: sorted(group, reverse=True) for table, group in hits.items()}


def _pair_score(block: dict[str, float], table: dict[str, float], *, iou_min: float) -> float:
    """配对分：IoU 够就用 IoU；不够时看**表块被 PP 表框包住的比例**。

    包住 = 块几乎全在 PP 表框里（实测 p11/p27/p35 是 95–98%），说明 PP 画大了而不是画错了表；
    这时仍配对，后面的结构闸门会把它记成 ``pp_box_outside_block``（PP 的问题）而不是
    ``unmatched_pp_table``（没配上，看不出责任方）。
    """
    iou_value = _iou(block, table)
    if iou_value >= iou_min:
        return iou_value
    contained = _containment(block, table)
    return contained if contained >= _TABLE_MATCH_CONTAINMENT_MIN else iou_value


def _containment(inner: dict[str, float], outer: dict[str, float]) -> float:
    """``inner`` 有多大比例落在 ``outer`` 里（0–1）；``inner`` 面积为 0 时为 0。"""
    left = max(float(inner["x"]), float(outer["x"]))
    top = max(float(inner["y"]), float(outer["y"]))
    right = min(float(inner["x"]) + float(inner["w"]), float(outer["x"]) + float(outer["w"]))
    bottom = min(float(inner["y"]) + float(inner["h"]), float(outer["y"]) + float(outer["h"]))
    if right <= left or bottom <= top:
        return 0.0
    area = float(inner["w"]) * float(inner["h"])
    return round(((right - left) * (bottom - top)) / area, _RECT_PRECISION) if area > 0 else 0.0


def _margin_of(ious: Sequence[Sequence[float]], *, table_index: int, best: float) -> float:
    """这张表的「最好块 − 次好块」差（只有一个块时为 ``best`` 本身）。"""
    column = sorted((row[table_index] for row in ious), reverse=True)
    second = column[1] if len(column) > 1 else 0.0
    return round(best - second, _RECT_PRECISION)


# =====================================================================
# pass 层：选页 → 抽子 PDF 批量送 / 单页裁图兜底 → 配对 → 落产物
#
# 这一层会做 IO（读 PDF、调引擎、渲染裁图、读开关），坐标数学全部复用上半层的纯函数。
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
) -> dict[str, Any]:
    """几何 pass 的入口：候选表页 → 一次子 PDF 批量送 → 逐页配对 → 产物 dict。

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
    }
    summary = artifact.get("summary") if isinstance(artifact, dict) else None
    if isinstance(summary, dict):
        block.update({key: summary[key] for key in SUMMARY_KEYS if key in summary and key != "enabled"})
    return block


# ── 开关 ───────────────────────────────────────────────────────

#: 几何 pass 总开关（SystemConfig；默认开）。关掉后不调用引擎、不写产物。
TABLE_GEOMETRY_ENABLED_KEY = "PDF_SPLIT_TABLE_GEOMETRY_ENABLED"

#: 回滚开关（SystemConfig；默认关）：几何缺失时是否退回旧的「行列均分」框。
#:
#: 默认关 = 缺几何就整表框 —— 均分不可能用任何便宜判据证明可靠（列宽离散度拿不到），
#: 留着它等于留着一个已知会指错地方的路径（DESIGN §1）。
TABLE_UNIFORM_FALLBACK_KEY = "PDF_SPLIT_TABLE_UNIFORM_FALLBACK"


def geometry_enabled() -> bool:
    """``PDF_SPLIT_TABLE_GEOMETRY_ENABLED``（默认 ``1``）。"""
    return _as_flag(_system_value(TABLE_GEOMETRY_ENABLED_KEY, "1"), default=True)


def uniform_fallback_enabled() -> bool:
    """``PDF_SPLIT_TABLE_UNIFORM_FALLBACK``（默认 ``0``）。"""
    return _as_flag(_system_value(TABLE_UNIFORM_FALLBACK_KEY, "0"), default=False)


def switches() -> tuple[bool, bool]:
    """一次读两个开关 → ``(enabled, legacy_uniform)``。

    三个 ``build_segments_markdown`` 调用点都只调这一个函数：分别读两个键迟早会
    出现“某一条路径读了回滚开关、另一条没读”的劈叉，而那种劈叉的表现是
    “同一份卷宗在不同入口的绿框不一样”。
    """
    return geometry_enabled(), uniform_fallback_enabled()


def _system_value(key: str, default: str) -> str:
    """读 SystemConfig 的一个开关值。

    延迟 import（``apps.core`` 依赖 Django）＋ 读不到回落默认值：开关是运维的「停用
    按钮」，它读不出来时应该走默认路径继续干活，而不是让整条分段链挂掉；但必须留痕。
    """
    try:
        from apps.core.services.system_config_service import SystemConfigService

        return str(SystemConfigService().get_value(key, default) or "")
    except (ImportError, AttributeError, ValueError, TypeError):
        logger.warning("pdf_split_table_geometry_config_unreadable", extra={"key": key})
        return default


def _as_flag(raw: str, *, default: bool) -> bool:
    """``"1"/"true"/"yes"/"on"`` → True；``"0"/"false"/"no"/"off"`` → False；空串/怪值用默认。"""
    value = raw.strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


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
    引那一个常量（模块级会循环：markdown_builder 反过来要 import 本模块的类型）。
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


def block_table_html(block: dict[str, Any]) -> str:
    """块内的表格 HTML：``table_body`` → ``table_structure`` → ``html``。

    第三档是 PR-2 补的：MinerU 的跨页残片块（p11）把 HTML 放在 ``block["html"]``，
    不认这一档就会把整块丢掉（``facts/FACTS.md`` SF-13）。
    """
    return str(block.get("table_body") or block.get("table_structure") or block.get("html") or "")


def html_grid_shape(html: Any) -> tuple[int | None, int | None]:
    """``pred_html`` → ``(rows, cols)`` 网格形状；拿不到返回 ``(None, None)``。

    这是**引擎自己**给出的形状，用来给聚类当约束（聚到正好 K 列、行数只做上限）：
    它比“固定容差”稳得多（理由见 ``build_cell_boxes``），又不会让「列数必须等于
    MinerU 的网格」这道闸门变成同义反复 —— 聚类用的是 PP 的 HTML，闸门比的是
    MinerU 的 ``table_body``，两者是独立来源。
    """
    text = html if isinstance(html, str) else ""
    if not text:
        return (None, None)
    grid = _parse_grid(text)
    rows, cols = _grid_row_count(text), _grid_col_count(grid)
    if rows <= 0 or cols <= 0:
        return (None, None)
    return (rows, cols)


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


def _table_entry(candidate: _TableCandidate, *, match: TableMatch, block: _CandidateBlock) -> dict[str, Any]:
    """一张配上块的表 → 产物条目（含派生 bbox、配对结果、诊断）。"""
    html_rows = _grid_row_count(block.html)
    html_cols = _grid_col_count(_parse_grid(block.html))
    return {
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


def _ocr_lines(raw: Any) -> tuple[tuple[str, Sequence[float]], ...]:
    """``table_ocr_pred`` → ``(text, box)`` 对；两侧数量不等就**整批不用**。

    数量不等说明 ``rec_texts`` 与 ``rec_boxes`` 不是同一批（有脏项被过滤过），
    按序配对会把文本贴到别的框上。宁可一格文本都不填（``text_source=none``），
    也不制造“贴错的文本”。
    """
    if not isinstance(raw, dict):
        return ()
    texts = raw.get("rec_texts")
    boxes = raw.get("rec_boxes")
    if not isinstance(texts, list) or not isinstance(boxes, list) or len(texts) != len(boxes):
        return ()
    return tuple(
        (text, box)
        for text, box in zip(texts, boxes, strict=True)
        if isinstance(text, str) and isinstance(box, (list, tuple)) and len(box) >= _BOX_AXES
    )


def _union_rect(cells: Sequence[TableCellBox]) -> dict[str, float]:
    """格子集合的并集外接框（供应商不给表级 bbox，只能派生）。"""
    left = min(cell.rect["x"] for cell in cells)
    top = min(cell.rect["y"] for cell in cells)
    right = max(cell.rect["x"] + cell.rect["w"] for cell in cells)
    bottom = max(cell.rect["y"] + cell.rect["h"] for cell in cells)
    return {
        "x": round(left, _RECT_PRECISION),
        "y": round(top, _RECT_PRECISION),
        "w": round(right - left, _RECT_PRECISION),
        "h": round(bottom - top, _RECT_PRECISION),
    }


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
    return PageTableGeometry(
        page_no=page_no,
        engine=PP_STRUCTURE_ENGINE,
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
