"""表格格子几何：把 OCR **量到**的像素框换成页面归一化矩形与真实行列网格（纯数学层）。

## 这个文件只放什么 / 不许放什么

只放**不碰外部世界**的坐标数学与几何判定：像素→页面换算（``map_pixel_rect``）、行列聚类
（``build_cell_boxes``）、文本归属（``assign_cell_texts``）、结构硬闸（``structural_check``）、
表↔块配对（``match_tables_to_blocks``）、HTML 形状（``block_table_html`` / ``html_grid_shape``）、
数据类与 reason 键。引擎由调用方注入（``TableMeasureEngine`` 协议），本模块只收字节、不发请求。

**不许放**：``import fitz``、网络/引擎客户端、文件读写、``SystemConfig``/Django、``print``。
「谁去量、怎么兜底」在 ``table_geometry_pass.py``，「三个开关」在 ``table_geometry_switches.py``；
本文件连它们都不 import —— ``markdown_builder`` 反向依赖本文件，它是定位层，绝不能因此把
fitz 或网络客户端拖进导入链。

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

## 三个模块，不要混

| 模块 | 内容 | 能不能做 IO |
|:--|:--|:--|
| ``table_geometry.py``（本文件） | ``map_pixel_rect`` / ``build_cell_boxes`` / ``assign_cell_texts`` / ``structural_check`` / ``match_tables_to_blocks`` / ``grid_shape`` / ``measure_table_crop`` | **不能**（不读 DB/settings、不写文件、不连网；引擎由调用方注入） |
| ``table_geometry_pass.py`` | ``build_geometry_artifact`` / ``PaddleTableGeometryEngine`` / ``geometries_by_page_block`` / ``summary_block`` | 能（抽子 PDF、调引擎、渲染裁图） |
| ``table_geometry_switches.py`` | ``switches`` / ``geometry_enabled`` / ``uniform_fallback_enabled`` | 只读 SystemConfig |

pass 层只负责「谁去量、怎么兜底」，坐标数学一律复用本文件的纯函数：两条路径
（子 PDF 批量 / 单页裁图）共用同一段对齐与配对代码，否则两条路径会得出两套格子。
"""

from __future__ import annotations

import bisect
import logging
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import product
from typing import Any, Protocol

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


def _union_rect(cells: Sequence[TableCellBox]) -> dict[str, float]:
    """格子集合的并集外接框（供应商不给表级 bbox，只能由格子派生）。"""
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


def _ocr_lines(raw: Any) -> tuple[tuple[str, Sequence[float]], ...]:
    """``table_ocr_pred`` → ``(text, box)`` 对；两侧数量不等就**整批不用**（纯入参适配）。

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


# ── HTML 形状（引擎 ``pred_html`` / MinerU 块 HTML；纯字符串解析）──────────


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
