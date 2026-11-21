"""表格几何 **pass 层**：选页 / 子 PDF 批量 / 单页兜底 / 表级配对 / 结构硬闸 / 产物。

## 这个文件在守什么

PR-1 只做了纯函数（像素→页面、网格聚类、解析层），没有“谁去量”。PR-2 加的是这条链：

    候选表页（高≥0.18 且 tr≥2，按面积降序、上限 24）
      → 子 PDF 一次送（批量主路径，JSONL 一行一页）
      → 逐页：cell_box_list → 格子 → 文本按几何归属 → 与本页 MinerU 块 IoU 配对
      → 结构硬闸 → 产物 analysis/table_geometry.json + summary.table_geometry

三类错误在这里被钉住（都是“看起来成功、其实指错地方”的那一类）：

1. **顺序**：``cell_box_list`` 不是 row-major（批量样本 p71/p72/p54/p20 实测），
   所以文本只能按「文本框中心落在哪个格」归属，不能按下标 zip；
2. **配对**：``table_res_list`` 没有表级 bbox（SF-20），同页多表（p16/p20 各 2 张）
   必须靠派生 bbox 做 IoU 一对一，配不上就整表框并留 reason；
3. **对齐**：批量响应的行序 = 送检页序，行数对不上就**整批作废**回退单页裁图，
   绝不按序硬凑（错一页就是把 A 页的格子画到 B 页上）。

p10 的真实数字（裁图 1555×1660、33 cell、6×6、页图实测列边界）来自
``facts/raw/p10_raw.json`` 与 ``tests/ci/fixtures/pdf_splitting/pp_structure_p10_table.json``；
批量样本的整页栅格取实测的 1191×1683（``facts/BATCH.md`` §1）。

## 跑法（红线：只能连测试库）

纯逻辑测试不需要 ``django_db``；但 conftest 会校验库名，必须显式给测试库：

```bash
cd backend
DB_NAME=test_fachuan_dev .venv/bin/python -m pytest tests/ci/unit/pdf_splitting/test_table_geometry_pass.py -q
```
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import table_geometry
from apps.pdf_splitting.services.split.split_models import PageDescriptor

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "pdf_splitting" / "pp_structure_p10_table.json"
)

# ── p10 真实数据（逐值可在 facts/raw/p10_raw.json 复核）──
P10_CROP = (0.04956, 0.18898, 0.98995, 0.89881)
P10_CROP_SIZE = (1555, 1660)
P10_MEASURED_COL_EDGES = (0.0645, 0.1323, 0.1806, 0.4613, 0.8492, 0.8927, 0.9645)
P10_ROWS = 6
P10_COLS = 6
P10_CELLS = 33
#: 批量送整页时服务端栅格（A4 @≈144dpi，实测 6/22 页样本全部 1191×1683）。
BATCH_RASTER = (1191, 1683)
TOL = 0.004

#: p10 的 table 块（MinerU 千分比，``facts/FACTS.md`` §3.1）。
P10_BLOCK_BBOX = [60, 198, 966, 890]


def _p10_pruned() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return payload["result"]["layoutParsingResults"][0]["prunedResult"]


def _p10_html() -> str:
    table = _p10_pruned()["table_res_list"][0]
    return str(table["pred_html"])


def _to_batch_boxes(cell_boxes: list[list[float]]) -> list[list[float]]:
    """p10 的**裁图**像素框 → 整页栅格像素框（模拟「送整页」拿回来的形状）。

    用户手上有的是裁图那次调用的坐标（= fixture），批量路径拿回来的是整页坐标，
    两者必须能互推：先按真实裁框换成页面归一化，再乘批量栅格。这不是造数据——
    它保证「同一张表在两条路径上的格子落在同一处」，而那正是这里要断言的。
    """
    boxes: list[list[float]] = []
    for box in cell_boxes:
        rect = table_geometry.map_pixel_rect(box, crop=P10_CROP, crop_size=P10_CROP_SIZE)
        assert rect is not None
        boxes.append(
            [
                rect["x"] * BATCH_RASTER[0],
                rect["y"] * BATCH_RASTER[1],
                (rect["x"] + rect["w"]) * BATCH_RASTER[0],
                (rect["y"] + rect["h"]) * BATCH_RASTER[1],
            ]
        )
    return boxes


def _page(page_no: int, blocks: list[dict[str, Any]], *, width: int = 1000, height: int = 1000) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text="",
        normalized_text="",
        head_text="",
        source_method="mineru_ocr",
        ocr_failed=False,
        top_candidates=[],
        layout={"width": width, "height": height, "blocks": blocks},
    )


def _table_block(bbox: list[int], html: str, *, text: str = "表格文字") -> dict[str, Any]:
    return {"type": "table", "text": text, "bbox": bbox, "table_body": html}


def _html(rows: int, cols: int, *, label: str = "R") -> str:
    body = "".join("<tr>" + "".join(f"<td>{label}{r}C{c}</td>" for c in range(cols)) + "</tr>" for r in range(rows))
    return f"<table>{body}</table>"


def _grid_boxes(
    bounds: tuple[float, float, float, float], rows: int, cols: int, *, raster: tuple[int, int] = BATCH_RASTER
) -> list[list[float]]:
    """页面归一化矩形内的一张 ``rows×cols`` 表 → 整页栅格像素框（行优先）。"""
    left, top, right, bottom = bounds
    boxes: list[list[float]] = []
    for row in range(rows):
        for col in range(cols):
            x0 = (left + (right - left) * col / cols) * raster[0]
            x1 = (left + (right - left) * (col + 1) / cols) * raster[0]
            y0 = (top + (bottom - top) * row / rows) * raster[1]
            y1 = (top + (bottom - top) * (row + 1) / rows) * raster[1]
            boxes.append([x0, y0, x1, y1])
    return boxes


def _payload(
    cell_boxes: list[list[float]],
    *,
    html: str,
    raster: tuple[int, int] = BATCH_RASTER,
    lines: list[tuple[str, list[float]]] | None = None,
) -> dict[str, Any]:
    """引擎返回的一张表（批量路径的形状）。"""
    pairs = lines or []
    return {
        "cell_box_list": cell_boxes,
        "pred_html": html,
        "image_size": list(raster),
        "table_ocr_pred": {
            "rec_texts": [text for text, _box in pairs],
            "rec_boxes": [box for _text, box in pairs],
        },
    }


def _pdf(tmp_path: Path, page_count: int, *, rotation: int = 0) -> Path:
    """合成 PDF（空白页就够：pass 层只用它抽页/渲染/读旋转）。"""
    document = fitz.open()
    try:
        for _index in range(page_count):
            page = document.new_page(width=595, height=841)
            if rotation:
                page.set_rotation(rotation)
        path = tmp_path / "source.pdf"
        document.save(path)
    finally:
        document.close()
    return path


class _BatchEngine:
    """``measure_pdf`` 返回固定逐页载荷；``measure`` 记录单页兜底调用次数。"""

    def __init__(self, pages: list[list[dict[str, Any]]] | None, *, crop_tables: Any = None) -> None:
        self._pages = pages
        self._crop_tables = crop_tables
        self.pdf_calls = 0
        self.crop_calls = 0

    def measure_pdf(self, pdf_bytes: bytes, *, page_count: int) -> list[list[dict[str, Any]]] | None:
        self.pdf_calls += 1
        return self._pages

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]] | None:
        self.crop_calls += 1
        return self._crop_tables


class _ExplodingBatchEngine:
    """批量调用直接炸（超时/5xx/凭证）→ 应回退单页裁图。"""

    def __init__(self) -> None:
        self.crop_calls = 0

    def measure_pdf(self, pdf_bytes: bytes, *, page_count: int) -> list[list[dict[str, Any]]] | None:
        raise RuntimeError("engine down")

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]] | None:
        self.crop_calls += 1
        return None


def _build(
    pages: list[PageDescriptor], *, pdf_path: Path, engine: Any, bbox_backend: str = "mineru", **kwargs: Any
) -> dict[str, Any]:
    return table_geometry.build_geometry_artifact(
        pages, pdf_path=pdf_path, engine=engine, bbox_backend=bbox_backend, **kwargs
    )


# ── 批量路径：整页栅格 + 逐页对齐 ────────────────────────────────


class TestBatchPath:
    def test_整页送检时格子落在实测列边界上(self, tmp_path: Path) -> None:
        """① 的底层依据：批量路径 ``crop=(0,0,1,1)``、``crop_size`` 取该页栅格。

        断言的是「与页图实测列边界差 ≤ 0.004 页宽」（p10 实测偏差 0.00295 页宽）。
        现行均分在同一基准上差 0.185 页宽 —— 差两个数量级。
        """
        table = _p10_pruned()["table_res_list"][0]
        payload = _payload(_to_batch_boxes(table["cell_box_list"]), html=_p10_html())
        pages = [_page(10, [_table_block(P10_BLOCK_BBOX, _p10_html())])]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        entry = artifact["pages"]["10"]["tables"]["0"]
        assert (entry["rows"], entry["cols"]) == (P10_ROWS, P10_COLS)
        assert len(entry["cells"]) == P10_CELLS
        assert entry["crop"] == [0.0, 0.0, 1.0, 1.0]
        assert entry["diagnostics"]["crop_size"] == list(BATCH_RASTER)
        edges = sorted({round(cell["rect"]["x"], 4) for cell in entry["cells"]})
        edges += [round(max(cell["rect"]["x"] + cell["rect"]["w"] for cell in entry["cells"]), 4)]
        # 一个格子的左边界不足以覆盖全部 7 条线，用「每条实测线都能在格子边界里找到」反查
        for measured in P10_MEASURED_COL_EDGES:
            closest = min(edges, key=lambda value: abs(value - measured))
            assert abs(closest - measured) <= TOL, f"列边界 {measured} 附近没有格子边界（最近 {closest}）"

    def test_一行一页_逐页对齐到各自页码(self, tmp_path: Path) -> None:
        """送检页序 [10, 20] → 第 1 行属于 p10、第 2 行属于 p20（不串页）。"""
        html10 = _html(2, 2, label="A")
        html20 = _html(2, 2, label="B")
        pages = [
            _page(10, [_table_block([100, 200, 900, 800], html10)], width=1000, height=1000),
            _page(20, [_table_block([100, 200, 900, 800], html20)], width=1000, height=1000),
        ]
        payload10 = _payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html10)
        payload20 = _payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html20)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 2), engine=_BatchEngine([[payload10], [payload20]]))

        assert artifact["summary"]["mode"] == "batch"
        assert artifact["pages"]["10"]["tables"]["0"]["rows"] == 2
        assert artifact["pages"]["20"]["tables"]["0"]["rows"] == 2
        assert artifact["summary"]["pages_measured"] == 2

    def test_行数与送检页数不等时整批作废(self, tmp_path: Path) -> None:
        """对齐不成立就整批不用（回退单页裁图），绝不按序硬凑。"""
        html = _html(2, 2)
        pages = [
            _page(10, [_table_block([100, 200, 900, 800], html)]),
            _page(20, [_table_block([100, 200, 900, 800], html)]),
        ]
        engine = _BatchEngine([[{"cell_box_list": [], "pred_html": html, "image_size": [100, 100]}]])

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 2), engine=engine)

        assert artifact["summary"]["mode"] == "per_page", "行数 ≠ 页数 → 回退单页裁图"
        assert engine.pdf_calls == 1

    def test_超过_max_pages_的页记_budget_exhausted(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [_page(no, [_table_block([100, 200, 900, 800], html)]) for no in (10, 20, 30)]
        engine = _BatchEngine([[_payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html)]] * 2)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 3), engine=engine, max_pages=2)

        assert artifact["summary"]["budget_exhausted"] is True
        assert artifact["pages"]["30"]["skipped"] == {"0": table_geometry.REASON_BUDGET_EXHAUSTED}
        assert artifact["summary"]["reason_counts"]["budget_exhausted"] == 1
        assert artifact["summary"]["pages_skipped"] == 1

    def test_旋转页不量且记_rotation(self, tmp_path: Path) -> None:
        """``/Rotate != 0``：本仓无法闭合验证旋转坐标，按纪律整表框（DESIGN §2-4）。"""
        html = _html(2, 2)
        pages = [_page(1, [_table_block([100, 200, 900, 800], html)])]
        engine = _BatchEngine([[_payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html)]])

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1, rotation=90), engine=engine)

        assert artifact["pages"]["1"]["skipped"] == {"0": table_geometry.REASON_ROTATION}
        assert artifact["pages"]["1"]["tables"] == {}
        assert engine.pdf_calls == 0, "旋转页不送检"


# ── 兜底：批量失败 → 前 6 页单页裁图 ────────────────────────────


class TestFallback:
    def test_批量异常时只回退前6页_其余记_batch_failed(self, tmp_path: Path) -> None:
        """22 页全跑单页要 158–715s（SF-16）→ 只救前 6 页，其余整表框并留 reason。"""
        # 8 行 × 5 列：单格占页 0.48/40 = 1.2% < 4%，不会被判成伪表
        html = _html(8, 5)
        pages = [
            _page(no, [_table_block([100, 200, 900, 800], html)])
            for no in (1, 2, 3, 4, 5, 6, 7, 8)
        ]
        engine = _ExplodingBatchEngine()

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 8), engine=engine)

        assert artifact["summary"]["mode"] == "per_page"
        assert engine.crop_calls == 6, "只回退前 6 页（第 7、8 页不再逐页付费）"
        assert artifact["summary"]["reason_counts"].get(table_geometry.REASON_BATCH_FAILED) == 2
        assert artifact["pages"]["7"]["skipped"] == {"0": table_geometry.REASON_BATCH_FAILED}
        assert artifact["pages"]["8"]["skipped"] == {"0": table_geometry.REASON_BATCH_FAILED}
        # 前 6 页确实被量过（引擎没出表 → 真表漏检），不是「静默跳过」
        assert artifact["pages"]["1"]["skipped"] == {"0": table_geometry.REASON_NO_TABLE_DETECTED}

    def test_预算耗尽后不再发单页请求(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [_page(no, [_table_block([100, 200, 900, 800], html)]) for no in (1, 2, 3)]
        engine = _ExplodingBatchEngine()

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 3), engine=engine, budget_seconds=-1)

        assert engine.crop_calls == 0, "预算已耗尽 → 一个单页请求也不该发"
        assert artifact["summary"]["budget_exhausted"] is True
        assert artifact["summary"]["reason_counts"].get(table_geometry.REASON_BUDGET_EXHAUSTED) == 3


# ── 表级配对（同页多表）────────────────────────────────────────


class TestPairing:
    def test_一块一表时配上且_iou_高(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        payload = _payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        match = artifact["pages"]["10"]["tables"]["0"]["match"]
        assert match["reason"] == table_geometry.REASON_MATCHED
        assert match["iou"] > 0.9
        assert match["block_index"] == 0

    def test_同页两表各自配上自己的块(self, tmp_path: Path) -> None:
        """p16/p20 的形状：同页两块、PP 也回两张表，必须各配各的（互 IoU = 0）。"""
        upper_html, lower_html = _html(3, 2, label="上"), _html(2, 2, label="下")
        pages = [
            _page(
                16,
                [
                    _table_block([100, 100, 900, 450], upper_html),
                    _table_block([100, 600, 900, 850], lower_html),
                ],
            )
        ]
        payloads = [
            _payload(_grid_boxes((0.1, 0.1, 0.9, 0.45), 3, 2), html=upper_html),
            _payload(_grid_boxes((0.1, 0.6, 0.9, 0.85), 2, 2), html=lower_html),
        ]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([payloads]))

        tables = artifact["pages"]["16"]["tables"]
        assert set(tables) == {"0", "1"}
        assert tables["0"]["rows"] == 3 and tables["1"]["rows"] == 2, "上表不能画成下表"
        assert tables["0"]["match"]["table_index"] == 0
        assert tables["1"]["match"]["table_index"] == 1
        assert artifact["summary"]["reason_counts"] == {}

    def test_配不上的块记_unmatched_pp_table(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [
            _page(
                16,
                [
                    _table_block([100, 100, 900, 450], html),
                    _table_block([100, 600, 900, 850], html),
                ],
            )
        ]
        payload = _payload(_grid_boxes((0.1, 0.1, 0.9, 0.45), 2, 2), html=html)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        assert artifact["pages"]["16"]["skipped"] == {"1": table_geometry.REASON_UNMATCHED_PP_TABLE}
        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_UNMATCHED_PP_TABLE: 1}

    def test_裁图外的_pp_表计入_orphan(self, tmp_path: Path) -> None:
        """多出来的一张 PP 表（误检/裁图外）不造成错框，但必须计数。"""
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        payloads = [
            _payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html),
            _payload(_grid_boxes((0.0, 0.0, 0.05, 0.05), 2, 2), html=html),
        ]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([payloads]))

        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_ORPHAN_PP_TABLE: 1}
        assert "0" in artifact["pages"]["10"]["tables"]

    def test_一张表同时命中两个块时两块都整表框(self) -> None:
        """PP 把上下两张表合成一张：不能拿它给任何一块定位（merged）。"""
        matches = table_geometry.match_tables_to_blocks(
            [{"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.4}, {"x": 0.1, "y": 0.5, "w": 0.8, "h": 0.4}],
            [{"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}],
        )

        assert {match.reason for match in matches.by_block.values()} == {table_geometry.REASON_MERGED_PP_TABLE}
        assert matches.orphan_tables == (0,)

    def test_一个块命中两张表时该块整表框(self) -> None:
        """PP 把一张表切碎：两块都只有半张表，谁也不能单独定位（split）。"""
        matches = table_geometry.match_tables_to_blocks(
            [{"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}],
            [{"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.4}, {"x": 0.1, "y": 0.5, "w": 0.8, "h": 0.4}],
        )

        assert matches.by_block[0].reason == table_geometry.REASON_SPLIT_PP_TABLE
        assert matches.by_block[0].table_index is None


# ── 结构硬闸（几何不可信 → 整表框）──────────────────────────────


class TestStructuralGate:
    def test_重复格位时整表框(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        # 左上格重复一次（同一框给两遍），另两格补成 2 列 / 2 行 →
        # 列数对得上、IoU 也对得上，唯独格位重复：这正是“行列推断失败”的硬信号
        left, top, right, bottom = 0.1 * BATCH_RASTER[0], 0.2 * BATCH_RASTER[1], 0.9 * BATCH_RASTER[0], 0.8 * BATCH_RASTER[1]
        mid_x, mid_y = (left + right) / 2, (top + bottom) / 2
        boxes = [
            [left, top, mid_x, mid_y],
            [left, top, mid_x, mid_y],
            [mid_x, top, right, mid_y],
            [left, mid_y, right, bottom],
        ]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(boxes, html=html)]]))

        assert artifact["pages"]["10"]["skipped"] == {"0": table_geometry.REASON_GEOMETRY_INCONSISTENT}
        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_GEOMETRY_INCONSISTENT: 1}

    def test_格子超出表块_bbox_时记_pp_box_outside_block(self, tmp_path: Path) -> None:
        """越界 1.5% 以上：**PP 的框铺到了块外**（责任方是引擎，不是聚类）。

        真实样本 p11/p27/p35 就是这个形态：PP 的格框虚高到页面下半部（连签名栏一起框），
        而 MinerU 的 bbox 是对的。与 ``geometry_inconsistent``（格位重叠，我们的问题）
        分开记，下一份卷宗出问题时才能一眼看出该查引擎还是查聚类。
        """
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        # 下边缘多出 3% 页高（> 1.5% 容差），横向不变 → IoU 仍 > 0.9，只有越界这一条拦得住
        boxes = _grid_boxes((0.1, 0.2, 0.9, 0.83), 2, 2)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(boxes, html=html)]]))

        assert artifact["pages"]["10"]["skipped"] == {"0": table_geometry.REASON_PP_BOX_OUTSIDE_BLOCK}
        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_PP_BOX_OUTSIDE_BLOCK: 1}

    def test_容差以内的抖动不算越界(self, tmp_path: Path) -> None:
        """实测像素→页面误差 0.0007–0.003 页宽（SF-6/SF-8），1.5% 容差不能误杀它。"""
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        boxes = _grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2)
        # 右边界多出 0.005 页宽（≈ 换算误差量级）
        nudged = [[box[0], box[1], box[2] + 0.005 * BATCH_RASTER[0], box[3]] for box in boxes]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(nudged, html=html)]]))

        assert "0" in artifact["pages"]["10"]["tables"]

    def test_列数与_HTML_不一致时整表框(self, tmp_path: Path) -> None:
        """行数可由跨页解释，列数不能 → 整表框并记 ``pp_shape_mismatch``（两侧对不上）。"""
        html = _html(2, 3)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        boxes = _grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(boxes, html=html)]]))

        assert artifact["pages"]["10"]["skipped"] == {"0": table_geometry.REASON_PP_SHAPE_MISMATCH}


# ── 引擎不出表：真表漏检 vs 伪表 ────────────────────────────────


class TestNoTable:
    def test_真表漏检记_no_table_detected(self, tmp_path: Path) -> None:
        """p52：真表但 PP 不出表（``table_res_list=[]``）→ 覆盖率缺口，不是伪表。"""
        html = _html(40, 5)
        pages = [_page(52, [_table_block([35, 109, 982, 738], html)])]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[]]))

        assert artifact["pages"]["52"]["skipped"] == {"0": table_geometry.REASON_NO_TABLE_DETECTED}
        assert artifact["summary"]["pages_failed"] == 1
        assert artifact["summary"]["pages_measured"] == 0

    def test_伪表记_pseudo_table(self, tmp_path: Path) -> None:
        """p29：整页被当成 3×3 表格（单格占页 10.9% > 4%）→ 本来就不该画格。"""
        html = _html(3, 3)
        pages = [_page(29, [_table_block([19, 9, 960, 818], html)])]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[]]))

        assert artifact["pages"]["29"]["skipped"] == {"0": table_geometry.REASON_PSEUDO_TABLE}
        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_PSEUDO_TABLE: 1}

    def test_引擎没给栅格尺寸时记_engine_error(self, tmp_path: Path) -> None:
        """没有该页栅格尺寸就无法把裁图像素换成页面坐标 —— 宁可整表框也不猜。"""
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]
        payload = {"cell_box_list": [[0, 0, 10, 10]], "pred_html": html, "image_size": None}

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        assert artifact["pages"]["10"]["skipped"] == {"0": table_geometry.REASON_ENGINE_ERROR}


# ── 文本按几何归属（PR-2 的核心修正）───────────────────────────


class TestTextAttribution:
    def test_乱序_cells_与乱序文本_各自贴回自己的格子(self, tmp_path: Path) -> None:
        """``cell_box_list`` 不是 row-major（批量样本实测），文本只能按几何归属。

        这里把**格子顺序打乱、文本顺序也打乱**：任何“按下标 zip”的实现都会贴错，
        而按「文本框中心落在哪个格」归属则与两边的顺序都无关。
        """
        html = _html(2, 2)
        boxes = _grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2)  # 行优先：00, 01, 10, 11
        shuffled = [boxes[3], boxes[0], boxes[2], boxes[1]]
        # 文本按格子几何中心造框，但**顺序再打乱一次**，且与 boxes 的顺序完全不同
        centres = {
            "甲": boxes[0],
            "乙": boxes[1],
            "丙": boxes[2],
            "丁": boxes[3],
        }
        lines = [
            (text, [box[0], box[1], box[2], box[3]])
            for text, box in (("丁", centres["丁"]), ("乙", centres["乙"]), ("甲", centres["甲"]), ("丙", centres["丙"]))
        ]
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]

        artifact = _build(
            pages,
            pdf_path=_pdf(tmp_path, 1),
            engine=_BatchEngine([[_payload(shuffled, html=html, lines=lines)]]),
        )

        cells = artifact["pages"]["10"]["tables"]["0"]["cells"]
        by_position = {(cell["row"], cell["col"]): cell["text"] for cell in cells}
        assert by_position == {(0, 0): "甲", (0, 1): "乙", (1, 0): "丙", (1, 1): "丁"}
        assert artifact["pages"]["10"]["tables"]["0"]["diagnostics"]["text_source"] == "table_ocr_pred"

    def test_缺_rec_boxes_时文本留空且_text_source_none(self, tmp_path: Path) -> None:
        """只有 ``rec_texts`` 没有框 → 无法归属 → **绝不**回退到按下标 zip。"""
        pruned = _p10_pruned()
        table = pruned["table_res_list"][0]
        payload = {
            "cell_box_list": _to_batch_boxes(table["cell_box_list"]),
            "pred_html": _p10_html(),
            "image_size": list(BATCH_RASTER),
            "table_ocr_pred": {"rec_texts": table["table_ocr_pred"]["rec_texts"]},  # 无 rec_boxes
        }
        pages = [_page(10, [_table_block(P10_BLOCK_BBOX, _p10_html())])]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        entry = artifact["pages"]["10"]["tables"]["0"]
        assert entry["diagnostics"]["text_source"] == "none"
        assert all(cell["text"] == "" for cell in entry["cells"])

    def test_两侧数量不等的行级文本整批不用(self, tmp_path: Path) -> None:
        """``rec_texts`` 与 ``rec_boxes`` 不是同一批 → 一个也不敢贴（按序配对必错位）。"""
        html = _html(2, 2)
        boxes = _grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2)
        payload = _payload(boxes, html=html, lines=[("甲", boxes[0]), ("乙", boxes[1])])
        payload["table_ocr_pred"]["rec_boxes"] = payload["table_ocr_pred"]["rec_boxes"][:1]  # 少一个框
        pages = [_page(1, [_table_block([100, 200, 900, 800], html)])]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        entry = artifact["pages"]["1"]["tables"]["0"]
        assert entry["diagnostics"]["text_source"] == "none"
        assert all(cell["text"] == "" for cell in entry["cells"])

    def test_落不进任何格子的文本被丢弃(self) -> None:
        cells = table_geometry.build_cell_boxes(
            [[0, 0, 100, 50]], crop=(0.0, 0.0, 1.0, 1.0), crop_size=(200, 100)
        )

        filled, source = table_geometry.assign_cell_texts(
            cells,
            lines=[("表外", [190, 90, 200, 100])],
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=(200, 100),
        )

        assert [cell.text for cell in filled] == [""]
        assert source == "none"


# ── 产物与 summary ────────────────────────────────────────────


class TestArtifact:
    def test_产物结构与跨阶段解析往返(self, tmp_path: Path) -> None:
        pruned = _p10_pruned()
        table = pruned["table_res_list"][0]
        payload = _payload(_to_batch_boxes(table["cell_box_list"]), html=_p10_html())
        pages = [_page(10, [_table_block(P10_BLOCK_BBOX, _p10_html())])]

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))
        mapping = table_geometry.geometries_by_page_block(artifact)

        assert set(artifact) == {"engine", "generated_at", "summary", "pages"}
        assert artifact["engine"] == table_geometry.PP_STRUCTURE_ENGINE
        geometry = mapping[10][0]
        assert (geometry.page_no, geometry.rows, geometry.cols) == (10, P10_ROWS, P10_COLS)
        assert len(geometry.cells) == P10_CELLS
        assert geometry.crop == (0.0, 0.0, 1.0, 1.0)
        assert geometry.pp_bbox is not None and geometry.match is not None
        assert geometry.match["reason"] == table_geometry.REASON_MATCHED

    def test_每个整表框都有_reason_且进产物与_summary(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [
            _page(
                16,
                [
                    _table_block([100, 100, 900, 450], html),
                    _table_block([100, 600, 900, 850], html),
                ],
            )
        ]
        payload = _payload(_grid_boxes((0.1, 0.1, 0.9, 0.45), 2, 2), html=html)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        skipped = artifact["pages"]["16"]["skipped"]
        assert skipped and all(reason for reason in skipped.values()), "整表框必须带原因"
        counts = artifact["summary"]["reason_counts"]
        assert sum(counts.values()) == len(skipped)

    def test_summary_区块形状固定(self) -> None:
        """开关关着 / 产物缺失时也给出同一组键的零值（前端不用为三种情况写分支）。"""
        block = table_geometry.summary_block({}, enabled=False)

        assert set(block) == set(table_geometry.SUMMARY_KEYS)
        assert block["enabled"] is False
        assert block["mode"] == "none"
        assert block["reason_counts"] == {}
        assert block["pages_measured"] == 0

    def test_没有坐标系时不产出几何(self, tmp_path: Path) -> None:
        """``bbox_backend`` 是本地 OCR/auto → 块 bbox 不可比 → 不猜（reason=no_coordinates）。"""
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 800], html)])]

        artifact = _build(
            pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[]]), bbox_backend="auto"
        )

        assert artifact["pages"] == {}
        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_NO_COORDINATES: 1}
        assert artifact["summary"]["mode"] == "none"

    def test_坏产物逐条跳过不抛(self) -> None:
        assert table_geometry.geometries_by_page_block(None) == {}
        assert table_geometry.geometries_by_page_block({"pages": "x"}) == {}
        assert table_geometry.geometries_by_page_block({"pages": {"10": {"tables": {"0": {"rows": None}}}}}) == {}


# ── 开关 ──────────────────────────────────────────────────────


class TestSwitches:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("1", True, id="1"),
            pytest.param("true", True, id="true"),
            pytest.param("ON", True, id="ON"),
            pytest.param("0", False, id="0"),
            pytest.param("off", False, id="off"),
        ],
    )
    def test_开关值解析(self, monkeypatch: Any, raw: str, expected: bool) -> None:
        monkeypatch.setattr(table_geometry, "_system_value", lambda key, default: raw)

        assert table_geometry.geometry_enabled() is expected

    def test_缺省时开启几何且不回落均分(self, monkeypatch: Any) -> None:
        """默认值：``PDF_SPLIT_TABLE_GEOMETRY_ENABLED=1``、``..._UNIFORM_FALLBACK=0``。"""
        seen: dict[str, str] = {}

        def fake(key: str, default: str) -> str:
            seen[key] = default
            return ""

        monkeypatch.setattr(table_geometry, "_system_value", fake)

        assert table_geometry.switches() == (True, False)
        assert seen == {
            table_geometry.TABLE_GEOMETRY_ENABLED_KEY: "1",
            table_geometry.TABLE_UNIFORM_FALLBACK_KEY: "0",
        }

    def test_开关读不到时回落默认值不抛(self) -> None:
        """配置读不出来（DB 不可用）不能让分段挂掉——但要走默认路径并留痕。"""
        assert table_geometry._as_flag("", default=True) is True
        assert table_geometry._as_flag("???", default=False) is False


# ── 真实批量样本上的三处整改（2026-11-21 端到端诊断）────────────────


class TestPairingIndexSpace:
    """候选列表位置 ≠ 版面块下标：混用会让“配上了也查不到”。

    真实事故：p10 的表格是版面第 3 块（下标 2），在候选列表里却是第 1 个；
    配对结果按位置 0 存、按版面下标 2 查 → 全落空，summary 里 13 个块被记成
    ``unmatched_pp_table``，p10 从此没有几何。这条用“表块前面还有两个非表块”
    的形状把它钉住。
    """

    def test_表块不是第一个版面块时仍然配上(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [
            _page(
                10,
                [
                    {"type": "text", "text": "正文一", "bbox": [100, 100, 900, 150]},
                    {"type": "text", "text": "正文二", "bbox": [100, 160, 900, 190]},
                    _table_block([100, 200, 900, 800], html),
                ],
            )
        ]
        payload = _payload(_grid_boxes((0.1, 0.2, 0.9, 0.8), 2, 2), html=html)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))

        tables = artifact["pages"]["10"]["tables"]
        assert list(tables) == ["2"], "配上的表要挂在**版面块下标**（2）上"
        assert tables["2"]["match"]["reason"] == table_geometry.REASON_MATCHED
        assert artifact["summary"]["pages_measured"] == 1
        mapping = table_geometry.geometries_by_page_block(artifact)
        assert set(mapping[10]) == {2}


class TestDenseGrid:
    """高密度长表：固定 1% 容差会把相邻行边界并成一条 → 大片重复格位。

    真实样本 p71/p72（50 行×8/10 列、行高 26px < 裁图高 1% = 16.8px）实测冒出
    48 / 73 个重复格位，整表被退回。改成「按引擎 HTML 的列数聚到 K 簇 + 行首合并
    上限 + 重复格位丢弃」后应当量得出来。
    """

    @staticmethod
    def _dense(rows: int, cols: int) -> tuple[list[list[float]], str]:
        # 行高 15.5px（1683 的 0.92% < 1% 容差），正是会被并成一条的那个量级
        top, bottom = 0.1 * BATCH_RASTER[1], 0.1 * BATCH_RASTER[1] + rows * 15.5
        boxes = _grid_boxes((0.1, top / BATCH_RASTER[1], 0.9, bottom / BATCH_RASTER[1]), rows, cols)
        return boxes, _html(rows, cols)

    def test_行高小于固定容差时仍能推出干净网格(self, tmp_path: Path) -> None:
        boxes, html = self._dense(60, 3)
        pages = [_page(71, [_table_block([100, 168, 900, 168 + 930], html)])]
        payload = _payload(boxes, html=html)

        cells = table_geometry.build_cell_boxes(
            boxes,
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=BATCH_RASTER,
            expected_cols=table_geometry.html_grid_shape(html)[1],
            expected_rows=table_geometry.html_grid_shape(html)[0],
        )

        assert len(cells) == 60 * 3, "一格都不能丢（没有重复 → 没有丢弃）"
        assert table_geometry.grid_shape(cells) == (60, 3)
        assert len({(cell.row, cell.col) for cell in cells}) == len(cells)
        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))
        assert "0" in artifact["pages"]["71"]["tables"] or "0" in artifact["pages"]["71"]["skipped"]

    def test_同一份网格用固定容差会塌(self) -> None:
        """反证：不给形状约束时（PR-1 行为）同一份数据确实出现重复格位。"""
        boxes, _html_text = self._dense(60, 3)

        cells = table_geometry.build_cell_boxes(boxes, crop=(0.0, 0.0, 1.0, 1.0), crop_size=BATCH_RASTER)

        assert len({(cell.row, cell.col) for cell in cells}) < len(cells) or table_geometry.grid_shape(cells)[0] < 60


class TestShapeConstrainedColumns:
    def test_两行左边界差略大于容差时不再多切一列(self, tmp_path: Path) -> None:
        """p27 实测：两行左边界差 12px，恰好越过「裁图宽 1% = 11.9px」的固定容差。

        旧实现把它当成两条列边界 → 4 列变 5 列 → 列数对不上 → 整表退回。
        """
        html = _html(2, 4)
        rows_boxes = _grid_boxes((0.1, 0.2, 0.9, 0.6), 2, 4)
        shifted = [
            [box[0] + (12 if index >= 4 else 0), box[1], box[2] + (12 if index >= 4 else 0), box[3]]
            for index, box in enumerate(rows_boxes)
        ]
        pages = [_page(27, [_table_block([100, 200, 900, 600], html)])]
        payload = _payload(shifted, html=html)

        cells = table_geometry.build_cell_boxes(
            shifted,
            crop=(0.0, 0.0, 1.0, 1.0),
            crop_size=BATCH_RASTER,
            expected_cols=4,
            expected_rows=2,
        )

        assert table_geometry.grid_shape(cells) == (2, 4)
        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[payload]]))
        assert artifact["pages"]["27"]["tables"]["0"]["cols"] == 4


class TestUntrustworthyGrid:
    def test_格子错乱到无法成网格时整表框(self, tmp_path: Path) -> None:
        """框的左右边界互相穿越（PP 在密集流水表上会这样）→ 列聚类不可信 → 整表框。"""
        html = _html(2, 3)
        # 两行的列起点完全对不上（90/450/810 vs 250/700/1000）：任何“3 列”都要求
        # 把相距 300px 的框并成一列 —— 簇内抖动远大于簇间距，正是列聚类不可信的定义
        chaotic = [
            [90, 200, 250, 260],
            [450, 200, 610, 260],
            [810, 200, 970, 260],
            [250, 320, 410, 380],
            [700, 320, 860, 380],
            [1000, 320, 1160, 380],
        ]
        pages = [_page(72, [_table_block([75, 119, 975, 320], html)])]

        artifact = _build(
            pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(chaotic, html=html)]])
        )

        assert artifact["pages"]["72"]["skipped"] == {"0": table_geometry.REASON_GEOMETRY_INCONSISTENT}
        assert artifact["summary"]["pages_measured"] == 0


class TestContainmentPairing:
    """PP 把表画大了（块几乎全在 PP 表框里）：仍要配上，好把原因记成 PP 的。

    真实样本 p27：块 (0.16,0.20,0.68,0.22) 有 95% 落在 PP 表框里，但 PP 的框高度是块的
    2 倍（连签名栏一起框）→ IoU 只有 0.44。只看 IoU 会记 ``unmatched_pp_table``，
    看不出是引擎画框的问题还是我们聚类的问题。
    """

    def test_块被_PP_表框包住时仍配对并记_pp_box_outside_block(self, tmp_path: Path) -> None:
        html = _html(2, 2)
        pages = [_page(27, [_table_block([160, 200, 840, 418], html)])]
        # 表块 y 0.2–0.418，而 PP 的框一直延伸到 0.67（把签名栏也框进去）
        boxes = _grid_boxes((0.174, 0.208, 0.843, 0.67), 2, 2)

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(boxes, html=html)]]))

        entry = artifact["pages"]["27"]
        assert entry["tables"] == {}
        assert entry["skipped"] == {"0": table_geometry.REASON_PP_BOX_OUTSIDE_BLOCK}
        assert artifact["summary"]["reason_counts"] == {table_geometry.REASON_PP_BOX_OUTSIDE_BLOCK: 1}

    def test_包不住时仍记未配上(self, tmp_path: Path) -> None:
        """只有一半落在块里的 PP 表不能硬配（否则等于拿别的表定位）。"""
        html = _html(2, 2)
        pages = [_page(10, [_table_block([100, 200, 900, 400], html)])]
        boxes = _grid_boxes((0.1, 0.6, 0.9, 0.9), 2, 2)  # 完全在块下方

        artifact = _build(pages, pdf_path=_pdf(tmp_path, 1), engine=_BatchEngine([[_payload(boxes, html=html)]]))

        assert artifact["pages"]["10"]["skipped"] == {"0": table_geometry.REASON_UNMATCHED_PP_TABLE}
