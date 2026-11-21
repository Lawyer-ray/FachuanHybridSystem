"""``table_geometry_lines``：本地表格线投影几何源（纯函数，不连库、不连网）。

## 这个文件在守什么

PP-StructureV3 对 7 个候选表页直接回 ``table_res_list=[]``（``facts/FACTS.md`` SF-16/SF-17），
这些页只能整表框。本模块换一条路：**不靠引擎**，直接在页图上做暗像素投影量墨线网格。
线检测与 ``docs/analysis/table-cell-geometry-2026-11-21/eval/measure_box_error.py`` 同源，
阈值口径一个字都没改（``DARK_THRESHOLD=140`` / 竖线覆盖 ≥40% 区域高 / 横线覆盖 ≥30% 区域宽 /
连续性 ≥20% / 2px 游程合并），所以这里用**页图真值**当回归基线而不是「跑一遍记下来」：

| 用例 | 钉住的东西 |
|:--|:--|
| p10 真实页 | 真值口径：6 列 6 行，列/行边界偏差 ≤0.004 页（实测列 0.0000 / 行 0.0006） |
| 合成网格图 | 基本换算（像素 → 页面归一化）与 1px 精度 |
| 文字竖排 / 单条竖线 / 页眉横线 | **判不出就是 None**：不许把文字笔画当成表格线，也不许编坐标 |
| region 越界/退化、空 bytes、非图片 | 输入脏就返回 None，不抛 |
| ``cells_from_grid`` | 行列连续、矩形落在网格内、``texts`` 长度不符时降级留空 |

## 为什么合成图是**运行时造**的，不是 ``fixtures/pdf_splitting/*.png``

仓库 ``.gitignore`` 有一条 `*.png`（只有 `backend/apps/**/static/**/*.png` 例外），
所以放进 ``tests/ci/fixtures/`` 的 PNG **不会被 git 收录**；而 ``CLAUDE.md`` 明令禁止
``git add -f``。真按 fixture 文件写，本地能跑、CI 上必然 ``FileNotFoundError``
（假绿 → 真红）。因此合成网格图改成用 PIL 在测试里按**显式像素坐标**造字节再走
``detect_grid_from_png``：既「永远跑」，又顺带覆盖了「字节 → 灰度」这条路径。

p10 真实页那条用例需要本机 job 的 PDF（``media/`` 同样不入库），不存在就 ``pytest.skip``。
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from apps.pdf_splitting.services.split import table_geometry_lines as lines

#: 仓库根（``backend/tests/ci/unit/pdf_splitting/`` 往上五层）。
REPO_ROOT = Path(__file__).resolve().parents[5]
#: 真实卷宗 job（``docs/analysis/table-cell-geometry-2026-11-21/`` 全部实测数字的来源）。
P10_JOB_ID = "523fabce-3004-4a41-8c12-c0f040f1a898"
P10_PDF = (
    REPO_ROOT / "backend" / "apiSystem" / "media" / "pdf_splitting" / "jobs" / P10_JOB_ID / "source" / "original.pdf"
)

#: p10 的 MinerU table 块 bbox（``analysis/pages.json`` → ``layout.blocks[2].bbox``，
#: permille/1000）。**不是** PP 的裁框：eval 与 ``table_geometry.py`` 都用这个区域找线。
P10_REGION = (0.06, 0.198, 0.966, 0.890)

#: p10 页图线检测真值（``facts/raw/p10_raw.json``，与 ``test_table_geometry.py`` 同一组数字）。
P10_COL_EDGES = (0.0645, 0.1323, 0.1806, 0.4613, 0.8492, 0.8927, 0.9645)
P10_ROW_EDGES = (0.2002, 0.2487, 0.4159, 0.4963, 0.6035, 0.7707, 0.8899)
#: 验收容差（页宽/页高）。实测残差列 0.0000 / 行 0.0006，取 0.004 留 6 倍余量。
P10_TOL = 0.004

#: 合成网格图：200×300 白底 + 4 条竖线 3 条横线 → 3 列 4 行。
GRID_WIDTH, GRID_HEIGHT = 200, 300
GRID_COLUMNS_PX = (10, 70, 130, 190)
GRID_ROWS_PX = (20, 80, 140, 200, 260)
#: 1px = 1/200 = 0.005 页宽；归一化保留 4 位再四舍五入，所以取 0.001 足够严。
SYNTHETIC_TOL = 0.001


def _blank(width: int = GRID_WIDTH, height: int = GRID_HEIGHT) -> np.ndarray:
    """纯白灰度图（``uint8``，255 = 纸底）。"""
    return np.full((height, width), 255, dtype=np.uint8)


def _draw_vertical(gray: np.ndarray, x: int, *, top: int, bottom: int) -> None:
    gray[top:bottom, x] = 0


def _draw_horizontal(gray: np.ndarray, y: int, *, left: int, right: int) -> None:
    gray[y, left:right] = 0


def _png_bytes(gray: np.ndarray) -> bytes:
    """灰度数组 → PNG 字节（走真的解码路径，不做 matrix 直通）。"""
    buffer = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buffer, format="PNG")
    return buffer.getvalue()


def _grid_image() -> np.ndarray:
    """200×300 的合成网格：4 条竖线（y 20–260）+ 3 条横线（x 10–190）。"""
    gray = _blank()
    for x in GRID_COLUMNS_PX:
        _draw_vertical(gray, x, top=20, bottom=261)
    for y in GRID_ROWS_PX:
        _draw_horizontal(gray, y, left=10, right=191)
    return gray


def _grid_png() -> bytes:
    return _png_bytes(_grid_image())


@contextmanager
def _debug_messages() -> Iterator[list[str]]:
    """抓 ``apps.pdf_splitting`` 的 DEBUG 消息。

    不用 ``caplog``：``apiSystem.settings.LOGGING`` 里 ``apps`` 这个 logger 是
    ``propagate=False``，记录到不了 root，pytest 挂在 root 的 handler 收不到。
    「判不出网格」的原因按契约走 ``logger.debug``，所以这里直接挂 handler 验它。
    """

    class _Collector(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.messages: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.messages.append(record.getMessage())

    collector = _Collector()
    target = logging.getLogger("apps.pdf_splitting")
    previous_level = target.level
    target.setLevel(logging.DEBUG)
    target.addHandler(collector)
    try:
        yield collector.messages
    finally:
        target.removeHandler(collector)
        target.setLevel(previous_level)


# ── 合成网格：基本换算 ────────────────────────────────────────


class TestSyntheticGrid:
    def test_合成网格图检出3列4行且边界落在1px内(self) -> None:
        grid = lines.detect_grid_from_png(_grid_png(), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is not None
        assert (grid.cols, grid.rows) == (3, 4)
        assert grid.xs == pytest.approx(tuple(px / GRID_WIDTH for px in GRID_COLUMNS_PX), abs=SYNTHETIC_TOL)
        assert grid.ys == pytest.approx(tuple(px / GRID_HEIGHT for px in GRID_ROWS_PX), abs=SYNTHETIC_TOL)
        assert grid.diagnostics["reason"] == lines.REASON_OK
        assert (grid.diagnostics["col_lines"], grid.diagnostics["row_lines"]) == (4, 5)
        assert grid.diagnostics["engine"] == lines.LOCAL_LINE_ENGINE

    def test_region只取局部时返回页面绝对坐标(self) -> None:
        """``region`` 是「在哪儿找线」，不是「坐标原点」——量到的仍是整页归一化位置。"""
        # 区域 x≤0.5 / y≤0.34，外扩 6px 后刚好只剩 x=10/70 两条竖线、y=20/80 两条横线
        grid = lines.detect_grid_from_png(_grid_png(), region=(0.0, 0.0, 0.5, 0.34))

        assert grid is not None
        assert grid.xs == pytest.approx((10 / GRID_WIDTH, 70 / GRID_WIDTH), abs=SYNTHETIC_TOL)
        assert grid.ys == pytest.approx((20 / GRID_HEIGHT, 80 / GRID_HEIGHT), abs=SYNTHETIC_TOL)


# ── 判不出网格必须是 None（不许编坐标）──────────────────────────


class TestNoGrid:
    def test_纯白图判不出网格(self) -> None:
        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(_png_bytes(_blank()), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any(lines.REASON_BLANK_REGION in message for message in messages)

    def test_文字竖排冒充竖线判不出网格(self) -> None:
        """字符笔画能过 40% 覆盖率，但过不了 20% 连续游程（真表格线是贯穿的）。"""
        gray = _blank()
        for x in range(20, GRID_WIDTH, 20):
            for top in range(20, 280, 8):
                _draw_vertical(gray, x, top=top, bottom=top + 5)

        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(_png_bytes(gray), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any(lines.REASON_FEW_COL_LINES in message for message in messages)

    def test_只有一条竖线判不出网格(self) -> None:
        gray = _blank()
        _draw_vertical(gray, 100, top=20, bottom=281)

        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(_png_bytes(gray), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any(lines.REASON_FEW_COL_LINES in message for message in messages)

    def test_页眉横线噪声不算表格(self) -> None:
        """两条竖线 + 一条页眉横线：竖线够但横线只有 1 条，围不出格子。"""
        gray = _blank()
        for x in (40, 160):
            _draw_vertical(gray, x, top=20, bottom=281)
        _draw_horizontal(gray, 15, left=0, right=GRID_WIDTH)

        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(_png_bytes(gray), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any(lines.REASON_FEW_ROW_LINES in message for message in messages)

    def test_边界间距过小判网格退化(self) -> None:
        """2px 游程合并挡不住的两条「假双线」（间距 3px / 2000px 页宽 = 0.0015）。"""
        gray = _blank(width=2000)
        for x in (100, 103, 300, 600, 900):
            _draw_vertical(gray, x, top=20, bottom=281)
        for y in (20, 150, 280):
            _draw_horizontal(gray, y, left=20, right=1980)

        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(_png_bytes(gray), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any(lines.REASON_DEGENERATE_GRID in message for message in messages)


# ── 输入健壮性：脏参数一律 None，不抛 ──────────────────────────


class TestRegionAndInputRobustness:
    @pytest.mark.parametrize(
        "region",
        [
            pytest.param((1.10, 0.10, 1.50, 0.50), id="x 越界"),
            pytest.param((-0.10, 0.10, 0.50, 0.50), id="x 为负"),
            pytest.param((0.10, 0.10, 0.50, 1.20), id="y 越界"),
            pytest.param((0.50, 0.10, 0.50, 0.60), id="宽为 0"),
            pytest.param((0.10, 0.60, 0.50, 0.60), id="高为 0"),
            pytest.param((0.60, 0.10, 0.40, 0.50), id="左右反序"),
            pytest.param((float("nan"), 0.10, 0.50, 0.60), id="NaN"),
            pytest.param((float("inf"), 0.10, 0.50, 0.60), id="inf"),
            pytest.param((0.10, 0.10, 0.50), id="只有三个数"),
            pytest.param(None, id="None"),
            pytest.param("0,0,1,1", id="字符串"),
        ],
    )
    def test_region不成立一律返回None(self, region: object) -> None:
        # 同一张图用合法 region 是能出网格的（见 TestSyntheticGrid），所以 None 只能来自 region 本身
        assert lines.detect_grid_from_png(_grid_png(), region=region) is None  # type: ignore[arg-type]

    def test_裁剪区小于下限返回None(self) -> None:
        tiny = _blank(width=5, height=5)

        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(_png_bytes(tiny), region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any(lines.REASON_REGION_TOO_SMALL in message for message in messages)

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(b"", id="空字节"),
            pytest.param(b"not an image at all", id="非图片字节"),
            pytest.param(b"%PDF-1.4\n", id="PDF 头"),
        ],
    )
    def test_空字节与非图片字节返回None(self, payload: bytes) -> None:
        with _debug_messages() as messages:
            grid = lines.detect_grid_from_png(payload, region=(0.0, 0.0, 1.0, 1.0))

        assert grid is None
        assert any("解不出灰度图" in message for message in messages)


# ── 网格 → PageTableGeometry ──────────────────────────────────


def _grid_geometry(texts: list[str] | None = None) -> tuple[lines.RasterGrid, object]:
    grid = lines.detect_grid_from_png(_grid_png(), region=(0.0, 0.0, 1.0, 1.0))
    assert grid is not None
    return grid, lines.cells_from_grid(grid, page_no=52, texts=texts)


class TestCellsFromGrid:
    def test_行列数正确且row_col连续(self) -> None:
        _grid, geometry = _grid_geometry()

        assert (geometry.rows, geometry.cols) == (4, 3)
        assert [(cell.row, cell.col) for cell in geometry.cells] == [(row, col) for row in range(4) for col in range(3)]
        assert all((cell.row_span, cell.col_span) == (1, 1) for cell in geometry.cells)
        # 坐标是页面的：本源的 crop 恒为整页（同批量送整页那条路径）
        assert geometry.crop == lines.FULL_PAGE_CROP
        assert geometry.engine == lines.LOCAL_LINE_ENGINE
        assert geometry.page_no == 52
        assert geometry.diagnostics["cell_count"] == 12

    def test_rect落在网格范围内且相邻格共边(self) -> None:
        grid, geometry = _grid_geometry()

        left, top, right, bottom = grid.xs[0], grid.ys[0], grid.xs[-1], grid.ys[-1]
        for cell in geometry.cells:
            assert left <= cell.rect["x"] < cell.rect["x"] + cell.rect["w"] <= right
            assert top <= cell.rect["y"] < cell.rect["y"] + cell.rect["h"] <= bottom
        first = geometry.cells[0]
        assert first.rect == pytest.approx(
            {"x": 10 / GRID_WIDTH, "y": 20 / GRID_HEIGHT, "w": 60 / GRID_WIDTH, "h": 60 / GRID_HEIGHT}, abs=1e-3
        )
        # 同一行相邻两格：右边界 = 下一格左边界（网格线是共用的）
        assert geometry.cells[0].rect["x"] + geometry.cells[0].rect["w"] == pytest.approx(
            geometry.cells[1].rect["x"], abs=1e-4
        )
        assert geometry.pp_bbox is not None
        assert geometry.pp_bbox["w"] == pytest.approx(180 / GRID_WIDTH, abs=1e-3)
        assert geometry.pp_bbox["h"] == pytest.approx(240 / GRID_HEIGHT, abs=1e-3)

    def test_texts长度匹配按row_major填入(self) -> None:
        labels = [f"行{row}列{col}" for row in range(4) for col in range(3)]
        _grid, geometry = _grid_geometry(labels)

        assert [cell.text for cell in geometry.cells] == labels
        assert geometry.diagnostics["text_source"] == lines.TEXT_SOURCE_PROVIDED

    @pytest.mark.parametrize("size", [0, 11, 13], ids=["空列表", "少一个", "多一个"])
    def test_texts长度不匹配降级为留空(self, size: int) -> None:
        """长度对不上就无法证明对应关系：整列留空，绝不按下标硬凑。"""
        _grid, geometry = _grid_geometry([f"t{index}" for index in range(size)])

        assert [cell.text for cell in geometry.cells] == [""] * 12
        assert geometry.diagnostics["text_source"] == lines.TEXT_SOURCE_NONE

    def test_退化网格返回空产物(self) -> None:
        degenerate = lines.RasterGrid(xs=(), ys=(), diagnostics={"reason": lines.REASON_DEGENERATE_GRID})

        geometry = lines.cells_from_grid(degenerate, page_no=50, texts=["会被丢掉"])

        assert (geometry.rows, geometry.cols, geometry.cells) == (0, 0, ())
        assert geometry.pp_bbox is None
        assert geometry.diagnostics["text_source"] == lines.TEXT_SOURCE_NONE


# ── 真实页回归（本机 job，文件不在就 skip）──────────────────────


def _render_gray(pdf_path: Path, page_no: int, *, dpi: int = 150) -> np.ndarray:
    """整页灰度渲染（与 eval / ``facts/raw`` 同口径：150dpi + ``csGRAY``）。"""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as document:
        pixmap = document[page_no - 1].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
        samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
        return samples.reshape(pixmap.height, pixmap.stride)[:, : pixmap.width].copy()


class TestRealPageRegression:
    def test_p10真实页检出6列6行且边界在容差内(self) -> None:
        """p10 是全框线的打印表格：真值来自页图实测（列偏差 0.0000 / 行偏差 0.0006）。"""
        if not P10_PDF.exists():
            pytest.skip(f"本机没有该 job 的 PDF（media/ 不入库）：{P10_PDF}")

        grid = lines.detect_grid_from_gray(_render_gray(P10_PDF, 10), region=P10_REGION)

        assert grid is not None
        assert (grid.cols, grid.rows) == (6, 6)
        assert grid.xs == pytest.approx(P10_COL_EDGES, abs=P10_TOL)
        assert grid.ys == pytest.approx(P10_ROW_EDGES, abs=P10_TOL)
        assert max(abs(a - b) for a, b in zip(grid.xs, P10_COL_EDGES, strict=True)) <= P10_TOL
        assert max(abs(a - b) for a, b in zip(grid.ys, P10_ROW_EDGES, strict=True)) <= P10_TOL
        # 竖线覆盖率/连续性必须明显高于阈值，否则这条回归只是「碰巧过了」
        assert grid.diagnostics["col_frac_min"] >= lines.MIN_COL_DARK_FRAC
        assert grid.diagnostics["col_run_min"] >= lines.MIN_RUN_FRAC

    def test_p10网格转格子后每个格子都在表块bbox内(self) -> None:
        """本源的格子是量出来的：6×6 格全部落在 MinerU 表块 bbox 内（无越界）。"""
        if not P10_PDF.exists():
            pytest.skip(f"本机没有该 job 的 PDF（media/ 不入库）：{P10_PDF}")

        grid = lines.detect_grid_from_gray(_render_gray(P10_PDF, 10), region=P10_REGION)
        assert grid is not None
        geometry = lines.cells_from_grid(grid, page_no=10)

        assert len(geometry.cells) == 36
        for cell in geometry.cells:
            assert cell.rect["x"] >= P10_REGION[0] - P10_TOL
            assert cell.rect["y"] >= P10_REGION[1] - P10_TOL
            assert cell.rect["x"] + cell.rect["w"] <= P10_REGION[2] + P10_TOL
            assert cell.rect["y"] + cell.rect["h"] <= P10_REGION[3] + P10_TOL
