"""旋转角度语义回归（2026-10-20 事故）。

界面（canvas ``ctx.rotate`` / CSS ``rotate()``）与 ONNX 检测输出以**顺时针为正**，
ONNX 会给出 ``-90`` / ``-270``；``PIL.Image.rotate`` 以**逆时针为正**。
历史记录导出此前把 ``-90`` 当非法值归零（不转）、``90``/``270`` 按 PIL 语义反向转，
导出的证据材料方向与页面所见不一致。本文件把「UI 顺时针」这一契约钉死在角落红块上。
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from apps.image_rotation.services.facade import ImageRotationService
from apps.image_rotation.services.transform import (
    apply_rotation_for_pdf,
    normalize_rotation,
    rotate_image_for_output,
    to_pil_angle,
)


def _marked_image(fmt: str = "PNG") -> bytes:
    """200×100 白底、左上角 40×40 红块——用角落位置判定旋转方向。"""
    img = Image.new("RGB", (200, 100), "white")
    img.paste((255, 0, 0), (0, 0, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _red_corner(data: bytes) -> str:
    """返回红块所在角落；顺时针 90° 时左上角红块应到右上角。"""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    corners = {"TL": (5, 5), "TR": (w - 6, 5), "BL": (5, h - 6), "BR": (w - 6, h - 6)}
    hits = [k for k, p in corners.items() if img.getpixel(p)[0] > 200 and img.getpixel(p)[1] < 80]
    assert len(hits) == 1, f"红块应恰在一个角落，实际命中 {hits}"
    return hits[0]


# ── 归一化 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0),
        (90, 90),
        (180, 180),
        (270, 270),
        (-90, 270),
        (-270, 90),
        (360, 0),
        (450, 90),
        (-180, 180),
        (45, 0),  # 非直角归零（维持旧防线）
        ("90", 90),
        ("-90", 270),  # 表单取出的字符串
        (None, 0),
        ("abc", 0),
    ],
)
def test_normalize_rotation(raw: object, expected: int) -> None:
    assert normalize_rotation(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("ui", "pil"),
    [(0, 0), (90, 270), (180, 180), (270, 90), (-90, 90), (-270, 270)],
)
def test_to_pil_angle_converts_clockwise_to_counterclockwise(ui: int, pil: int) -> None:
    assert to_pil_angle(ui) == pil


# ── 方向契约：红块角落 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("rotation", "size", "corner"),
    [
        (0, (200, 100), "TL"),
        (90, (100, 200), "TR"),  # 界面顺时针 90：左上 → 右上
        (180, (200, 100), "BR"),
        (270, (100, 200), "BL"),  # 270 ≡ 逆时针 90：左上 → 左下
        (-90, (100, 200), "BL"),  # ONNX 负角度必须被接受，等价 270
        (-270, (100, 200), "TR"),  # 等价 90
        (450, (100, 200), "TR"),  # 越过 360
    ],
)
def test_rotate_image_for_output_follows_ui_clockwise(rotation: int, size: tuple[int, int], corner: str) -> None:
    out = rotate_image_for_output(_marked_image(), rotation=rotation, img_format="png")
    assert Image.open(io.BytesIO(out)).size == size
    assert _red_corner(out) == corner


@pytest.mark.parametrize(
    ("rotation", "size", "corner"),
    [
        (0, (200, 100), "TL"),
        (90, (100, 200), "TR"),
        (270, (100, 200), "BL"),
        (-90, (100, 200), "BL"),
    ],
)
def test_apply_rotation_for_pdf_follows_ui_clockwise(rotation: int, size: tuple[int, int], corner: str) -> None:
    out = apply_rotation_for_pdf(_marked_image("JPEG"), rotation)
    assert Image.open(io.BytesIO(out)).size == size
    assert _red_corner(out) == corner


# ── facade 入口：-90 不再被静默归零 ───────────────────────────────────────────


def test_process_page_for_pdf_keeps_negative_onnx_rotation() -> None:
    service = ImageRotationService()
    page = {"data": base64.b64encode(_marked_image()).decode(), "rotation": -90}

    processed = service._process_page_for_pdf(page)

    assert processed is not None
    _image_bytes, rotation = processed
    assert rotation == 270
