"""页面方向反变换（``split/page_rotation.py``）：公式、p52 真实样本标定、两处接线的端到端。

## 这个文件在守什么

开启 PaddleOCR 整页方向分类后，服务端返回的**所有**坐标都在「转正帧」（``p52`` 实测：
转正帧 1753×1240、原图 1240×1753、``doc_preprocessor_res.angle=270``）。不反变换，
版面框与表格格子就会整片横躺；转两次，它们会飘到页外。所以本文件钉三件事：

1. **公式**（``TestDerotateMath``）：四个直角的点/矩形映射与 ``numpy.rot90`` 的逐像素结果
   一致（独立实现对照，不是抄同一份公式），且 round-trip 误差 < 1e-6；
2. **方向**（``TestP52RealSample``）：用真实 p52 响应标定——反变换后的标题 rect 必须落在
   原页**另一次调用**（方向分类关闭、未旋转）检出的文本行框内，且矩形内墨迹占比远高于
   随机平移位置。方向搞反（θ=90/180）或干脆不回写（θ=0）这条都过不去；
3. **接线**（``TestWiring``）：VL 块与 PP 表格 cells 出 OCR 层时都已回到原页帧，且只转一次。

## fixture 与脱敏

``pp_structure_p52_rotated.json`` 是 p52 真实响应的切片：人名/医院名 → 「甲/乙」，
证件号/电话/诊断正文等字段整段删除；``original_page.ink_boxes`` 只保留几何（文本行框的
外接矩形），不含任何文字。

## 跑法（红线：只能连测试库）

```bash
cd backend
DB_NAME=test_fachuan_dev_tg_b .venv/bin/python -m pytest tests/ci/unit/pdf_splitting/test_page_rotation.py -q
```
"""

from __future__ import annotations

import json
import random
import typing
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from apps.automation.services.ocr.paddleocr_api_service import parse_table_results
from apps.pdf_splitting.services.split import ocr_handler, table_geometry_pass
from apps.pdf_splitting.services.split.dual_engine import normalize_paddleocr_vl_blocks
from apps.pdf_splitting.services.split.page_rotation import (
    THETAS,
    derotate_pixel_box,
    derotate_point,
    derotate_rect,
    normalize_theta,
    page_angle,
    rotated_frame_size,
)

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "pdf_splitting" / "pp_structure_p52_rotated.json"

#: p52 的实测帧尺寸：转正帧 1753×1240（服务端返回的 width/height）、原图 1240×1753。
ROT_W, ROT_H = 1753.0, 1240.0
ORIG_W, ORIG_H = 1240.0, 1753.0

#: 转正帧里「疾病诊断证明书」标题块的 block_bbox（真实值）。
P52_TITLE_BBOX = (542.0, 339.0, 1216.0, 441.0)

#: 原页帧里那条标题文本行的框（**另一次**调用检出：方向分类关闭 + 未旋转）。
P52_TITLE_LINE_BOX = (341.0, 534.0, 392.0, 1209.0)

#: 归一化比较容差：页宽的 1%（≈12px），足够吸收两套检测框的固有差异。
_TOL = 0.01


def _fixture() -> dict[str, Any]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _page() -> dict[str, Any]:
    page = _fixture()["page"]
    assert isinstance(page, dict)
    return page


def _ink_boxes() -> list[list[float]]:
    boxes = _fixture()["original_page"]["ink_boxes"]
    assert isinstance(boxes, list)
    return boxes


def _title_norm() -> dict[str, float]:
    """p52 标题块在**转正帧**的归一化矩形（服务端原样返回的坐标）。"""
    x0, y0, x1, y1 = P52_TITLE_BBOX
    return {"x": x0 / ROT_W, "y": y0 / ROT_H, "w": (x1 - x0) / ROT_W, "h": (y1 - y0) / ROT_H}


