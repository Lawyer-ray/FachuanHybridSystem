"""bbox 归一化：三家后端坐标 → 前端 0–1 矩形。

这块的错法都很隐蔽（绿框飘到页外 / 缩成一点 / 指向别处），所以重点覆盖
「坐标单位换算」与「算不出来时必须返回 None，而不是编一个框」。
"""

from __future__ import annotations

import pytest

from apps.pdf_splitting.services.split.bbox import normalize_bbox, resolve_bbox_unit


class TestResolveUnit:
    def test_known_backends(self) -> None:
        assert resolve_bbox_unit("mineru") == "permille"
        assert resolve_bbox_unit("textin") == "absolute"

    def test_unknown_backend_is_unknown(self) -> None:
        # 本地 OCR / 未知后端：不给坐标，前端就不画框
        assert resolve_bbox_unit("local") == "unknown"
        assert resolve_bbox_unit(None) == "unknown"
        assert resolve_bbox_unit("") == "unknown"


class TestMineruPermille:
    def test_permille_needs_no_page_size(self) -> None:
        # MinerU 从不返回页面尺寸，千分比按 1000 基准直接换算
        rect = normalize_bbox([100, 200, 600, 400], unit="permille")
        assert rect is not None
        assert rect["x"] == pytest.approx(0.1)
        assert rect["y"] == pytest.approx(0.2)
        assert rect["w"] == pytest.approx(0.5)
        assert rect["h"] == pytest.approx(0.2)

    def test_full_page(self) -> None:
        rect = normalize_bbox([0, 0, 1000, 1000], unit="permille")
        assert rect is not None
        assert (rect["x"], rect["y"], rect["w"], rect["h"]) == (0.0, 0.0, 1.0, 1.0)

    def test_out_of_range_is_clamped(self) -> None:
        # 后端偶尔给出越界值（识别到了页边外），夹紧而不是让绿框跑到页面外
        rect = normalize_bbox([-50, -20, 1200, 1100], unit="permille")
        assert rect is not None
        assert (rect["x"], rect["y"], rect["w"], rect["h"]) == (0.0, 0.0, 1.0, 1.0)


class TestTextinAbsolute:
    def test_absolute_uses_page_size(self) -> None:
        rect = normalize_bbox([100, 200, 300, 400], unit="absolute", page_width=1000, page_height=1000)
        assert rect is not None
        assert rect["x"] == pytest.approx(0.1)
        assert rect["y"] == pytest.approx(0.2)
        assert rect["w"] == pytest.approx(0.2)
        assert rect["h"] == pytest.approx(0.2)

    def test_missing_page_size_returns_none(self) -> None:
        # 关键：没有页面尺寸就算不出来。返回 None 让前端不画框，
        # 绝不编一个坐标（错框比没框更糟——会让人指着 A 说 B）
        assert normalize_bbox([10, 20, 30, 40], unit="absolute") is None
        assert normalize_bbox([10, 20, 30, 40], unit="absolute", page_width=0, page_height=800) is None
        assert normalize_bbox([10, 20, 30, 40], unit="absolute", page_width=None, page_height=800) is None

    def test_quad_points_converted_to_bounding_box(self) -> None:
        # Textin 有时给四点四边形，取外接矩形
        rect = normalize_bbox(
            [[100, 100], [300, 110], [300, 210], [100, 200]],
            unit="absolute",
            page_width=1000,
            page_height=1000,
        )
        assert rect is not None
        assert rect["x"] == pytest.approx(0.1)
        assert rect["y"] == pytest.approx(0.1)
        assert rect["w"] == pytest.approx(0.2)
        assert rect["h"] == pytest.approx(0.11)


class TestDegenerateInput:
    @pytest.mark.parametrize("bad", [None, [], [1, 2], "abc", {"x": 1}, [1, 2, "a", 4]])
    def test_unusable_input_returns_none(self, bad: object) -> None:
        assert normalize_bbox(bad, unit="permille") is None

    def test_zero_area_box_returns_none(self) -> None:
        # 宽或高为 0 的框画出来是一条线，没有定位意义
        assert normalize_bbox([100, 200, 100, 400], unit="permille") is None
        assert normalize_bbox([100, 200, 300, 200], unit="permille") is None

    def test_reversed_coords_are_sorted(self) -> None:
        # 少数后端给的是右下-左上顺序，排序后再算，别算出负宽
        rect = normalize_bbox([600, 400, 100, 200], unit="permille")
        assert rect is not None
        assert rect["x"] == pytest.approx(0.1)
        assert rect["y"] == pytest.approx(0.2)
        assert rect["w"] == pytest.approx(0.5)
        assert rect["h"] == pytest.approx(0.2)

    def test_normalized_passthrough(self) -> None:
        rect = normalize_bbox([0.1, 0.2, 0.6, 0.4], unit="normalized")
        assert rect is not None
        assert rect["w"] == pytest.approx(0.5)

    def test_unknown_unit_returns_none(self) -> None:
        assert normalize_bbox([1, 2, 3, 4], unit="furlongs") is None

    def test_approx_flag_false_for_real_coords(self) -> None:
        # 原样量出来的坐标：approx=False（区别于 Office 那种整页近似框）。
        # 两个单位各给一个在该单位下**非退化**的框——归一化下 [10,10,20,20]
        # 早已越过 1.0 被夹成整页，而千分比下同一组数只有 1% 见方。
        assert normalize_bbox([100, 100, 600, 400], unit="permille")["approx"] is False  # type: ignore[index]
        assert normalize_bbox([0.1, 0.1, 0.6, 0.4], unit="normalized")["approx"] is False  # type: ignore[index]
