"""PP-StructureV3 的表格几何解析层（``table_res_list``）。

## 为什么必须多读一个信封

``pp_structure_v3`` 走 ``_OCR_ENDPOINT_MODELS`` 分支，``_parse_ocr_response`` 读的是
``result["ocrResults"][i]["prunedResult"]``；而真实响应里那个 ``prunedResult`` 的键是
``model_settings / dt_polys / text_det_params / text_type / textline_orientation_angles /
text_rec_score_thresh / return_word_box / rec_texts / rec_scores / rec_polys / rec_boxes``
——**没有** ``table_res_list``。

表格几何在**另一个信封**：``result["layoutParsingResults"][0]["prunedResult"]["table_res_list"]``
（实测 p10 一页一表 33 个 cell）。所以修法不是「别丢字段」，而是多读一个信封；
``test_几何不在_ocrResults_信封里_别读错树`` 就是防止把解析逻辑写回旧树。

fixture ``tests/ci/fixtures/pdf_splitting/pp_structure_p10_table.json``：这次真实调用的
最小裁剪版（``layoutParsingResults[0].prunedResult`` 的 ``width/height/table_res_list``
+ ``ocrResults[0].prunedResult.rec_texts`` 骨架），已脱敏（姓名/单位名/地址 → 甲/乙/某）。

## 跑法（红线：只能连测试库）

纯函数测试，不需要 ``django_db``；但 conftest 仍会校验库名，必须显式给测试库：

```bash
cd backend
DB_NAME=test_fachuan_dev .venv/bin/python -m pytest tests/ci/unit/automation/test_pp_structure_tables.py -q
```
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from apps.automation.services.ocr.paddleocr_api_service import parse_table_results, parse_table_results_by_page

#: 裁剪后的真实响应。
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "pdf_splitting" / "pp_structure_p10_table.json"
)

#: fixture 里这张表的实测事实（``facts/raw/p10_raw.json`` 的数，别凭记忆改）。
_P10_CELLS = 33
_P10_TD = 33
_P10_TR = 6
_P10_REC_TEXTS = 70
_P10_CROP_PX = (1555, 1660)


def _raw_result() -> dict[str, Any]:
    """完整响应体的 ``result`` 段（fixture 保留了 ``layoutParsingResults`` 信封）。"""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    result = payload["result"]
    assert isinstance(result, dict)
    return result


def _table_res() -> dict[str, Any]:
    """fixture 里那一条 ``table_res_list[0]``，用于逐字段核对解析结果。"""
    table = _raw_result()["layoutParsingResults"][0]["prunedResult"]["table_res_list"][0]
    assert isinstance(table, dict)
    return table


def _row_bands(cell_boxes: tuple[tuple[float, float, float, float], ...], *, tol: float) -> list[list[int]]:
    """把 cell 的**上边**归到最近的一条水平边界线上，返回每个行带里的 cell 下标。

    注意不能按「框中心最近的边界」归行：rowspan 的框中心落在两行中间，
    会被归到相邻行去（第一版就是这么写错的，实测得到 ``[3,6,6,5,5,5,3]``）。

    这里自带一份最小聚类，是为了让「解析层」的断言**不依赖``table_geometry``**
    （否则两层的待实现状态会互相拖死）。容差口径与 geometry 侧一致：裁图像高的 1%。
    6 行的表格有 **7 条**水平边界线 —— 断言的是 7 条线、6 个行带。
    """
    edges: list[float] = []
    for x0, y0, x1, y1 in cell_boxes:
        edges.extend((y0, y1))
    edges.sort()
    lines: list[list[float]] = [[edges[0]]]
    for value in edges[1:]:
        if value - lines[-1][-1] <= tol:
            lines[-1].append(value)
        else:
            lines.append([value])
    centers = [sum(line) / len(line) for line in lines]
    grouped: list[list[int]] = [[] for _ in centers]
    for index, (x0, y0, x1, y1) in enumerate(cell_boxes):
        top = min(range(len(centers)), key=lambda i: abs(centers[i] - y0))
        grouped[top].append(index)
    # 最后一条边界线是表底，不该有框从那里「开始」；多出来的空列直接暴露错位
    assert not grouped[-1], "有框从表底边界开始 —— 说明坐标顺序不对"
    return list(grouped[:-1])


# ── 正常路径：真实响应能取到几何 ────────────────────────────────


class TestP10RealResponse:
    """p10 证据清单表：PP-StructureV3 单次调用的真实响应。"""

    def test_能从_layoutParsingResults_信封取出表格结果(self) -> None:
        parsed = parse_table_results(_raw_result())

        assert len(parsed) == 1, "p10 这张裁图里有且只有一张表"
        table = parsed[0]
        assert len(table.cell_boxes) == _P10_CELLS
        assert "<td" in table.html
        # 信封里的 table_ocr_pred.rec_texts 也要能透出（下游做 cell 文本比对要用）
        assert len(table.texts) == _P10_REC_TEXTS

    def test_裁图像素尺寸来自_prunedResult_的_width_height(self) -> None:
        parsed = parse_table_results(_raw_result())

        # 这条很关键：cell_box_list 是**裁图**像素坐标，没有裁图尺寸就无法反算页面坐标。
        # 实测 prunedResult.width/height = 1555/1660（= 559.8×597.6pt @200dpi）。
        assert parsed[0].image_size == _P10_CROP_PX

    def test_cells_与_pred_html_的_td_数量一致(self) -> None:
        table = _table_res()
        parsed = parse_table_results(_raw_result())

        html_td = table["pred_html"].count("<td")
        assert html_td == _P10_TD
        assert len(parsed[0].cell_boxes) == html_td, "数量不等就不能硬配（DESIGN §8 cell_order_mismatch）"

    def test_cells_与_td_同序_都是_row_major(self) -> None:
        """实测结论：``cell_box_list`` 与 ``pred_html`` 的 ``<td>`` 1:1 同序（row-major）。

        断言方式：按 y 聚行带后，行带数量 = 物理行数 6，且每行带的 cell 数 = [6,6,5,6,5,5]
        （首列 rowspan=2 + rowspan=3 让第 3、5、6 行各少一个 td）。顺序不对就凑不出这个形状。
        """
        parsed = parse_table_results(_raw_result())
        boxes = parsed[0].cell_boxes

        bands = _row_bands(boxes, tol=_P10_CROP_PX[1] * 0.01)
        assert len(bands) == _P10_TR, "6 行 → 7 条水平边界线 → 6 个行带"
        assert [len(group) for group in bands] == [6, 6, 5, 6, 5, 5]
        # row-major：行带内部下标必须连续递增，行带之间首尾相接
        flat = [index for group in bands for index in group]
        assert flat == sorted(flat)
        assert flat == list(range(_P10_CELLS))

    def test_几何不在_ocrResults_信封里_别读错树(self) -> None:
        """把 ``ocrResults`` 那一支单独交给解析函数 → 空列表，不许「顺手」从别处捞。"""
        result = _raw_result()
        ocr_only = {"ocrResults": result["ocrResults"]}

        assert parse_table_results(ocr_only) == []

    def test_未知信封形状一律空列表(self) -> None:
        assert parse_table_results({"layoutParsingResults": [{"prunedResult": {"table_res_list": []}}]}) == []


# ── 降级：脏数据不许抛 ──────────────────────────────────────────


class TestDegradation:
    """解析层是「一次付费调用的唯一出口」，脏数据只能降级，不能抛。"""

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="空 dict"),
            pytest.param({"layoutParsingResults": []}, id="空页列表"),
            pytest.param({"layoutParsingResults": "not-a-list"}, id="页列表不是 list"),
            pytest.param({"layoutParsingResults": [{}]}, id="页项缺 prunedResult"),
            pytest.param({"layoutParsingResults": [{"prunedResult": None}]}, id="prunedResult 为 None"),
            pytest.param({"layoutParsingResults": [{"prunedResult": "{not json"}]}, id="prunedResult 是坏 JSON 串"),
            pytest.param(
                {"layoutParsingResults": [{"prunedResult": {"table_res_list": None}}]},
                id="table_res_list 为 None",
            ),
            pytest.param(
                {"layoutParsingResults": [{"prunedResult": {"table_res_list": {}}}]},
                id="table_res_list 是 dict 不是 list",
            ),
            pytest.param(
                {"layoutParsingResults": [{"prunedResult": {"table_res_list": [None, 7, "x"]}}]},
                id="table_res_list 里全是垃圾项",
            ),
            pytest.param(
                {"layoutParsingResults": [{"prunedResult": {"table_res_list": [{"cell_box_list": "x"}]}}]},
                id="cell_box_list 是字符串",
            ),
        ],
    )
    def test_缺字段或脏形状降级为空且不抛(self, payload: dict[str, Any]) -> None:
        assert parse_table_results(payload) == []

    def test_prunedResult_是_JSON_字符串时照样能解析(self) -> None:
        """``prunedResult`` 实测可能是 ``str``（``_parse_ocr_response`` 拿到过）。"""
        pruned = _raw_result()["layoutParsingResults"][0]["prunedResult"]
        payload = {"layoutParsingResults": [{"prunedResult": json.dumps(pruned, ensure_ascii=False)}]}

        parsed = parse_table_results(payload)

        assert len(parsed) == 1
        assert len(parsed[0].cell_boxes) == _P10_CELLS
        assert parsed[0].image_size == _P10_CROP_PX

    def test_元素级脏坐标逐条丢弃_不影响同表其他框(self) -> None:
        payload = {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 100,
                        "height": 100,
                        "table_res_list": [
                            {
                                "cell_box_list": [
                                    [0, 0, 10, 10],
                                    [0, 0, 10],  # 只有 3 个数
                                    None,  # 不是序列
                                    ["a", "b", "c", "d"],  # 不是数字
                                    [20.0, 20.0, 30.0, 30.0],
                                ],
                                "pred_html": "<table><tr><td>a</td><td>b</td></tr></table>",
                            }
                        ],
                    }
                }
            ]
        }
        parsed = parse_table_results(payload)

        assert len(parsed) == 1
        # 只留两条合法框，顺序保持原样（顺序是「与 td 同序」的前提，不能重排）
        assert parsed[0].cell_boxes == ((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0))

    def test_缺_pred_html_或_table_ocr_pred_时字段为空(self) -> None:
        payload = {
            "layoutParsingResults": [
                {"prunedResult": {"width": 10, "height": 10, "table_res_list": [{"cell_box_list": [[0, 0, 5, 5]]}]}}
            ]
        }
        parsed = parse_table_results(payload)

        assert len(parsed) == 1
        assert parsed[0].html == ""
        assert parsed[0].texts == ()

    def test_缺裁图宽高时_image_size_为_None(self) -> None:
        payload = {
            "layoutParsingResults": [
                {"prunedResult": {"table_res_list": [{"cell_box_list": [[0, 0, 5, 5]], "pred_html": "<td>"}]}}
            ]
        }
        parsed = parse_table_results(payload)

        # 宁可给 None（调用方据此整表框），也不要编一个 1000×1000 的假定尺寸
        assert parsed[0].image_size is None

    def test_裸片段行的_table_res_list_也能取到(self) -> None:
        """PDF 的 JSONL 切片里会出现不带容器的裸片段行（``_parse_jsonl_response`` 同源）。"""
        pruned = _raw_result()["layoutParsingResults"][0]["prunedResult"]

        parsed = parse_table_results(pruned)

        assert len(parsed) == 1
        assert len(parsed[0].cell_boxes) == _P10_CELLS


# ── 端到端：解析结果要挂到 PaddleOCRApiResult 上 ────────────────


class TestParseResponseIntegration:
    """光有纯函数还不够：``_parse_response`` 的产物里也得能拿到表，否则等于没接上。"""

    def _engine(self) -> Any:
        from apps.automation.services.ocr.paddleocr_api_service import PaddleOCRApiEngine

        with patch("apps.automation.services.ocr.paddleocr_api_service.SystemConfigService"):
            return PaddleOCRApiEngine(model="pp_structure_v3")

    def test_parse_response_为_pp_structure_v3_带上表格结果(self) -> None:
        payload = {"result": _raw_result()}
        parsed_result = self._engine()._parse_response(payload, "pp_structure_v3")

        assert parsed_result.tables, "PP-StructureV3 的表格几何必须随结果一起出来"
        assert len(parsed_result.tables[0].cell_boxes) == _P10_CELLS
        # 不能为了拿表把正文弄丢：rec_texts 仍在（回归保护）
        assert parsed_result.text.strip()

    def test_parse_response_对纯文字模型不解析表格(self) -> None:
        """PP-OCRv5 没有 ``layoutParsingResults``，不能顺手也去解析（会把空表当结果）。"""
        payload = {"result": _raw_result()}

        parsed_result = self._engine()._parse_response(payload, "pp_ocrv5")

        assert parsed_result.tables == []

    def test_jsonl_路径同样聚合表格几何(self) -> None:
        """PDF 输入的响应是多行 JSONL，只取某一行会丢表。"""
        line = json.dumps({"result": _raw_result()}, ensure_ascii=False)
        jsonl_text = "\n".join([line, line])

        parsed_result = self._engine()._parse_jsonl_response(jsonl_text, "pp_structure_v3")

        assert len(parsed_result.tables) == 2, "每行各带一张表 → 两行合并成两张"
        assert len(parsed_result.tables[0].cell_boxes) == _P10_CELLS
        assert parsed_result.text.strip()


# ── 逐页分组：批量路径的页码维度 ────────────────────────────────


class TestPerPageGrouping:
    """批量送子 PDF 时响应是 JSONL、一行 = 一页，``table_res_list`` 是**每页各自**的列表。

    扁平的 ``tables`` 表达不了「哪张表属于哪一页」，把两页的表连成一片就是
    “把 A 页的格子画到 B 页上”。``parse_table_results_by_page`` 给出页码维度，
    并且外层下标必须与送检页序一致。
    """

    def test_一页一表时外层下标就是页序(self) -> None:
        grouped = parse_table_results_by_page(_raw_result())

        assert len(grouped) == 1
        assert len(grouped[0]) == 1
        assert len(grouped[0][0].cell_boxes) == _P10_CELLS

    def test_同页多表留在同一组(self) -> None:
        """p16/p20 的形状：一页两张表。分组后仍同属该页，不能摊到下一页去。"""
        pruned = _raw_result()["layoutParsingResults"][0]["prunedResult"]
        table = pruned["table_res_list"][0]
        two_tables = {
            "width": pruned["width"],
            "height": pruned["height"],
            "table_res_list": [table, table],
        }
        result = {"layoutParsingResults": [{"prunedResult": two_tables}]}

        grouped = parse_table_results_by_page(result)

        assert len(grouped) == 1, "两页会被摊成两行，这里必须只有一页"
        assert len(grouped[0]) == 2

    def test_没有表的页保留空组(self) -> None:
        """一页没出表也不能让后面的页**前移**（前移＝整本页码错位）。"""
        pruned = _raw_result()["layoutParsingResults"][0]["prunedResult"]
        empty_page = {"prunedResult": {"width": 1191, "height": 1683, "table_res_list": []}}
        result = {"layoutParsingResults": [empty_page, {"prunedResult": pruned}]}

        grouped = parse_table_results_by_page(result)

        assert len(grouped) == 2
        assert grouped[0] == []
        assert len(grouped[1]) == 1

    def test_jsonl_逐页分组按行序拼接(self) -> None:
        """传 PDF 的多行 JSONL：外层下标跨行连续，等于送检页序。"""
        payload = _raw_result()
        empty_line = json.dumps(
            {"result": {"layoutParsingResults": [{"prunedResult": {"width": 1191, "height": 1683}}]}},
            ensure_ascii=False,
        )
        line = json.dumps({"result": payload}, ensure_ascii=False)

        parsed = TestParseResponseIntegration()._engine()._parse_jsonl_response(
            "\n".join([empty_line, line]), "pp_structure_v3"
        )

        assert len(parsed.table_pages) == 2, "两行 = 两页"
        assert parsed.table_pages[0] == []
        assert len(parsed.table_pages[1]) == 1
        assert len(parsed.tables) == 1, "扁平列表仍然同源（旧调用方）"

    def test_行级_ocr_文本框随表一起透出(self) -> None:
        """``rec_boxes`` 是“文本按几何归属”的前提；缺了它格内文本只能留空。"""
        pruned = _raw_result()["layoutParsingResults"][0]["prunedResult"]
        table = pruned["table_res_list"][0]
        with_boxes = {
            "width": pruned["width"],
            "height": pruned["height"],
            "table_res_list": [
                {
                    **table,
                    "table_ocr_pred": {
                        "rec_texts": ["甲", "乙"],
                        "rec_boxes": [[0, 0, 10, 10], [20, 20, 30, 30]],
                    },
                }
            ],
        }

        parsed = parse_table_results({"layoutParsingResults": [{"prunedResult": with_boxes}]})

        assert parsed[0].texts == ("甲", "乙")
        assert parsed[0].text_boxes == ((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0))

    def test_缺_rec_boxes_时文本与框长度不等(self) -> None:
        """fixture 只有 ``rec_texts``：下游据“长度不等”整批不用，不按下标硬配。"""
        parsed = parse_table_results(_raw_result())

        assert parsed[0].texts, "rec_texts 仍在（PR-1 契约不变）"
        assert parsed[0].text_boxes == ()


# ── 数量闸门（2026-11-21 放宽）────────────────────────────────


class TestCellCountGate:
    """``cell_box_list`` 与 ``<td>`` 数不等时怎么处理。

    真实事故（job 523fabce 端到端）：
    ``PaddleOCR 表格解析: cell_box_list(39) 与 pred_html 的 <td>(47) 数量不等，该表已跳过``
    —— 8 个退化框被过滤就把整张真表丢掉了。而 PP 输出 rowspan/colspan 时
    ``<td>`` 数本来就不等于格位数。顺序既然已经没有消费方（行列靠几何聚类、
    文本按几何归属），闸门就只该留「框不能比渲染格还多」这一条上界。
    """

    def _pruned_with(self, boxes: list[Any], td_count: int) -> dict[str, Any]:
        row = "".join("<td></td>" for _ in range(td_count))
        return {
            "width": 1000,
            "height": 1000,
            "table_res_list": [{"cell_box_list": boxes, "pred_html": f"<table><tr>{row}</tr></table>"}],
        }

    def test_框数少于_td_数时照收(self) -> None:
        boxes = [[0, 0, 10, 10], [20, 0, 30, 10]]
        payload = {"layoutParsingResults": [{"prunedResult": self._pruned_with(boxes, 3)}]}

        parsed = parse_table_results(payload)

        assert len(parsed) == 1, "少几个框不该整表作废（下游只少画几格）"
        assert len(parsed[0].cell_boxes) == 2

    def test_框数多于_td_数时跳过(self) -> None:
        boxes = [[0, 0, 10, 10], [20, 0, 30, 10], [40, 0, 50, 10]]
        payload = {"layoutParsingResults": [{"prunedResult": self._pruned_with(boxes, 2)}]}

        assert parse_table_results(payload) == [], "框比渲染格还多 = 结果自相矛盾"

    def test_数量不等时仍透出行级文本框(self) -> None:
        """文本按几何归属要 ``rec_boxes``：闸门放宽后它必须还在。"""
        pruned = self._pruned_with([[0, 0, 10, 10]], 4)
        pruned["table_res_list"][0]["table_ocr_pred"] = {"rec_texts": ["甲"], "rec_boxes": [[0, 0, 10, 10]]}

        parsed = parse_table_results({"layoutParsingResults": [{"prunedResult": pruned}]})

        assert len(parsed) == 1
        assert parsed[0].text_boxes == ((0.0, 0.0, 10.0, 10.0),)
