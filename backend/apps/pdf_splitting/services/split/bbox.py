"""版面坐标归一化：把三家后端的 bbox 统一成前端能直接画的 0–1 矩形。

## 为什么要单独一层

三家后端给出的坐标**互不兼容**，而前端 `PageRect` 只认一种：归一化 0–1
（`left: x*100%`）。原样传下去的结果是绿框飘到页外或缩成一点：

| 来源 | 原始格式 | 是否有页面尺寸 |
|---|---|---|
| MinerU | ``[x0, y0, x1, y1]``，**千分比**（页宽高为 1000） | 页面级**不给** width/height |
| Textin | ``[x0, y0, x1, y1]`` 或 ``[[x,y],...]``，**绝对**像素/点 | 给 ``page_width/page_height`` |
| 本地 OCR | 无坐标（逐行文本） | 无 |
| Office | 无像素坐标，只有结构 locator | 无 |

MinerU 是这里最坑的一个：它**不返回页面尺寸**，千分比只能靠"假定 1000"还原，
所以 ``unit="permille"`` 分支不需要页宽高。而 Textin 的绝对坐标**必须**有页
宽高，否则无法换算——这时宁可返回 None（前端就不画框），也不要编一个坐标。

## 输出契约

    {"x": 0..1, "y": 0..1, "w": 0..1, "h": 0..1, "approx": bool}

``approx=True`` 表示"这个框是推出来的、不是原样量出来的"（如 Office 整页框、
缺页面尺寸时按假定尺寸算出来的 MinerU 框）。前端据此决定要不要给律师看绿框：
**宁可少画一个框，也不能画错一个框** —— 错框会让人指着 A 处说 B 处的内容。
"""

from __future__ import annotations

from typing import Any

#: MinerU 的 bbox 坐标基准：页宽高视为 1000
_MinerU_PERMILLE = 1000.0


def _to_floats(raw: Any) -> list[float] | None:
    """把各种形状的坐标转成 [x0, y0, x1, y1]；转不了返回 None。"""
    if not isinstance(raw, (list, tuple)):
        return None
    # [[x,y],[x,y],[x,y],[x,y]] 四点多边形 → 取外接矩形
    if raw and isinstance(raw[0], (list, tuple)):
        xs: list[float] = []
        ys: list[float] = []
        for point in raw:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            try:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
            except (TypeError, ValueError):
                return None
        if not xs or not ys:
            return None
        return [min(xs), min(ys), max(xs), max(ys)]
    if len(raw) < 4:
        return None
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def normalize_bbox(
    bbox: Any,
    *,
    unit: str,
    page_width: Any = None,
    page_height: Any = None,
) -> dict[str, Any] | None:
    """把后端 bbox 归一化为 0–1 矩形。

    Args:
        bbox: 后端原始坐标。
        unit: ``"permille"``（MinerU，坐标除以 1000）或 ``"absolute"``
            （Textin，坐标除以页宽高）。
        page_width / page_height: 页面尺寸，``unit="absolute"`` 时必需。

    Returns:
        ``{"x","y","w","h","approx"}``；无法换算时返回 None（不编造坐标）。
    """
    coords = _to_floats(bbox)
    if coords is None:
        return None
    x0, y0, x1, y1 = coords

    if unit == "permille":
        # MinerU 不给页面尺寸，千分比是它自己约定的 1000 基准
        nx0, ny0 = x0 / _MinerU_PERMILLE, y0 / _MinerU_PERMILLE
        nx1, ny1 = x1 / _MinerU_PERMILLE, y1 / _MinerU_PERMILLE
        approx = False
    elif unit == "absolute":
        try:
            pw = float(page_width)
            ph = float(page_height)
        except (TypeError, ValueError):
            return None
        # 页面尺寸缺失或为零时无法换算：返回 None 让前端不画框，
        # 而不是除出 inf/nan 把整个 SVG 层搞坏
        if pw <= 0 or ph <= 0:
            return None
        nx0, ny0 = x0 / pw, y0 / ph
        nx1, ny1 = x1 / pw, y1 / ph
        approx = False
    elif unit == "normalized":
        nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        approx = False
    else:
        return None

    nx0, nx1 = sorted((nx0, nx1))
    ny0, ny1 = sorted((ny0, ny1))
    nx0, ny0, nx1, ny1 = _clamp01(nx0), _clamp01(ny0), _clamp01(nx1), _clamp01(ny1)
    w, h = nx1 - nx0, ny1 - ny0
    # 退化框（宽或高为 0）没有可视意义，当作"没有坐标"处理
    if w <= 0 or h <= 0:
        return None
    # 保留 4 位小数：除法会把 0.04 算成 0.03999999999999998，直接下发丑陋且
    # 让前端快照测试难写；0.0001 的精度对任何页面都远超一个像素。
    return {
        "x": round(nx0, 4),
        "y": round(ny0, 4),
        "w": round(w, 4),
        "h": round(h, 4),
        "approx": approx,
    }


def resolve_bbox_unit(backend: str | None) -> str:
    """按后端名给出它的 bbox 坐标单位（未知名返回不可用）。"""
    name = str(backend or "").strip().lower()
    if name == "mineru":
        return "permille"
    if name == "textin":
        return "absolute"
    return "unknown"


__all__ = ["normalize_bbox", "resolve_bbox_unit"]
