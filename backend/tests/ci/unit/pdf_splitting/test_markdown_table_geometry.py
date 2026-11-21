"""``markdown_builder`` 的表格定位**三期分流**（DESIGN §6）+ 正文零影响红线。

## 三期的判据与行为

| 期 | 条件 | precision | 事实依据 |
|:--|:--|:--|:--|
| ① | 有几何且 ``rows/cols`` 与本页 HTML 网格一致 | ``grid``（``approx=False``） | p10 33 cell / 6×6 实测 |
| ② | 有几何、列数一致、行数不同（MinerU 跨页并表） | ``grid``，只画本页可见行 | p10 HTML 7 行、本页真实 6 行（SF-12） |
| ③ | 无几何（未量/失败/列数对不上） | 整表框 ``page``；``legacy_uniform=True`` 才走旧均分 | 均分在 p10 上偏 0.185 页宽（SF-9） |

## 为什么这些断言长这样

* ①：断言「件数」列的框落在**页图实测**的 0.8492–0.8927 上。均分算出来的 0.664–0.815
  会整块落进隔壁「证明内容」列——律师点「件数」看到的是别人的内容（这是本 PR 的原始缺陷）。
* ②：断言「本页没有第 7 行的框，但第 7 行的文字仍在正文里」——跨页行物理在下一页，
  画在本页就是把框指错地方；而正文是律师要引用的原话，**一行都不能少**。
* ③：断言**格子数为 0**（不是“格子数变少”），确保没有偷偷保留均分。
* ⑧（正文零影响）：同一份 pages 在「有几何 / 无几何 / 回滚开关」三条路径下，
  ``markdown`` 必须**逐字相同**，只有 ``positioned`` 变。

p10 的 fixture 与实测数字见 ``tests/ci/fixtures/pdf_splitting/pp_structure_p10_table.json``
与 ``facts/FACTS.md``；批量路径的整页栅格取实测 1191×1683（``facts/BATCH.md`` §1）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import table_geometry, table_geometry_pass
from apps.pdf_splitting.services.split.markdown_builder import (
    build_positioned_blocks,
    build_segment_markdown,
    build_segments_markdown,
)
from apps.pdf_splitting.services.split.split_models import PageDescriptor, SegmentDraft

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "pdf_splitting" / "pp_structure_p10_table.json"
)

P10_CROP = (0.04956, 0.18898, 0.98995, 0.89881)
P10_CROP_SIZE = (1555, 1660)
P10_MEASURED_COL_EDGES = (0.0645, 0.1323, 0.1806, 0.4613, 0.8492, 0.8927, 0.9645)
P10_BLOCK_BBOX = [60, 198, 966, 890]
P10_ROWS = 6
P10_COLS = 6
P10_CELLS = 33
BATCH_RASTER = (1191, 1683)
TOL = 0.004

#: p10 的第 7 行物理在 p11（MinerU 跨页并表把它并进了 p10 的 HTML，SF-12）。
P10_CROSS_PAGE_ROW = '<tr><td>结果及送达</td><td>6</td><td>《认定工伤决定书》</td><td>送达回证。</td><td>3</td><td>81-83</td></tr>'


def _p10_table() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    table = payload["result"]["layoutParsingResults"][0]["prunedResult"]["table_res_list"][0]
    assert isinstance(table, dict)
    return table


def _p10_html(*, cross_page: bool = False) -> str:
    html = str(_p10_table()["pred_html"])
    if not cross_page:
        return html
    return html.replace("</tbody></table>", f"{P10_CROSS_PAGE_ROW}</tbody></table>")


def _batch_boxes() -> list[list[float]]:
    """p10 的裁图像素框 → 整页栅格像素框（模拟「送整页」返回的形状）。"""
    boxes: list[list[float]] = []
    for box in _p10_table()["cell_box_list"]:
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


def _page(page_no: int, blocks: list[dict[str, Any]]) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text="",
        normalized_text="",
        head_text="",
        source_method="mineru_ocr",
        ocr_failed=False,
        top_candidates=[],
        layout={"width": 1000, "height": 1000, "blocks": blocks},
    )


def _draft(page_no: int) -> SegmentDraft:
    return SegmentDraft(
        order=1,
        page_start=page_no,
        page_end=page_no,
        segment_type="evidence",
        filename="证据清单.pdf",
        confidence=1.0,
        source_method="llm",
        review_flag="normal",
    )


class _Engine:
    """批量引擎替身：一页一张表（结构与真实响应同形）。"""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads

    def measure_pdf(self, pdf_bytes: bytes, *, page_count: int) -> list[list[dict[str, Any]]]:
        return [self._payloads for _ in range(page_count)]

    def measure(self, image_bytes: bytes) -> list[dict[str, Any]]:
        return self._payloads


def _geometry_for(pages: list[PageDescriptor], payloads: list[dict[str, Any]], tmp_path: Path) -> dict[int, dict[int, Any]]:
    """跑一次真实的 pass，拿到 ``{页号: {block_index: PageTableGeometry}}``。"""
    document = fitz.open()
    try:
        for _page_no in pages:
            document.new_page(width=595, height=841)
        pdf_path = tmp_path / "source.pdf"
        document.save(pdf_path)
    finally:
        document.close()
    artifact = table_geometry_pass.build_geometry_artifact(
        pages, pdf_path=pdf_path, engine=_Engine(payloads), bbox_backend="mineru"
    )
    return table_geometry_pass.geometries_by_page_block(artifact)


def _payload(html: str, cell_boxes: list[list[float]]) -> dict[str, Any]:
    return {
        "cell_box_list": cell_boxes,
        "pred_html": html,
        "image_size": list(BATCH_RASTER),
        "table_ocr_pred": {"rec_texts": [], "rec_boxes": []},
    }


@pytest.fixture
def p10_setup(tmp_path: Path) -> tuple[list[PageDescriptor], dict[int, dict[int, Any]]]:
    """p10 的 pages + 真实几何（6 行；HTML 也是 6 行 → ① 的形态）。"""
    pages = [_page(10, [{"type": "table", "text": "材料类别", "bbox": P10_BLOCK_BBOX, "table_body": _p10_html()}])]
    geometry = _geometry_for(pages, [_payload(_p10_html(), _batch_boxes())], tmp_path)
    assert geometry, "几何 pass 没量出东西，后面的断言都会变成假绿"
    return pages, geometry


# ── ① 有几何且行列一致 ────────────────────────────────────────


class TestGridPrecision:
    def test_33_格全是_grid_且不谎报_approx(self, p10_setup: tuple[list[PageDescriptor], dict[int, Any]]) -> None:
        pages, geometry = p10_setup

        blocks = build_positioned_blocks(pages, bbox_backend="mineru", table_geometry=geometry)
        cells = [block for block in blocks if block["type"] == "table_cell"]

        assert len(cells) == P10_CELLS
        assert {cell["rect"]["precision"] for cell in cells} == {"grid"}
        assert {cell["rect"]["approx"] for cell in cells} == {False}

    def test_件数列落在页图实测列边界上(self, p10_setup: tuple[list[PageDescriptor], dict[int, Any]]) -> None:
        """原始缺陷症状：「件数」列的框整块落进「证明内容」列（偏 0.185 页宽 ≈ 110pt）。"""
        pages, geometry = p10_setup

        blocks = build_positioned_blocks(pages, bbox_backend="mineru", table_geometry=geometry)
        cells = [block for block in blocks if block["type"] == "table_cell"]
        left, right = P10_MEASURED_COL_EDGES[4], P10_MEASURED_COL_EDGES[5]
        jianshu = [block for block in cells if abs(block["rect"]["x"] - left) <= TOL]

        assert len(jianshu) == P10_ROWS, "表头 + 5 个数据行都在「件数」列"
        assert "件数" in [block["text"] for block in jianshu]
        for block in jianshu:
            assert abs(block["rect"]["x"] + block["rect"]["w"] - right) <= TOL
        # 均分算出来的「件数」列是 0.664–0.815，整块落在隔壁「证明内容」列里 —— 不许再出现
        assert [block for block in cells if 0.60 < block["rect"]["x"] < 0.83] == []

    def test_格子文字来自本页_HTML_而不是引擎行级文本(self, p10_setup: tuple[list[PageDescriptor], dict[int, Any]]) -> None:
        """定位块文字与 markdown 表格文字必须同源（这里同为 HTML 网格）。

        引擎的行级 OCR 文本（``table_ocr_pred``）只进产物供排障/交叉核对；
        若把它拿来当定位块文字，前端悬浮窗会显示与正文不一样的措辞。
        """
        pages, geometry = p10_setup
        blocks = build_positioned_blocks(pages, bbox_backend="mineru", table_geometry=geometry)
        header = [block for block in blocks if block["type"] == "table_cell" and block["rect"]["y"] < 0.26]

        assert [block["text"] for block in header[:6]] == ["材料 类别", "序号", "名称", "证明内容", "件数", "页码"]


# ── ② 跨页：行列数不一致 ──────────────────────────────────────


class TestCrossPage:
    def test_只画本页可见行_跨页行不出框(self, tmp_path: Path) -> None:
        """p10 的 HTML 有 7 行（第 7 行物理在 p11），本页真实 6 行 → 只画 6 行。"""
        pages = [
            _page(
                10,
                [
                    {
                        "type": "table",
                        "text": "材料类别",
                        "bbox": P10_BLOCK_BBOX,
                        "table_body": _p10_html(cross_page=True),
                    }
                ],
            )
        ]
        geometry = _geometry_for(pages, [_payload(_p10_html(), _batch_boxes())], tmp_path)

        blocks = build_positioned_blocks(pages, bbox_backend="mineru", table_geometry=geometry)
        cells = [block for block in blocks if block["type"] == "table_cell"]

        assert geometry[10][0].rows == P10_ROWS, "几何只含本页 6 行"
        assert len(cells) == P10_CELLS, "第 7 行（跨页行）不该在本页出框"
        assert all(block["rect"]["precision"] == "grid" for block in cells)
        # 跨页行既不能画框，也不能从正文里消失
        markdown = build_segment_markdown("证据清单", pages)
        assert "结果及送达" in markdown

    def test_诊断记_cross_page(self, tmp_path: Path) -> None:
        pages = [
            _page(
                10,
                [
                    {
                        "type": "table",
                        "text": "材料类别",
                        "bbox": P10_BLOCK_BBOX,
                        "table_body": _p10_html(cross_page=True),
                    }
                ],
            )
        ]
        document = fitz.open()
        try:
            document.new_page(width=595, height=841)
            pdf_path = tmp_path / "cross.pdf"
            document.save(pdf_path)
        finally:
            document.close()

        artifact = table_geometry_pass.build_geometry_artifact(
            pages, pdf_path=pdf_path, engine=_Engine([_payload(_p10_html(), _batch_boxes())]), bbox_backend="mineru"
        )

        diagnostics = artifact["pages"]["10"]["tables"]["0"]["diagnostics"]
        assert diagnostics["cross_page"] is True
        assert diagnostics["html_row_count"] == P10_ROWS + 1
        assert artifact["summary"]["cross_page_tables"] == 1


# ── ③ 无几何 / 列数对不上 ────────────────────────────────────


class TestWholeTableFallback:
    @staticmethod
    def _blocks() -> list[dict[str, Any]]:
        body = "".join(
            "<tr>" + "".join(f"<td>R{r}C{c}</td>" for c in range(4)) + "</tr>" for r in range(6)
        )
        return [
            {
                "type": "table",
                "text": "押品信息",
                "bbox": [100, 200, 900, 800],
                "table_body": f"<table>{body}</table>",
            }
        ]

    def test_无几何时整表框且格子数为零(self) -> None:
        """默认路径**不再均分**：格子数必须是 0（不是变少），否则就是偷偷留着推算框。"""
        blocks = build_positioned_blocks([_page(22, self._blocks())], bbox_backend="mineru")

        assert [block["type"] for block in blocks] == ["table"]
        assert blocks[0]["rect"]["precision"] == "page"
        assert blocks[0]["rect"]["approx"] is True
        assert [block for block in blocks if block["type"] == "table_cell"] == []

    def test_列数对不上时也整表框(self, tmp_path: Path) -> None:
        pages = [_page(22, self._blocks())]
        body = self._blocks()[0]["table_body"]
        # 几何是 3 列，HTML 是 4 列 → 行数不一致可由跨页解释，列数不一致不行
        three_columns = [
            [100 + index * 100, 200, 200 + index * 100, 300] for index in range(3)
        ]
        geometry = _geometry_for(pages, [_payload(body, three_columns)], tmp_path)

        blocks = build_positioned_blocks(pages, bbox_backend="mineru", table_geometry=geometry)

        assert [block["type"] for block in blocks] == ["table"]
        assert geometry.get(22, {}) == {}, "列数不一致的表不进定位映射（整表框 + 记 reason）"

    def test_回滚开关恢复旧均分(self) -> None:
        """``legacy_uniform=True`` 是灰度/回退手段：行为必须与改造前一致（precision=cell）。"""
        blocks = build_positioned_blocks(
            [_page(22, self._blocks())], bbox_backend="mineru", legacy_uniform=True
        )
        cells = [block for block in blocks if block["type"] == "table_cell"]

        assert len(cells) == 24
        assert {cell["rect"]["precision"] for cell in cells} == {"cell"}
        assert {cell["rect"]["approx"] for cell in cells} == {True}
        # 均分：首格落在表格左上角
        assert cells[0]["rect"]["x"] == pytest.approx(0.1, abs=0.01)
        assert cells[0]["rect"]["y"] == pytest.approx(0.2, abs=0.01)


# ── ⑦ p11 残片块（text 为空、HTML 在 block["html"]）─────────────


class TestFragmentBlock:
    #: p11 的 table 块：``table_body=None``、``text=""``、HTML 在 ``html`` 字段（SF-13）。
    _P11 = {
        "type": "table",
        "text": "",
        "bbox": [58, 110, 964, 337],
        "html": "<table><tr><td>……被截断的正文</td><td>3</td></tr>"
        "<tr><td>结果及送达</td><td>6</td></tr></table>",
    }

    def test_残片块不再被丢且整表框(self) -> None:
        blocks = build_positioned_blocks([_page(11, [self._P11])], bbox_backend="mineru")

        assert [block["type"] for block in blocks] == ["table"], "旧代码在 `not text` 那行把它整条丢了"
        assert blocks[0]["rect"]["precision"] == "page", "2 行残片拆格只会画错地方"
        assert blocks[0]["table_rows"] == 2
        assert blocks[0]["text"], "定位块不能是空标题（文字从表格 HTML 提）"

    def test_残片块不进正文(self) -> None:
        """正文红线：残片块在 markdown 里仍然不产出内容（与改造前逐字相同）。"""
        markdown = build_segment_markdown("证据清单", [_page(11, [self._P11])])

        assert markdown == "# 证据清单\n"
        assert "结果及送达" not in markdown


# ── ⑧ 正文零影响 ────────────────────────────────────────────


class TestMarkdownUnchanged:
    def test_有几何与无几何的正文逐字相同(self, p10_setup: tuple[list[PageDescriptor], dict[int, Any]]) -> None:
        """只有 ``positioned`` 变；``markdown`` 必须是同一个字符串。"""
        pages, geometry = p10_setup

        without = build_segments_markdown([_draft(10)], pages, bbox_backend="mineru")
        with_grid = build_segments_markdown([_draft(10)], pages, bbox_backend="mineru", table_geometry=geometry)
        with_uniform = build_segments_markdown(
            [_draft(10)], pages, bbox_backend="mineru", legacy_uniform=True
        )

        assert without[0]["markdown"] == with_grid[0]["markdown"] == with_uniform[0]["markdown"]
        assert without[0]["page_spans"] == with_grid[0]["page_spans"]
        # 定位确实变了（否则这条断言可能只是因为两边都是空的）
        assert [b["rect"]["precision"] for b in without[0]["positioned"]] == ["page"]
        assert {b["rect"]["precision"] for b in with_grid[0]["positioned"]} == {"grid"}

    def test_两页正文逐字快照(self, p10_setup: tuple[list[PageDescriptor], dict[int, Any]]) -> None:
        """p10 + p11 两页的正文快照：几何接线不能顺手改到 ``_assemble_segment``。"""
        pages, geometry = p10_setup
        fragment = TestFragmentBlock._P11
        pages = [pages[0], _page(11, [fragment])]
        draft = SegmentDraft(
            order=1,
            page_start=10,
            page_end=11,
            segment_type="evidence",
            filename="证据清单.pdf",
            confidence=1.0,
            source_method="llm",
            review_flag="normal",
        )

        grid = build_segments_markdown([draft], pages, bbox_backend="mineru", table_geometry=geometry)
        plain = build_segments_markdown([draft], pages, bbox_backend="mineru")

        assert grid[0]["markdown"] == plain[0]["markdown"]
        assert grid[0]["markdown"].startswith("# 证据清单\n\n")
        # 表头行与末行都在（GFM 表格形状没被拆格逻辑动过）
        assert "| 材料 类别 | 序号 | 名称 | 证明内容 | 件数 | 页码 |" in grid[0]["markdown"]
        assert "结果及送达" not in grid[0]["markdown"], "p11 残片仍不进正文"
