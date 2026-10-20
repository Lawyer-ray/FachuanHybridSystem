"""旋转角度语义的唯一归一点。

两套符号约定在此交汇，必须显式转换，不能把数值直接递给 PIL：

- 界面侧（canvas ``ctx.rotate`` / CSS ``rotate()``）与 ONNX 检测输出：**顺时针为正**，
  且 ONNX 会给出 ``-90`` / ``-270``，手动累加也可能越过 360。
- ``PIL.Image.rotate(angle)``：**逆时针为正**。

2026-10-20 之前三处消费点都写成 ``if rotation not in (0, 90, 180, 270): rotation = 0``
再 ``img.rotate(rotation)``：``-90`` 被当非法值静默归零（不转），``90`` / ``270`` 则按 PIL 语义反向转。
"""

from __future__ import annotations

RIGHT_ANGLES: tuple[int, ...] = (0, 90, 180, 270)


def normalize_rotation(rotation: int | float | str | None) -> int:
    """任意输入 → 0 / 90 / 180 / 270（顺时针）。非直角、非法值归零。"""
    if rotation is None:
        return 0
    try:
        value = int(rotation) % 360
    except (TypeError, ValueError):
        return 0
    return value if value in RIGHT_ANGLES else 0


def to_pil_angle(rotation: int | float | str | None) -> int:
    """顺时针界面角度 → ``PIL.Image.rotate`` 需要的逆时针角度。"""
    return (-normalize_rotation(rotation)) % 360
