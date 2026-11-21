"""``table_geometry``：裁图像素 → 页面归一化 + 真实格子网格（纯函数，不连网、不连库）。

## 为什么这些断言长这样

缺陷本体（PR-2 才修）是「表格 bbox ÷ 行列数」均分推格子（``markdown_builder.py:376-377``）：
列宽不等时整块框会指到隔壁列——p10 的「件数」列偏 0.185 页宽（≈110pt）。
这里用**同一次真实调用的响应**把「量到的格子」钉在页图实测网格上，容差 0.004 页。

## p10 真实数据（``facts/raw/p10_raw.json`` 实测，数字别凭记忆改）

- 裁图像素 1555 × 1660（= 559.8 × 597.6 pt @200dpi）；
- 裁图在页面上的归一化区域 ``(0.04956, 0.18898, 0.98995, 0.89881)``——由 clip
  ``(29.5, 159.1, 589.3, 756.7) pt @200dpi`` 反算。⚠️ 它**不是**表格 bbox
  （0.06/0.198/0.966/0.890），两者差 0.026 页宽，见 ``test_把裁框当成整表_bbox_会偏出容差``；
- 33 个 cell = ``pred_html`` 的 33 个 ``<td>``（1:1 同序，row-major），6 行 × 6 列；
- 页图线检测实测边界：列 ``0.0645/0.1323/0.1806/0.4613/0.8492/0.8927/0.9645``、
  行 ``0.2002/0.2487/0.4159/0.4963/0.6035/0.7707/0.8899``（本页物理只有 6 行）。

实测换算后与页图网格的最大偏差：列 **0.0027**、行 **0.0025**（容差取 0.004）。

fixture ``tests/ci/fixtures/pdf_splitting/pp_structure_p10_table.json`` 是这份响应的
最小裁剪版，且已脱敏（当事人姓名/单位名/地址替换为甲/乙/某，结构与数字原样）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps.pdf_splitting.services.split import table_geometry

#: 裁剪后的真实响应（``result.layoutParsingResults[0].prunedResult`` + ``ocrResults[0]``）。
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "pdf_splitting" / "pp_structure_p10_table.json"
)

# ── p10 真实数据（逐值可在 facts/raw/p10_raw.json 复核）──
P10_CROP = (0.04956, 0.18898, 0.98995, 0.89881)
P10_CROP_SIZE = (1555, 1660)
P10_MEASURED_COL_EDGES = (0.0645, 0.1323, 0.1806, 0.4613, 0.8492, 0.8927, 0.9645)
P10_MEASURED_ROW_EDGES = (0.2002, 0.2487, 0.4159, 0.4963, 0.6035, 0.7707, 0.8899)
P10_CELLS = 33
P10_ROWS = 6
P10_COLS = 6
#: 任务规定的容差（页宽/页高）。实测最大偏差 0.0027，取 0.004 留余量。
TOL = 0.004


def _p10_table() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    table = payload["result"]["layoutParsingResults"][0]["prunedResult"]["table_res_list"][0]
    assert isinstance(table, dict)
    return table


def _p10_cells(**kwargs: Any) -> tuple[table_geometry.TableCellBox, ...]:
    """p10 的 33 个像素框 → TableCellBox（row-major）。

    注意 ``table_ocr_pred.rec_texts`` 是**行级** OCR 文本（实测 70 条），不是 33 个格子的
    文本，不能按同序贴到格子上；cell 文本由 ``pred_html`` 走 ``md_table.parse_grid`` 取。
    """
    table = _p10_table()
    return table_geometry.build_cell_boxes(
        table["cell_box_list"],
        crop=P10_CROP,
        crop_size=P10_CROP_SIZE,
        **kwargs,
    )


def _cluster(values: list[float], tol: float) -> list[float]:
    ordered = sorted(values)
    groups: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - groups[-1][-1] <= tol:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _edges(cells: Any, axis: str) -> list[float]:
    """格子集合的边界线（取所有 left/right 或 top/bottom 再聚类）。"""
    if axis == "x":
        raw = [cell.rect["x"] for cell in cells] + [cell.rect["x"] + cell.rect["w"] for cell in cells]
    else:
        raw = [cell.rect["y"] for cell in cells] + [cell.rect["y"] + cell.rect["h"] for cell in cells]
    # 页空间容差 0.006：足够吸收 cell 边的 1–2px 抖动（实测最大 2.3px ≈ 0.0014 页宽），
    # 又远小于最窄列宽（0.049 页宽），不会把相邻列并成一条。
    return _cluster(raw, 0.006)


# ── 纯函数：像素 → 页面 ────────────────────────────────────────


class TestMapPixelRect:
    def test_局部裁图的线性换算(self) -> None:
        rect = table_geometry.map_pixel_rect((0, 0, 100, 200), crop=(0.2, 0.1, 0.6, 0.5), crop_size=(400, 400))

        assert rect is not None
        assert rect["x"] == pytest.approx(0.2)
        assert rect["y"] == pytest.approx(0.1)
        assert rect["w"] == pytest.approx(0.1)
        assert rect["h"] == pytest.approx(0.2)

    def test_裁图等于整页时是恒等映射(self) -> None:
        rect = table_geometry.map_pixel_rect((100, 200, 300, 400), crop=(0.0, 0.0, 1.0, 1.0), crop_size=(1000, 1000))

        assert rect is not None
        assert rect["x"] == pytest.approx(0.1)
        assert rect["y"] == pytest.approx(0.2)
        assert rect["w"] == pytest.approx(0.2)
        assert rect["h"] == pytest.approx(0.2)

    def test_越界按_0_1_裁剪(self) -> None:
        rect = table_geometry.map_pixel_rect((-10, 50, 110, 60), crop=(0.0, 0.0, 1.0, 1.0), crop_size=(100, 100))

        assert rect is not None
        assert rect["x"] == 0.0
        assert rect["w"] == pytest.approx(1.0)
        assert rect["y"] == pytest.approx(0.5)
        assert rect["h"] == pytest.approx(0.1)

    @pytest.mark.parametrize(
        "rect_px",
        [
            pytest.param((10, 10, 10, 50), id="宽为 0"),
            pytest.param((10, 10, 50, 10), id="高为 0"),
            pytest.param((50, 0, 10, 10), id="负宽（顺手排了个序也不许）"),
            pytest.param((1, 2, 3), id="只有 3 个数"),
            pytest.param(None, id="None"),
            pytest.param("1234", id="字符串"),
            pytest.param((0, 0, float("nan"), 10), id="NaN"),
        ],
    )
    def test_退化框返回_None(self, rect_px: Any) -> None:
        assert table_geometry.map_pixel_rect(rect_px, crop=(0.0, 0.0, 1.0, 1.0), crop_size=(100, 100)) is None

    @pytest.mark.parametrize(
        ("crop", "crop_size"),
        [
            pytest.param((0.0, 0.0, 1.0, 1.0), (0, 0), id="裁图尺寸为 0"),
            pytest.param((0.0, 0.0, 1.0, 1.0), (-5, 10), id="裁图尺寸为负"),
            pytest.param((0.5, 0.0, 0.5, 1.0), (100, 100), id="裁框宽为 0"),
            pytest.param((0.0, 0.5, 1.0, 0.5), (100, 100), id="裁框高为 0"),
            pytest.param((0.0, 0.0, 1.0), (100, 100), id="裁框不是 4 元组"),
        ],
    )
    def test_参数不可用时返回_None_而不是除零(self, crop: Any, crop_size: Any) -> None:
        assert table_geometry.map_pixel_rect((0, 0, 10, 10), crop=crop, crop_size=crop_size) is None


# ── p10 真实网格 ───────────────────────────────────────────────


class TestP10MeasuredGrid:
    """用真实响应 + 真实裁图区域，把「量到的格子」钉在页图实测网格上。"""

    def test_33_格_6_行_6_列(self) -> None:
        cells = _p10_cells()

        assert len(cells) == P10_CELLS
        assert table_geometry.grid_shape(cells) == (P10_ROWS, P10_COLS)

    def test_列边界对上页图实测网格(self) -> None:
        cells = _p10_cells()

        edges = _edges(cells, "x")
        assert len(edges) == P10_COLS + 1
        worst = max(abs(got - want) for got, want in zip(edges, P10_MEASURED_COL_EDGES, strict=True))
        # 实测 0.0027；容差 0.004。现行均分在同一基准上的最大偏差是 0.185（约 46 倍）。
        assert worst <= TOL, f"列边界最大偏差 {worst:.4f} > {TOL}；converted={[round(v, 4) for v in edges]}"

    def test_行边界对上页图实测网格(self) -> None:
        cells = _p10_cells()

        edges = _edges(cells, "y")
        assert len(edges) == P10_ROWS + 1
        worst = max(abs(got - want) for got, want in zip(edges, P10_MEASURED_ROW_EDGES, strict=True))
        assert worst <= TOL, f"行边界最大偏差 {worst:.4f} > {TOL}；converted={[round(v, 4) for v in edges]}"

    def test_件数列落在真实位置_不再落进证明内容列(self) -> None:
        """缺陷的原始症状：「件数」列的框整块落进「证明内容」列。

        均分列边界是 ``0.06 + k*0.151``（0.906/6），第 5 列 = 0.664–0.815，
        而真实「件数」列是 0.8492–0.8927 → 偏 **0.185 页宽（≈110pt）**。
        """
        cells = _p10_cells()

        jianshu = [cell for cell in cells if cell.col == 4]
        assert len(jianshu) == P10_ROWS, "表头 + 5 个数据行都在这一列"
        for cell in jianshu:
            assert abs(cell.rect["x"] - 0.8492) <= TOL
            assert abs(cell.rect["x"] + cell.rect["w"] - 0.8927) <= TOL
            # 均分算出来的位置必须**不**再出现（0.664 ≤ x < 0.815 一带）
            assert not (0.60 < cell.rect["x"] < 0.83)

    def test_首列合并单元格的_row_span(self) -> None:
        """首列是「当事人申请及受理材料」rowspan=2、「证据材料」rowspan=3。

        p10 的 ``pred_html`` 里这两个属性是明写的（33 td 覆盖 36 个格位），
        而 ``cell_box_list`` 对应格子的高度也确实是 2 行/3 行高，所以**只能**从框推出来
        ——解析层不保证 span 属性总在 HTML 里。
        """
        cells = _p10_cells()
        by_pos = {(cell.row, cell.col): cell for cell in cells}

        assert by_pos[(1, 0)].row_span == 2
        assert by_pos[(3, 0)].row_span == 3
        assert all(cell.col_span == 1 for cell in cells), "这张表没有 colspan"

    def test_行索引严格_row_major(self) -> None:
        cells = _p10_cells()

        keys = [(cell.row, cell.col) for cell in cells]
        assert keys == sorted(keys), "输出必须 row-major（与 td 同序的前提）"
        per_row = [sum(1 for cell in cells if cell.row == row) for row in range(P10_ROWS)]
        assert per_row == [6, 6, 5, 6, 5, 5]

    def test_把裁框当成整表_bbox_会偏出容差(self) -> None:
        """为什么裁图区域必须显式携带、不能假定 = 表格 bbox。

        整表 bbox 是 ``x=0.06 y=0.198 w=0.906 h=0.692``（→ 0.06–0.966 / 0.198–0.890），
        而这次裁图实际用的是 0.0496–0.9900 / 0.1890–0.8988（clip 29.5/159.1 → 589.3/756.7 pt）。
        差 0.02 页宽看起来小，落到列边界上就是 **0.0256 页宽 = 容差的 6.4 倍**。
        """
        table = _p10_table()
        cells = table_geometry.build_cell_boxes(
            table["cell_box_list"],
            crop=(0.06, 0.198, 0.966, 0.890),
            crop_size=P10_CROP_SIZE,
        )

        edges = _edges(cells, "x")
        worst = max(abs(got - want) for got, want in zip(edges, P10_MEASURED_COL_EDGES, strict=True))
        assert worst > 5 * TOL, f"假定裁框=整表 bbox 居然也过了？worst={worst:.4f}"


# ── span 的长宽推导（合成小样本，便于看清几何） ─────────────────


class TestSpanGeometry:
    def test_colspan_的宽度是两列之和(self) -> None:
        # 2 列（0–120 / 120–200 px），首行一个 colspan=2 的格子
        cells = table_geometry.build_cell_boxes(
            [[0, 0, 200, 50], [0, 50, 120, 100], [120, 50, 200, 100]],
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=(200, 100),
        )

        assert table_geometry.grid_shape(cells) == (2, 2)
        header = cells[0]
        assert (header.row, header.col, header.row_span, header.col_span) == (0, 0, 1, 2)
        # 宽 = 两列之和 = 整宽；高 = 半页
        assert header.rect["w"] == pytest.approx(1.0)
        assert header.rect["h"] == pytest.approx(0.5)
        assert cells[1].rect["w"] == pytest.approx(0.6)
        assert cells[2].rect["w"] == pytest.approx(0.4)

    def test_rowspan_的高度是两行之高(self) -> None:
        cells = table_geometry.build_cell_boxes(
            [[0, 0, 100, 120], [100, 0, 200, 50], [100, 50, 200, 120]],
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=(200, 120),
        )

        assert table_geometry.grid_shape(cells) == (2, 2)
        left = cells[0]
        assert (left.row, left.col, left.row_span, left.col_span) == (0, 0, 2, 1)
        assert left.rect["h"] == pytest.approx(1.0)

    def test_文本按几何归属_与输入顺序无关(self) -> None:
        """PR-2 拆掉的正是「按下标 zip」：``cell_box_list`` 的顺序不是契约。

        这里框的顺序是 ``[右, 左]``（相邻项 x0 逆序，批量样本 p71/p72/p54/p20 的形态），
        文本顺序又与之不同；按几何归属后每个格子的文字必须跟着**自己的位置**走。
        """
        cells = table_geometry.build_cell_boxes(
            [[100, 0, 200, 50], [0, 0, 100, 50]],
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=(200, 100),
        )

        filled, source = table_geometry.assign_cell_texts(
            cells,
            lines=[("右", [100, 0, 200, 50]), ("左", [0, 0, 100, 50])],
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=(200, 100),
        )

        # 输出始终 row-major：左边那格是 (0,0)，右边是 (0,1)
        assert [(cell.row, cell.col) for cell in cells] == [(0, 0), (0, 1)]
        assert [cell.text for cell in filled] == ["左", "右"]
        assert source == "table_ocr_pred"

    def test_格内多行文本按_y_再_x_拼接(self) -> None:
        cells = table_geometry.build_cell_boxes(
            [[0, 0, 100, 100]], crop=(0.0, 0.0, 1.0, 1.0), crop_size=(200, 200)
        )

        filled, _source = table_geometry.assign_cell_texts(
            cells,
            lines=[("第二行", [0, 60, 100, 90]), ("第一行", [0, 10, 100, 40])],
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=(200, 200),
        )

        assert [cell.text for cell in filled] == ["第一行第二行"]


# ── 降级 ───────────────────────────────────────────────────────


class TestDegradation:
    @pytest.mark.parametrize(
        ("boxes", "crop", "crop_size"),
        [
            pytest.param([], (0.0, 0.0, 1.0, 1.0), (100, 100), id="没有框"),
            pytest.param([[0, 0, 0, 0]], (0.0, 0.0, 1.0, 1.0), (100, 100), id="全退化"),
            pytest.param([None, "x", [1, 2, 3]], (0.0, 0.0, 1.0, 1.0), (100, 100), id="全是垃圾"),
            pytest.param([[0, 0, 10, 10]], (0.0, 0.0, 1.0, 1.0), (0, 0), id="裁图尺寸为 0"),
            pytest.param([[0, 0, 10, 10]], (0.0, 0.0, 1.0), (100, 100), id="裁框坏"),
        ],
    )
    def test_量不到几何时返回空_不抛(self, boxes: Any, crop: Any, crop_size: Any) -> None:
        assert table_geometry.build_cell_boxes(boxes, crop=crop, crop_size=crop_size) == ()
        assert table_geometry.grid_shape(()) == (0, 0)

    def test_单框时是_1x1_交给调用方决定不拆(self) -> None:
        cells = table_geometry.build_cell_boxes(
            [[0, 0, 100, 100]], crop=(0.0, 0.0, 1.0, 1.0), crop_size=(100, 100)
        )

        # 单格表不是「点得中的格子」，是否整表框由 markdown_builder 的 row_count<2 判据决定
        assert len(cells) == 1
        assert table_geometry.grid_shape(cells) == (1, 1)


# ── 引擎接线（注入 fake 引擎，不连网） ─────────────────────────


class _FakeEngine:
    """``measure(image_bytes) -> list[dict] | None`` 协议的最小实现（DESIGN §3「可测性」）。"""

    def __init__(self, tables: list[dict[str, Any]] | None) -> None:
        self._tables = tables
        self.calls = 0

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]] | None:
        self.calls += 1
        return self._tables


class _ExplodingEngine:
    """引擎抛异常（超时/5xx/凭证）时的降级路径。"""

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]] | None:
        raise RuntimeError("engine down")


class TestMeasureTableCrop:
    def test_引擎原始表格变成_PageTableGeometry(self) -> None:
        table = _p10_table()
        engine = _FakeEngine([{"cell_box_list": table["cell_box_list"], "pred_html": table["pred_html"]}])

        geometry = table_geometry.measure_table_crop(
            b"fake-crop-bytes", page_no=10, crop=P10_CROP, crop_size=P10_CROP_SIZE, engine=engine
        )

        assert geometry is not None
        assert geometry.page_no == 10
        assert geometry.engine == "pp_structure_v3"
        assert (geometry.rows, geometry.cols) == (P10_ROWS, P10_COLS)
        assert len(geometry.cells) == P10_CELLS
        assert geometry.crop == pytest.approx(P10_CROP)
        assert geometry.diagnostics["cell_count"] == P10_CELLS
        assert geometry.diagnostics["crop_size"] == list(P10_CROP_SIZE)
        assert engine.calls == 1

    def test_引擎返回_None_或空表时不给几何(self) -> None:
        for payload in (None, []):
            geometry = table_geometry.measure_table_crop(
                b"fake-crop-bytes",
                page_no=10,
                crop=P10_CROP,
                crop_size=P10_CROP_SIZE,
                engine=_FakeEngine(payload),
            )
            assert geometry is None

    def test_框数少于_td_数时仍然可用(self) -> None:
        """数量闸门已放宽（2026-11-21 真实 job 实测）。

        真表会被 ``<td>`` 数与框数不等坑掉两次：退化框被过滤（39 vs 47）、
        PP 输出 rowspan/colspan（框数 ≠ 格位数）。顺序已经没有消费方
        （行列靠几何聚类、文本按几何归属），所以只保留「框数不得多于渲染格数」这条上界；
        真正的把关交给几何层（列数必须等于 MinerU 网格 / 无重复格位 / 不出表块 bbox）。
        """
        table = _p10_table()
        fewer = [{"cell_box_list": table["cell_box_list"][:30], "pred_html": table["pred_html"]}]

        geometry = table_geometry.measure_table_crop(
            b"fake-crop-bytes", page_no=10, crop=P10_CROP, crop_size=P10_CROP_SIZE, engine=_FakeEngine(fewer)
        )

        assert geometry is not None, "少几个框不该整表作废（少画几格而已）"
        assert geometry.diagnostics["html_cell_count"] == P10_CELLS

    def test_框数多于_td_数时判结果自相矛盾(self) -> None:
        """框比渲染格还多 → 这张表的结果不可信（重复框/串表），整表框。"""
        table = _p10_table()
        boxes = list(table["cell_box_list"]) + [table["cell_box_list"][0]]
        mismatched = [{"cell_box_list": boxes, "pred_html": table["pred_html"]}]

        geometry = table_geometry.measure_table_crop(
            b"fake-crop-bytes", page_no=10, crop=P10_CROP, crop_size=P10_CROP_SIZE, engine=_FakeEngine(mismatched)
        )

        assert geometry is None

    def test_pred_html_缺失时不给几何(self) -> None:
        """顺序无从核对 → 不量（调用方退回整表框），不拿「框数」自己证明自己。"""
        table = _p10_table()
        engine = _FakeEngine([{"cell_box_list": table["cell_box_list"]}])

        geometry = table_geometry.measure_table_crop(
            b"fake-crop-bytes", page_no=10, crop=P10_CROP, crop_size=P10_CROP_SIZE, engine=engine
        )

        assert geometry is None

    def test_引擎抛异常时降级为_None(self) -> None:
        geometry = table_geometry.measure_table_crop(
            b"fake-crop-bytes",
            page_no=10,
            crop=P10_CROP,
            crop_size=P10_CROP_SIZE,
            engine=_ExplodingEngine(),
        )

        assert geometry is None

    def test_裁图参数坏时连引擎都不调(self) -> None:
        engine = _FakeEngine([{"cell_box_list": [[0, 0, 10, 10]], "pred_html": "<td>"}])

        geometry = table_geometry.measure_table_crop(
            b"fake-crop-bytes", page_no=10, crop=P10_CROP, crop_size=(0, 0), engine=engine
        )

        assert geometry is None
        assert engine.calls == 0
