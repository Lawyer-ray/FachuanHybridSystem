"""本地「表格线投影」几何源：引擎不出表时，直接量页图上的墨线。

## 补的是哪个缺口

PP-StructureV3 几何 pass 在真实卷宗上 ``pages_total=22 / pages_measured=9 / pages_failed=13``，
13 页里有 **7 页 ``no_table_detected``**（引擎直接回 ``table_res_list=[]``，含 p52 这种
真表：165 行 974 td，见 ``facts/FACTS.md`` SF-16/SF-17）、2 页 ``pp_box_outside_block``。
这些页只能退回整表框。但**页面上有墨线的表**不依赖引擎也能量到：主会话在 p10/p16 上
验过「竖线 7/7、横线命中真实网格」，实现就在
``docs/analysis/table-cell-geometry-2026-11-21/eval/measure_box_error.py``。

## 与 eval 脚本同源（改一处要改两处）

线检测的**阈值口径一个字都没改**，只是把 eval 里 ``_line_candidates`` / ``detect_grid``
搬进来做成纯函数：

===============  ==================================================  ==========
常量             含义                                                 取值
===============  ==================================================  ==========
``DARK_THRESHOLD``        二值化阈值（扫描件表格线是深灰/黑，纸底 >140）      140
``MIN_COL_DARK_FRAC``     竖线：该列暗像素 / 区域高                           0.40
``MIN_ROW_DARK_FRAC``     横线：该行暗像素 / 区域宽                           0.30
``MIN_RUN_FRAC``          连续性：最长暗游程 / 区域对应边长                    0.20
``RUN_MERGE_GAP_PX``      游程合并容差（抗锯齿把 1px 线糊成 2~3px）            2px
``REGION_PAD_PX``         区域外扩（bbox 常贴着最外一条线甚至内缩）            6px
===============  ==================================================  ==========

「连续性」那道判据不是可选项：表单类表格的**字符竖排**能让暗像素投影轻易过 40%，
但那是 2~3px 短游程（eval 实测 p16 假列线 ``frac=0.42 / maxrun=0.05``，真表格线
``0.96~0.97 / 0.86~0.97``；p13 假行线 ``maxrun=0.01~0.08``，真行线 ``0.71``）。

⚠️ **这份阈值是复制而不是 import**：eval 脚本要能在没有 Django/``apps`` 的环境里
直接跑，反向 import 会把「度量工具」变成「运行时依赖」。所以在 eval 脚本的常量块里
也指向本模块；**改任一侧必须同步改另一侧**。

## 纪律：判不出网格就是 ``None``，绝不编坐标

以下情形一律 ``None``（原因写进 ``logger.debug``，不刷 warning —— 它每页都会发生）：

- 区域参数不成立（非 4 个数 / 非有限 / 越界 / 退化）或裁剪区 < ``MIN_REGION_PX``；
- 区域内无暗像素；
- 任一轴检出的线 **< 2 条**（1 条线围不出格子，2 条才有 1 格）；
- 边界重复（归一化后不再严格递增）或**网格退化**：任一相邻边界间距
  < ``MIN_EDGE_GAP_RATIO``（0.2% 页宽/页高）——那种「间距」是同一根线被拆成两条，
  画出来的格子只有 3px 宽却会被当成真格子；
- 图片字节解不出来（空 / 非位图）。

## 坐标口径

``RasterGrid.xs``/``ys`` 是**页面归一化** 0–1 的边界（与 ``bbox.normalize_bbox``、
``PositionedRectOut`` 同口径，前端 ``left: x*100%``），不是区域内的相对值：
量测在 ``region`` 裁剪区上做，换算时除以**整页**像素宽/高（与 eval 的
``(x0 + p) / page_w`` 一致）。``cells_from_grid`` 因此可以像整页送检那条路径一样
把 ``crop`` 记成 ``(0, 0, 1, 1)``——坐标本来就是页面的，不存在裁图换算。

## 两层，不要混

本文件只有**纯函数**：不读 DB/settings、不写文件、不连网，也不 import
``table_geometry`` 的 pass 层（``build_geometry_artifact`` / ``PaddleTableGeometryEngine``
会拉 fitz 与网络客户端）。与装配层的耦合只到数据类
（``PageTableGeometry`` / ``TableCellBox``）。
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np
from PIL import Image

from .table_geometry import PageTableGeometry, TableCellBox

logger = logging.getLogger("apps.pdf_splitting")

# ── 线检测参数（与 docs/analysis/table-cell-geometry-2026-11-21/eval/measure_box_error.py 同源）──

#: 二值化阈值：卷宗扫描件的表格线是深灰/黑，纸底与浅灰底纹都 >140。
DARK_THRESHOLD = 140

#: 竖线判据：该列暗像素数 / 区域高。竖表格线贯穿整表，文字笔画做不到。
MIN_COL_DARK_FRAC = 0.40

#: 横线判据：该行暗像素数 / 区域宽。
MIN_ROW_DARK_FRAC = 0.30

#: 连续性判据：最长连续暗像素游程 / 区域对应边长。抗「字符竖排冒充表格线」。
MIN_RUN_FRAC = 0.20

#: 游程合并容差（px）：抗锯齿会把一条 1px 线糊成 2~3px。
RUN_MERGE_GAP_PX = 2

#: 区域外扩（px）。表块 bbox 常贴着最外一条表格线甚至略微内缩，不外扩会把最后一条
#: 横线切在裁剪边界外（eval 实测 p10 底边 0.8899 就这样丢掉）。
REGION_PAD_PX = 6

#: 裁剪区最小边长（px）：比这更小投影统计量没有意义（除零/全噪声）。
MIN_REGION_PX = 8

#: 每个轴至少要几条线才可能围出格子：1 条线 = 0 格。
MIN_LINES_PER_AXIS = 2

#: 相邻边界的最小间距（页宽/页高）。小于它说明同一根线被拆成了两条。
MIN_EDGE_GAP_RATIO = 0.002

#: 边界/矩形保留的小数位（0.0001 页 ≈ 0.25px @150dpi，远小于 0.004 的验收容差）。
_EDGE_PRECISION = 4

#: 本模块的 ``PageTableGeometry.crop``：坐标是页面的，不需要裁图换算（同批量送整页那条路径）。
FULL_PAGE_CROP: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

#: 量测来源标识（``PageTableGeometry.engine``）。刻意不用 ``pp_structure_v3``：
#: 两者失败模式完全不同，事后统计覆盖率必须能分开数。
LOCAL_LINE_ENGINE = "raster_lines"

#: ``texts`` 被采用 / 未提供（或长度不匹配而整列留空）时的 ``diagnostics["text_source"]``。
TEXT_SOURCE_PROVIDED = "provided"
TEXT_SOURCE_NONE = "none"

# ── 判不出网格的原因（诊断契约；同时写进 ``logger.debug`` 与 ``diagnostics["reason"]``）──
REASON_OK = "ok"
#: 图片字节为空 / 解不出位图（非本页问题，调用方给错了输入）。
REASON_IMAGE_UNREADABLE = "image_unreadable"
#: ``region`` 不是 4 个有限数 / 越界 / 宽高为 0。
REASON_REGION_INVALID = "region_invalid"
#: 裁剪区（含外扩）小于 ``MIN_REGION_PX``。
REASON_REGION_TOO_SMALL = "region_too_small"
#: 区域内一个暗像素都没有 —— 空白页或区域指到了空白处。
REASON_BLANK_REGION = "blank_region"
#: 竖线不足 2 条（无框线表、纯文字段）。
REASON_FEW_COL_LINES = "few_col_lines"
#: 横线不足 2 条（同上，纵向）。
REASON_FEW_ROW_LINES = "few_row_lines"
#: 边界重复或相邻间距 < ``MIN_EDGE_GAP_RATIO`` —— 网格退化，画出来是假格子。
REASON_DEGENERATE_GRID = "degenerate_grid"


@dataclass(frozen=True)
class RasterGrid:
    """页图上量到的网格。

    ``xs``/``ys`` 是**页面归一化**的边界（0–1，升序），长度 = 列数/行数 + 1：
    相邻两条 ``xs`` 夹出一列，相邻两条 ``ys`` 夹出一行。
    ``diagnostics`` 是判定的实际取值（线数、覆盖率、最短游程、最小间距），
    事后不必重跑就能判断「这次凭什么出网格」。
    """

    xs: tuple[float, ...]
    ys: tuple[float, ...]
    diagnostics: dict[str, Any]

    @property
    def cols(self) -> int:
        """列数 = 竖线数 − 1（边界不足 2 条时为 0）。"""
        return max(0, len(self.xs) - 1)

    @property
    def rows(self) -> int:
        """行数 = 横线数 − 1（边界不足 2 条时为 0）。"""
        return max(0, len(self.ys) - 1)


def detect_grid_from_gray(
    gray: np.ndarray,
    *,
    region: tuple[float, float, float, float],
    dark_threshold: int = DARK_THRESHOLD,
    min_col_frac: float = MIN_COL_DARK_FRAC,
    min_row_frac: float = MIN_ROW_DARK_FRAC,
    min_run_frac: float = MIN_RUN_FRAC,
    gap_px: int = RUN_MERGE_GAP_PX,
    pad_px: int = REGION_PAD_PX,
    min_edge_gap_ratio: float = MIN_EDGE_GAP_RATIO,
) -> RasterGrid | None:
    """在``region``（页面归一化 ``(x0, y0, x1, y1)``）里找表格线，量出整页归一化网格。

    Args:
        gray: **整页**灰度图（``uint8`` 二维数组，PIL ``convert("L")`` / fitz ``csGRAY`` 口径）。
        region: 要找线的页面归一化区域，通常是 MinerU 的 table 块 bbox；会按 ``pad_px``
            外扩后夹到页内（与 eval 的 ``_PAD_PX`` 同一做法）。
        dark_threshold: 二值化阈值，``gray < dark_threshold`` 记为墨。
        min_col_frac: 竖线的最小暗像素覆盖率（相对区域高）。
        min_row_frac: 横线的最小暗像素覆盖率（相对区域宽）。
        min_run_frac: 线的最小连续游程（相对区域对应边长）。
        gap_px: 同一条线的游程合并容差（px）。
        pad_px: 区域外扩（px）。
        min_edge_gap_ratio: 相邻边界的最小间距（页宽/页高），更小即判网格退化。

    Returns:
        量到的 ``RasterGrid``；判不出网格返回 ``None``（原因写 ``logger.debug``）。
    """
    grid, diagnostics = _project_grid(
        gray,
        region=region,
        dark_threshold=dark_threshold,
        min_col_frac=min_col_frac,
        min_row_frac=min_row_frac,
        min_run_frac=min_run_frac,
        gap_px=gap_px,
        pad_px=pad_px,
        min_edge_gap_ratio=min_edge_gap_ratio,
    )
    if grid is None:
        logger.debug(
            "表格线几何: 判不出网格（reason=%s, region=%r, crop_px=%s）",
            diagnostics.get("reason"),
            region,
            diagnostics.get("crop_px"),
        )
    return grid


def detect_grid_from_png(
    image_bytes: bytes,
    *,
    region: tuple[float, float, float, float],
    dark_threshold: int = DARK_THRESHOLD,
    min_col_frac: float = MIN_COL_DARK_FRAC,
    min_row_frac: float = MIN_ROW_DARK_FRAC,
    min_run_frac: float = MIN_RUN_FRAC,
    gap_px: int = RUN_MERGE_GAP_PX,
    pad_px: int = REGION_PAD_PX,
    min_edge_gap_ratio: float = MIN_EDGE_GAP_RATIO,
) -> RasterGrid | None:
    """位图字节（PNG/JPEG…PIL 认得的都行）→ 灰度 → ``detect_grid_from_gray``。

    解不出位图（空字节 / 非图片字节）返回 ``None``，不抛、不惊动主链路。
    整页图与裁图都收：``region`` 按**这张图**的归一化坐标解释，调用方自己保证
    ``region`` 与图是同一坐标系。
    """
    gray = _gray_from_bytes(image_bytes)
    if gray is None:
        logger.debug("表格线几何: 图片字节解不出灰度图（%s 字节），判不出网格", len(image_bytes))
        return None
    return detect_grid_from_gray(
        gray,
        region=region,
        dark_threshold=dark_threshold,
        min_col_frac=min_col_frac,
        min_row_frac=min_row_frac,
        min_run_frac=min_run_frac,
        gap_px=gap_px,
        pad_px=pad_px,
        min_edge_gap_ratio=min_edge_gap_ratio,
    )


def cells_from_grid(grid: RasterGrid, *, page_no: int, texts: Sequence[str] | None = None) -> PageTableGeometry:
    """网格 → ``PageTableGeometry``（每格 ``row_span``/``col_span`` 都是 1）。

    ``texts`` 是**row-major** 的格子文本（长度必须正好 ``rows * cols``）。长度对不上
    （或没给）时**整列留空**并记 ``text_source="none"``：局部几何源拿不到引擎的
    ``pred_html``，按下标硬凑就是「把文字贴错格」，宁可留空让调用方另找文本。

    网格退化（``rows``/``cols`` 为 0）时返回 ``rows=0 / cols=0 / cells=()`` 的产物，
    与 ``table_geometry`` 里「量不到就给空」的纪律一致——调用方据空退回整表框。
    """
    rows, cols = grid.rows, grid.cols
    labels, text_source = _row_major_texts(texts, count=rows * cols)
    cells = tuple(
        TableCellBox(
            text=labels[row * cols + col] if labels else "",
            row=row,
            col=col,
            row_span=1,
            col_span=1,
            rect=_cell_rect(grid, row=row, col=col),
        )
        for row in range(rows)
        for col in range(cols)
    )
    diagnostics = dict(grid.diagnostics)
    diagnostics.update({"rows": rows, "cols": cols, "cell_count": len(cells), "text_source": text_source})
    return PageTableGeometry(
        page_no=page_no,
        engine=LOCAL_LINE_ENGINE,
        rows=rows,
        cols=cols,
        cells=cells,
        crop=FULL_PAGE_CROP,
        diagnostics=diagnostics,
        pp_bbox=_outer_bbox(grid),
    )


def _project_grid(
    gray: np.ndarray,
    *,
    region: Any,
    dark_threshold: int,
    min_col_frac: float,
    min_row_frac: float,
    min_run_frac: float,
    gap_px: int,
    pad_px: int,
    min_edge_gap_ratio: float,
) -> tuple[RasterGrid | None, dict[str, Any]]:
    """线检测本体：返回 ``(网格或 None, 诊断)``；``诊断["reason"]`` 说明成败原因。"""
    shape = _gray_shape(gray)
    if shape is None:
        return None, {"reason": REASON_IMAGE_UNREADABLE}
    page_w, page_h = shape
    diagnostics: dict[str, Any] = {
        "engine": LOCAL_LINE_ENGINE,
        "reason": REASON_OK,
        "image_size": [page_w, page_h],
        "pad_px": pad_px,
        "dark_threshold": dark_threshold,
    }
    crop = _region_pixels(region, page_w=page_w, page_h=page_h, pad=pad_px)
    if crop is None:
        diagnostics["reason"] = REASON_REGION_INVALID
        return None, diagnostics
    left, top, right, bottom = crop
    diagnostics["crop_px"] = [left, top, right, bottom]
    if right - left < MIN_REGION_PX or bottom - top < MIN_REGION_PX:
        diagnostics["reason"] = REASON_REGION_TOO_SMALL
        return None, diagnostics

    dark = np.asarray(gray)[top:bottom, left:right] < dark_threshold
    if not dark.any():
        diagnostics["reason"] = REASON_BLANK_REGION
        return None, diagnostics

    col_px, col_frac, col_run = _line_candidates(
        dark, axis="col", min_frac=min_col_frac, min_run_frac=min_run_frac, gap=gap_px
    )
    row_px, row_frac, row_run = _line_candidates(
        dark, axis="row", min_frac=min_row_frac, min_run_frac=min_run_frac, gap=gap_px
    )
    diagnostics.update(
        {
            "col_lines": len(col_px),
            "row_lines": len(row_px),
            "col_frac_min": _min_or_none(col_frac),
            "col_run_min": _min_or_none(col_run),
            "row_frac_min": _min_or_none(row_frac),
            "row_run_min": _min_or_none(row_run),
        }
    )
    if len(col_px) < MIN_LINES_PER_AXIS:
        diagnostics["reason"] = REASON_FEW_COL_LINES
        return None, diagnostics
    if len(row_px) < MIN_LINES_PER_AXIS:
        diagnostics["reason"] = REASON_FEW_ROW_LINES
        return None, diagnostics

    xs = _normalised_edges([left + position for position in col_px], span=page_w)
    ys = _normalised_edges([top + position for position in row_px], span=page_h)
    diagnostics["col_gap_min"] = _min_gap(xs)
    diagnostics["row_gap_min"] = _min_gap(ys)
    if not _usable_axis(xs, min_gap=min_edge_gap_ratio) or not _usable_axis(ys, min_gap=min_edge_gap_ratio):
        diagnostics["reason"] = REASON_DEGENERATE_GRID
        return None, diagnostics
    return RasterGrid(xs=xs, ys=ys, diagnostics=diagnostics), diagnostics


def _line_candidates(
    dark: np.ndarray, *, axis: str, min_frac: float, min_run_frac: float, gap: int
) -> tuple[list[int], list[float], list[float]]:
    """按投影 + 连续性找线（与 eval ``_line_candidates`` 同一实现）。

    Args:
        dark: 裁剪区二值图 ``(h, w)``，``True`` = 墨。
        axis: ``"col"``（竖线，沿 y 投影到 x）或 ``"row"``（横线，沿 x 投影到 y）。
        min_frac: 暗像素覆盖率下限（竖线除以高、横线除以宽）。
        min_run_frac: 最长连续游程下限（除以对应的区域边长）。
        gap: 同一条线的游程合并容差（px）。

    Returns:
        ``(线中心像素索引, 每条线的覆盖率, 每条线的最长游程占比)``，三者同序。
    """
    height, width = dark.shape
    if axis == "col":
        frac = dark.sum(axis=0) / height
        span = height
    else:
        frac = dark.sum(axis=1) / width
        span = width
    idx = np.flatnonzero(frac >= min_frac)
    centers: list[int] = []
    if idx.size:
        start = prev = int(idx[0])
        for raw in idx[1:]:
            position = int(raw)
            if position - prev <= gap:
                prev = position
                continue
            centers.append((start + prev) // 2)
            start = prev = position
        centers.append((start + prev) // 2)
    keep: list[int] = []
    fvals: list[float] = []
    rvals: list[float] = []
    for center in centers:
        line = dark[:, center] if axis == "col" else dark[center, :]
        run = _max_run(line) / span if span else 0.0
        if run < min_run_frac:
            continue  # 一堆短游程 = 文字，不是线
        keep.append(center)
        fvals.append(float(frac[center]))
        rvals.append(float(run))
    return keep, fvals, rvals


def _max_run(flags: np.ndarray) -> int:
    """最长连续 ``True`` 游程的长度（与 eval ``_max_run`` 同一实现）。"""
    best = current = 0
    for flag in flags:
        if flag:
            current += 1
            if current > best:
                best = current
        else:
            current = 0
    return best


def _gray_shape(gray: np.ndarray) -> tuple[int, int] | None:
    """整页灰度图 → ``(宽, 高)``；不是二维非空数组返回 ``None``。"""
    array = np.asarray(gray)
    if array.ndim != 2 or array.size == 0:
        return None
    height, width = int(array.shape[0]), int(array.shape[1])
    if height <= 0 or width <= 0:  # pragma: no cover - ndim==2 且非空时不可能出现
        return None
    return width, height


def _region_pixels(region: Any, *, page_w: int, page_h: int, pad: int) -> tuple[int, int, int, int] | None:
    """页面归一化区域 → 页内像素裁剪框 ``(left, top, right, bottom)``；不成立返回 ``None``。

    越界（任一值落在 0–1 之外）**不夹取也不猜**：那说明调用方给错了坐标系（例如把
    permille bbox 直接传进来），夹一下就会把整页当成表格。
    """
    values = _as_floats(region, count=4)
    if values is None:
        return None
    x0, y0, x1, y1 = values
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        return None
    left = max(0, round(x0 * page_w) - pad)
    right = min(page_w, round(x1 * page_w) + pad)
    top = max(0, round(y0 * page_h) - pad)
    bottom = min(page_h, round(y1 * page_h) + pad)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _as_floats(raw: Any, *, count: int) -> tuple[float, ...] | None:
    """任意形状 → 恰好 ``count`` 个有限浮点数；转不了返回 ``None``。"""
    if not isinstance(raw, (list, tuple)) or len(raw) != count:
        return None
    values: list[float] = []
    for item in raw:
        try:
            number = float(item)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(number):
            return None
        values.append(number)
    return tuple(values)


def _gray_from_bytes(image_bytes: bytes) -> np.ndarray | None:
    """位图字节 → 整页灰度二维数组；解不出来返回 ``None``。

    只 catch ``(OSError, ValueError)``：``PIL.UnidentifiedImageError`` 是 ``OSError``
    的子类，截断文件也抛 ``OSError``；其余异常说明是程序 bug，应该炸出来而不是吞掉。
    """
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        return None
    try:
        with Image.open(io.BytesIO(bytes(image_bytes))) as image:
            return np.asarray(image.convert("L"), dtype=np.uint8)
    except (OSError, ValueError):
        return None


def _normalised_edges(positions: Sequence[int | float], *, span: int) -> tuple[float, ...]:
    """像素边界 → 页面归一化边界（升序、保留 ``_EDGE_PRECISION`` 位）。"""
    return tuple(round(position / span, _EDGE_PRECISION) for position in positions)


def _usable_axis(edges: Sequence[float], *, min_gap: float) -> bool:
    """边界轴是否可用：严格递增且相邻间距 ≥ ``min_gap``。

    归一化后不再严格递增 = 两条线被四舍五入到同一个值（间距 1px 的假双线），
    那样的格子宽度为 0，画出来是无意义的框。间距 < ``min_gap`` 同理。
    """
    return all(later - earlier >= min_gap for earlier, later in pairwise(edges))


def _min_gap(edges: Sequence[float]) -> float | None:
    """相邻边界的最小间距；不足两条边界返回 ``None``（无法评估）。"""
    gaps = [later - earlier for earlier, later in pairwise(edges)]
    return round(min(gaps), _EDGE_PRECISION) if gaps else None


def _min_or_none(values: Sequence[float]) -> float | None:
    """序列最小值（保留 3 位）；空序列返回 ``None``。"""
    return round(min(values), 3) if values else None


def _row_major_texts(texts: Sequence[str] | None, *, count: int) -> tuple[list[str], str]:
    """``texts`` → ``(row-major 文本, text_source)``；长度不符/未给时整列留空。

    绝不截断、绝不补齐：格子数由几何决定，文本数由调用方决定，两者不等时无法证明
    对应关系（同 ``table_geometry.assign_cell_texts`` 拒绝「按下标 zip」的理由）。
    """
    if not texts:
        return [], TEXT_SOURCE_NONE
    if len(texts) != count:
        logger.debug("表格线几何: texts 长度 %d ≠ 格子数 %d，格子文本整列留空", len(texts), count)
        return [], TEXT_SOURCE_NONE
    return [str(text).strip() for text in texts], TEXT_SOURCE_PROVIDED


def _cell_rect(grid: RasterGrid, *, row: int, col: int) -> dict[str, float]:
    """``(row, col)`` 对应的页面归一化矩形 ``{"x","y","w","h"}``。"""
    left, top = grid.xs[col], grid.ys[row]
    return {
        "x": round(left, _EDGE_PRECISION),
        "y": round(top, _EDGE_PRECISION),
        "w": round(grid.xs[col + 1] - left, _EDGE_PRECISION),
        "h": round(grid.ys[row + 1] - top, _EDGE_PRECISION),
    }


def _outer_bbox(grid: RasterGrid) -> dict[str, float] | None:
    """网格的外接矩形（页面归一化 ``{"x","y","w","h"}``）；退化网格返回 ``None``。

    供 ``table_geometry.match_tables_to_blocks`` 与 MinerU 表块做 IoU 配对：
    本源的「表框」就是最外两条线的外接框，不需要额外参数。
    """
    if grid.rows <= 0 or grid.cols <= 0:
        return None
    left, top = grid.xs[0], grid.ys[0]
    return {
        "x": round(left, _EDGE_PRECISION),
        "y": round(top, _EDGE_PRECISION),
        "w": round(grid.xs[-1] - left, _EDGE_PRECISION),
        "h": round(grid.ys[-1] - top, _EDGE_PRECISION),
    }