def _to_pixels(rect: dict[str, float]) -> tuple[float, float, float, float]:
    """原页帧归一化矩形 → 原页帧像素框。"""
    x0, y0 = rect["x"] * ORIG_W, rect["y"] * ORIG_H
    return (x0, y0, x0 + rect["w"] * ORIG_W, y0 + rect["h"] * ORIG_H)


def _overlap(rect_px: tuple[float, float, float, float], box: typing.Sequence[float]) -> float:
    """两个像素框的交集面积。"""
    ox = max(0.0, min(rect_px[2], box[2]) - max(rect_px[0], box[0]))
    oy = max(0.0, min(rect_px[3], box[3]) - max(rect_px[1], box[1]))
    return ox * oy


def _ink_coverage(rect: dict[str, float]) -> float:
    """原页帧归一化矩形内被墨迹框覆盖的面积占比。"""
    rect_px = _to_pixels(rect)
    area = (rect_px[2] - rect_px[0]) * (rect_px[3] - rect_px[1])
    if area <= 0:
        return 0.0
    return sum(_overlap(rect_px, box) for box in _ink_boxes()) / area


def _best_line_coverage(rect: dict[str, float]) -> float:
    """单个墨迹框对该矩形的最大覆盖占比（一个文本块 ≈ 一条文本行，看的就是这个）。"""
    rect_px = _to_pixels(rect)
    area = (rect_px[2] - rect_px[0]) * (rect_px[3] - rect_px[1])
    if area <= 0:
        return 0.0
    return max(_overlap(rect_px, box) for box in _ink_boxes()) / area


def _random_shift_baseline(rect: dict[str, float], *, samples: int = 2000) -> tuple[float, float]:
    """同尺寸矩形随机平移后的（墨迹占比中位数, 单框最大覆盖中位数）。"""
    rng = random.Random(20261121)  # 固定种子：断言必须可复现
    coverages: list[float] = []
    bests: list[float] = []
    for _ in range(samples):
        shifted = {
            "x": rng.uniform(0.0, 1.0 - rect["w"]),
            "y": rng.uniform(0.0, 1.0 - rect["h"]),
            "w": rect["w"],
            "h": rect["h"],
        }
        coverages.append(_ink_coverage(shifted))
        bests.append(_best_line_coverage(shifted))
    coverages.sort()
    bests.sort()
    middle = samples // 2
    return coverages[middle], bests[middle]


# ── ① 公式：与 numpy 的旋转逐像素对照 ──────────────────────────


