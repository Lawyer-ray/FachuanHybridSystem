"""`/export` 的旋转方向必须与界面一致（2026-11-23 审计 P11-03 回归）。

## 事故形态

`services/facade.py` 把前端传来的**顺时针**角度先写成 `(-rotation) % 360`，再交给
`transform/image_transform.rotate_image_for_output`；而后者内部又调用
`transform/angles.to_pil_angle()` 做「顺时针 → PIL 逆时针」的**唯一**转换
（`angles.py` 文件头明确禁止在别处再转一次）。

两次取反相互抵消 → 顺时针 90° 实际输出成逆时针 90°，`/export` 的 90°/270° 方向与
界面所见相反。这类回归肉眼可见，但历史上没有任何断言检查方向，只断言「返回了 bytes」。

## 本测试的判定方式

在 100x50 的白图**上边中点**画一块红方块，请求顺时针 90°：

- 顺时针（正确）：上边转到右边 → 红块应落在输出图的**右半侧**；
- 逆时针（错误）：上边转到左边 → 红块落在**左半侧**。
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from apps.image_rotation.services.facade import ImageRotationService


def _image_with_top_marker() -> bytes:
    img = Image.new("RGB", (100, 50), (255, 255, 255))
    for x in range(45, 56):
        for y in range(0, 11):
            img.putpixel((x, y), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _red_centroid_x(data: bytes) -> tuple[float, int]:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    width, height = img.size
    xs: list[int] = []
    for x in range(width):
        for y in range(height):
            r, g, b = img.getpixel((x, y))
            if r > 200 and g < 80 and b < 80:
                xs.append(x)
    assert xs, "输出图里找不到红色标记——旋转实现被改坏了"
    return sum(xs) / len(xs), width


@pytest.mark.parametrize(("rotation", "expect_right_side"), [(90, True), (270, False)])
def test_export_respects_clockwise_semantics(rotation: int, expect_right_side: bool) -> None:
    item = {
        "filename": "page1.png",
        "format": "png",
        "rotation": rotation,
        "data": base64.b64encode(_image_with_top_marker()).decode(),
    }
    result = ImageRotationService()._process_single_image(item)
    assert result is not None, "导出应产出 (filename, bytes, format)"
    out = result[1]

    centroid_x, width = _red_centroid_x(out)
    on_right = centroid_x > width / 2
    direction = "顺时针" if expect_right_side else "逆时针"
    assert on_right is expect_right_side, (
        f"请求 {direction} {rotation}° 后，原本在**上边**的标记应落在"
        f"{'右' if expect_right_side else '左'}半侧，实际重心 x={centroid_x:.1f} / 宽 {width}"
    )