class TestDerotateMath:
    """公式本身：方向、宽高互换、round-trip。"""

    @pytest.mark.parametrize("theta", THETAS)
    def test_与_numpy_旋转逐像素一致(self, theta: int) -> None:
        """独立实现对照：把转正帧的掩膜按 θ 转回去，标记框的外接矩形 = ``derotate_rect``。

        掩膜用 ``numpy.rot90``（k=1 是**逆时针** 90°），与我们的公式没有任何共享代码——
        方向或宽高互换写错时这里必然对不上。
        """
        rot_w, rot_h = 40, 26
        mask = np.zeros((rot_h, rot_w), dtype=bool)
        mask[7:19, 5:33] = True  # 转正帧里的一个非对称矩形（x 5..33, y 7..19）
        # 服务端把原页逆时针转了 θ；转回来就是再逆时针转 (360-θ)
        back = np.rot90(mask, k=((360 - theta) // 90) % 4)
        rows, cols = np.nonzero(back)
        orig_h, orig_w = back.shape

        rect = derotate_rect(
            {"x": 5 / rot_w, "y": 7 / rot_h, "w": 28 / rot_w, "h": 12 / rot_h},
            theta,
            rot_w=rot_w,
            rot_h=rot_h,
        )

        assert rect["x"] * orig_w == pytest.approx(float(cols.min()), abs=1e-9)
        assert rect["y"] * orig_h == pytest.approx(float(rows.min()), abs=1e-9)
        assert (rect["x"] + rect["w"]) * orig_w == pytest.approx(float(cols.max() + 1), abs=1e-9)
        assert (rect["y"] + rect["h"]) * orig_h == pytest.approx(float(rows.max() + 1), abs=1e-9)

    @pytest.mark.parametrize("theta", THETAS)
    def test_round_trip_误差小于_1e_6(self, theta: int) -> None:
        """``derotate(derotate(r, θ), 360-θ) ≈ r``：贴边、零宽、整页四种形状都测。"""
        orig_w, orig_h = rotated_frame_size(theta, rot_w=ROT_W, rot_h=ROT_H)
        rects = (
            {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            {"x": 0.0, "y": 0.0, "w": 0.125, "h": 0.5},
            {"x": 0.875, "y": 0.5, "w": 0.125, "h": 0.5},
            {"x": 0.3092, "y": 0.2734, "w": 0.3845, "h": 0.0823},
        )
        for rect in rects:
            back = derotate_rect(rect, theta, rot_w=ROT_W, rot_h=ROT_H)
            again = derotate_rect(back, (360 - theta) % 360, rot_w=orig_w, rot_h=orig_h)
            for key in ("x", "y", "w", "h"):
                assert again[key] == pytest.approx(rect[key], abs=1e-6), f"θ={theta} {rect} 的 {key}"

    def test_四个角点落在原页帧的四个角上(self) -> None:
        """转正帧左上角 → 原页帧的角（θ=90 右上、θ=270 左下）；输出必须在原页帧边界内。"""
        expected = {0: (0.0, 0.0), 90: (ROT_H, 0.0), 180: (ROT_W, ROT_H), 270: (0.0, ROT_W)}
        for theta, want in expected.items():
            orig_w, orig_h = rotated_frame_size(theta, rot_w=ROT_W, rot_h=ROT_H)
            got = derotate_point(0.0, 0.0, theta, rot_w=ROT_W, rot_h=ROT_H)
            assert got == pytest.approx(want), f"θ={theta}"
            assert 0.0 <= got[0] <= orig_w and 0.0 <= got[1] <= orig_h, f"θ={theta} 跑出了原页帧"
        # 90 与 270 必须落在**不同的**角上：只差宽高互换的话两条会相等
        assert derotate_point(0.0, 0.0, 90, rot_w=ROT_W, rot_h=ROT_H) != derotate_point(
            0.0, 0.0, 270, rot_w=ROT_W, rot_h=ROT_H
        )

    def test_脏角度与缺帧尺寸的边界(self) -> None:
        """脏 angle 归 0（不抛）；像素反变换缺帧尺寸时报错，不编坐标。"""
        assert normalize_theta(270) == 270
        assert normalize_theta(-90) == 270
        assert normalize_theta("180") == 180
        assert normalize_theta(45) == 0
        assert normalize_theta(None) == 0
        assert page_angle({"doc_preprocessor_res": {"angle": 90}}) == 90
        assert page_angle({}) == 0
        assert page_angle({"doc_preprocessor_res": {"angle": "x"}}) == 0
        assert rotated_frame_size(90, rot_w=ROT_W, rot_h=ROT_H) == (ROT_H, ROT_W)
        assert rotated_frame_size(180, rot_w=ROT_W, rot_h=ROT_H) == (ROT_W, ROT_H)
        with pytest.raises(ValueError, match="帧尺寸"):
            derotate_point(1.0, 2.0, 90, rot_w=0.0, rot_h=ROT_H)


# ── ② 方向：p52 真实样本的墨迹标定 ─────────────────────────────


class TestP52RealSample:
    """真实样本标定：反变换后的矩形必须压在**原页**的墨迹上。"""

    def test_标题块反变换后落在原页检出的文本行框内(self) -> None:
        """最强的一条：原页那次独立检测到的标题文本行框，必须被反变换后的 rect 包住。

        两个框来自**两次不同调用**（一次开方向分类、一次不开），唯一的联系是本文件的
        公式——方向写反时这条必然失败（θ=90/180/0 都包不住）。
        """
        rect = derotate_rect(_title_norm(), 270, rot_w=ROT_W, rot_h=ROT_H)
        x0, y0, x1, y1 = _to_pixels(rect)
        tol_x, tol_y = _TOL * ORIG_W, _TOL * ORIG_H
        left, top, right, bottom = P52_TITLE_LINE_BOX

        assert x0 - tol_x <= left and y0 - tol_y <= top, "标题行框的左/上边落在 rect 外"
        assert right <= x1 + tol_x and bottom <= y1 + tol_y, "标题行框的右/下边落在 rect 外"
        # 反过来也得成立：rect 不该是一个盖住半页的大框（那样「包住」毫无信息量）
        assert rect["w"] * ORIG_W < 0.25 * ORIG_W
        assert rect["h"] * ORIG_H < 0.75 * ORIG_H

    def test_墨迹占比显著高于随机平移(self) -> None:
        """可自动断言的口径：rect 内墨迹占比 0.74，随机平移中位数 0.22（≥3 倍）。"""
        rect = derotate_rect(_title_norm(), 270, rot_w=ROT_W, rot_h=ROT_H)
        coverage = _ink_coverage(rect)
        median, _ = _random_shift_baseline(rect)

        assert coverage >= 0.45, f"反变换后的标题 rect 里几乎没有墨（coverage={coverage:.3f}）"
        assert coverage >= 3.0 * median, f"coverage={coverage:.3f} 没到随机平移中位数 {median:.3f} 的 3 倍"

    def test_单条文本行填满矩形且远超随机(self) -> None:
        """标题块 = 一条文本行：单个墨迹框就该覆盖 rect 的一半，是随机中位数的 6 倍以上。"""
        rect = derotate_rect(_title_norm(), 270, rot_w=ROT_W, rot_h=ROT_H)
        best = _best_line_coverage(rect)
        _, median_best = _random_shift_baseline(rect)

        assert best >= 0.45, f"没有哪条墨迹框填得住这个 rect（best={best:.3f}）"
        assert best >= 5.0 * median_best, f"best={best:.3f} 没到随机中位数 {median_best:.3f} 的 5 倍"

    def test_只有正确的角度能同时通过墨迹与位置判据(self) -> None:
        """θ=0/90/180 的墨迹占比都低于 θ=270：方向错一位就不成立。"""
        covariances = {
            theta: _ink_coverage(derotate_rect(_title_norm(), theta, rot_w=ROT_W, rot_h=ROT_H)) for theta in THETAS
        }

        assert covariances[270] == max(covariances.values())
        for theta in (0, 90, 180):
            assert covariances[theta] < covariances[270], f"θ={theta} 与 θ=270 分不开（{covariances}）"


# ── ③ 接线：出 OCR 层时已在原页帧，且只转一次 ────────────────


class TestWiring:
    """两处接线：VL 块（``dual_engine.normalize_paddleocr_vl_blocks``）与 PP 表格 cells。"""

    def _title_block(self, page: dict[str, Any]) -> Any:
        blocks = normalize_paddleocr_vl_blocks([page])
        for block in blocks:
            if "疾病诊断证明书" in block.text:
                return block
        raise AssertionError("fixture 里必须有标题块")

    def test_vl块开方向分类后回到原页帧(self) -> None:
        rect = self._title_block(_page()).rect

        # 归一化到原页帧后应落在页面左侧偏中（x 0.27–0.36、y 0.31–0.69），与标题行框一致
        assert rect["x"] == pytest.approx(0.2734, abs=1e-3)
        assert rect["y"] == pytest.approx(0.3063, abs=1e-3)
        assert rect["w"] == pytest.approx(0.0823, abs=1e-3)
        assert rect["h"] == pytest.approx(0.3845, abs=1e-3)

    def test_vl块关方向分类时坐标留在转正帧(self) -> None:
        """没有 ``doc_preprocessor_res`` = 服务端没转 —— 坐标不许被动过（逐位等于改动前）。"""
        page = dict(_page())
        page.pop("doc_preprocessor_res")

        rect = self._title_block(page).rect

        assert rect["x"] == pytest.approx(542.0 / ROT_W, abs=1e-4)
        assert rect["y"] == pytest.approx(339.0 / ROT_H, abs=1e-4)
        assert rect["w"] == pytest.approx(674.0 / ROT_W, abs=1e-4)
        assert rect["h"] == pytest.approx(102.0 / ROT_H, abs=1e-4)

    def test_vl块转正但缺帧尺寸时不出框(self) -> None:
        """知道页被转过、却拿不到转正帧尺寸 → 换不回原页帧：宁可不出框，也不画横躺的框。"""
        page = dict(_page())
        page["width"] = None
        page["height"] = None

        block = self._title_block(page)

        assert block.rect == {}
        assert block.approx is True
        assert "疾病诊断证明书" in block.text, "没坐标不等于丢正文"

    def test_vl_page_layout_的千分比在原页帧(self) -> None:
        """``ocr_handler.vl_page_layout`` 是 ocr_handler 的唯一消费点，钉住具体范围。"""
        layout = ocr_handler.vl_page_layout([{"prunedResult": _page()}], page_no=52, text="正文")
        assert layout is not None
        title = next(block for block in layout["blocks"] if "疾病诊断证明书" in str(block.get("text")))
        bbox = title["bbox"]

        assert bbox[0] == pytest.approx(273.4, abs=1.0)
        assert bbox[1] == pytest.approx(306.3, abs=1.0)
        assert bbox[2] == pytest.approx(355.7, abs=1.0)
        assert bbox[3] == pytest.approx(690.8, abs=1.0)

    def _table(self, page: dict[str, Any]) -> Any:
        tables = parse_table_results({"layoutParsingResults": [{"prunedResult": page}]})
        assert tables, "fixture 里必须有表"
        return tables[0]

    def test_表格_payload_反变换回原页帧并换帧尺寸(self) -> None:
        table = self._table(_page())
        payload = table_geometry_pass._table_payload(table)

        assert table.page_angle == 270
        assert tuple(payload["image_size"]) == (int(ORIG_W), int(ORIG_H)), "90/270 必须换成原页帧尺寸"
        expected = derotate_pixel_box(table.cell_boxes[0], 270, rot_w=ROT_W, rot_h=ROT_H)
        assert payload["cell_box_list"][0] == pytest.approx(list(expected))
        # 行级 OCR 框与格子同源，必须一起换；只换一半会让「文本贴错格」
        assert payload["table_ocr_pred"]["rec_boxes"][0] == pytest.approx(list(expected))

    def test_表格_payload_未转正时逐位不变(self) -> None:
        page = dict(_page())
        page.pop("doc_preprocessor_res")
        table = self._table(page)
        payload = table_geometry_pass._table_payload(table)

        assert table.page_angle == 0
        assert tuple(payload["image_size"]) == (int(ROT_W), int(ROT_H))
        assert payload["cell_box_list"][0] == list(table.cell_boxes[0])

    def test_表格格子只转一次且仍落在表块内(self) -> None:
        """格子（表信封）与表块（版面信封）各转一次后仍互相嵌套；转两次必然跑到块外。"""
        table = self._table(_page())
        payload = table_geometry_pass._table_payload(table)
        block = next(block for block in normalize_paddleocr_vl_blocks([_page()]) if block.block_type == "table")
        frame_w, frame_h = payload["image_size"]

        for box in payload["cell_box_list"]:
            cell = {
                "x": box[0] / frame_w,
                "y": box[1] / frame_h,
                "w": (box[2] - box[0]) / frame_w,
                "h": (box[3] - box[1]) / frame_h,
            }
            tol = 0.002
            assert cell["x"] >= block.rect["x"] - tol
            assert cell["y"] >= block.rect["y"] - tol
            assert cell["x"] + cell["w"] <= block.rect["x"] + block.rect["w"] + tol
            assert cell["y"] + cell["h"] <= block.rect["y"] + block.rect["h"] + tol
