"""把「服务端转正帧」的坐标换回「原页帧」的纯数学。

## 为什么需要这一层

PaddleOCR 云端开启整页方向分类（``useDocOrientationClassify``）后会先把页面**转正**
再识别，于是响应里的坐标系整体跟着变：

- ``prunedResult.width`` / ``height`` = **转正帧**尺寸（90/270 时与原页互换；实测 p52：
  转正帧 1753×1240，原图 1240×1753）；
- ``prunedResult.doc_preprocessor_res.angle`` = 服务端把页面**逆时针**转正了多少度；
- ``parsing_res_list`` / ``table_res_list`` / ``overall_ocr_res`` 的坐标**全部在转正帧**。

上游 paddlex 不做回写（``doc_preprocessor/pipeline.py`` 与 ``layout_parsing/pipeline_v2.py``
只把转正后的图交出去，结果坐标系随之改变），所以「页内归一化坐标」必须有且只有**一次**
反变换，且只能发生在坐标离开 OCR 层之前——我们的版面框、表格 cells、前端绿框都画在
原页帧（PDF 渲染出来的那个坐标系），不反变换就会整片横躺。

## 角度约定：θ = 逆时针（实测标定，不是抄公式）

``angle`` 的符号约定响应里没有文档，只能实测钉住。p52 的证据链：

1. 原图（1240×1753、内容躺倒、``/Rotate=0``）人工**顺时针**转 90° 后送 PP-StructureV3，
   得到的 ``doc_title`` [541,339,1215,440] / ``table`` [418,486,1354,1005]，与「开方向
   分类」那次响应的 [542,339,1216,441] / [420,486,1355,1001] 逐像素一致；人工**逆时针**
   转 90° 送检则仍旧是垃圾文本。
2. 所以 ``angle=270`` 对应的正是「顺时针 90°」=「逆时针 270°」，即 ``angle`` 按
   **逆时针为正**（与 ``apps/image_rotation`` 的界面顺时针角符号相反，取值集合相同）。

``tests/ci/unit/pdf_splitting/test_page_rotation.py`` 用两个可自动断言的口径把方向钉死：
反变换后的标题 rect 落在原页**独立检测**到的文本行框内；且该 rect 内的墨迹占比
（0.499）达到随机平移中位数（0.077）的 6 倍以上。方向搞反（θ=90/180）时两条都不成立，
θ=0（不回写）也不成立。

## 归一化坐标的旋转不需要页面长宽比

90/180/270 都是轴对齐旋转，矩形仍是矩形；在归一化坐标里旋转只发生在**单位方格**上
（转 90° 后「除以转正帧宽」与「乘以原页帧高」恰好相消），所以结果与页面是否方形无关。
``derotate_point`` 吃的是**像素**，那里才真的需要转正帧宽高（原页帧宽高 = 二者互换）。
"""

from __future__ import annotations

import math
from typing import Any

#: 方向分类可能给出的直角。
#:
#: 取值集合与 ``apps/image_rotation/services/transform/angles.py`` 的 ``RIGHT_ANGLES``
#: 是同一条约定，但**不能 import 过来**：那个包的 ``__init__`` 会把整套旋转服务
#: （含 ONNX 检测）拉进 import 链，而本模块必须保持「纯数学、无外部副作用」。
#: 两边的差别只在符号语义：那边是界面上的**顺时针**角，这里是响应里的**逆时针**角。
THETAS: tuple[int, ...] = (0, 90, 180, 270)


def normalize_theta(raw: Any) -> int:
    """任意输入 → 0 / 90 / 180 / 270；非直角与脏值一律归 0（``-90`` → ``270``）。

    为什么不抛：angle 是上游模型给的辅助信息，一个脏值不该让一次已付费的识别结果
    作废。θ=0 的语义是「坐标不动」——与关闭方向分类时的行为逐位相同。
    """
    try:
        value = int(raw) % 360
    except (TypeError, ValueError):
        return 0
    return value if value in THETAS else 0


def _require_frame(theta: int, rot_w: float, rot_h: float) -> None:
    """像素反变换必须知道转正帧宽高：缺失/非正时**报错**而不是算出一个假坐标。"""
    if theta == 0:
        return
    if not all(math.isfinite(value) and value > 0 for value in (rot_w, rot_h)):
        raise ValueError(f"页面方向反变换缺少有效帧尺寸: rot_w={rot_w!r}, rot_h={rot_h!r}")


def derotate_point(x: float, y: float, theta: int, *, rot_w: float, rot_h: float) -> tuple[float, float]:
    """转正帧**像素**点 → 原页帧**像素**点（θ = 服务端逆时针转正的角度）。

    原页帧宽高 = 转正帧宽高互换（90/270），所以 ``rot_w`` / ``rot_h`` 在这里是真的要用：
    θ=90 的输出 x 以 ``rot_h`` 为界，θ=270 的输出 y 以 ``rot_w`` 为界。
    """
    theta = normalize_theta(theta)
    _require_frame(theta, rot_w, rot_h)
    if theta == 0:
        return x, y
    if theta == 90:
        return rot_h - y, x
    if theta == 180:
        return rot_w - x, rot_h - y
    return y, rot_w - x


def derotate_rect(rect: dict[str, float], theta: int, *, rot_w: float, rot_h: float) -> dict[str, float]:
    """转正帧**归一化**矩形 ``{"x","y","w","h"}`` → 原页帧归一化矩形。

    实现走「两个角点各自做像素反变换、再除以原页帧宽高」：那样像素↔归一化的互换只在
    ``derotate_point`` 里写一次，不会出现两份互相漂移的公式。返回值**不四舍五入**
    （round-trip 要求误差 < 1e-6，取整会直接破坏它）；取整交给下游的输出边界。
    """
    theta = normalize_theta(theta)
    _require_frame(theta, rot_w, rot_h)
    x, y, w, h = float(rect["x"]), float(rect["y"]), float(rect["w"]), float(rect["h"])
    if theta == 0:
        return {"x": x, "y": y, "w": w, "h": h}
    # 90/270 时原页帧 = 转正帧宽高互换；180 时不变
    orig_w, orig_h = (rot_h, rot_w) if theta in (90, 270) else (rot_w, rot_h)
    ax, ay = derotate_point(x * rot_w, y * rot_h, theta, rot_w=rot_w, rot_h=rot_h)
    bx, by = derotate_point((x + w) * rot_w, (y + h) * rot_h, theta, rot_w=rot_w, rot_h=rot_h)
    return {
        "x": min(ax, bx) / orig_w,
        "y": min(ay, by) / orig_h,
        "w": abs(bx - ax) / orig_w,
        "h": abs(by - ay) / orig_h,
    }


def derotate_pixel_box(
    box: tuple[float, float, float, float] | list[float],
    theta: int,
    *,
    rot_w: float,
    rot_h: float,
) -> tuple[float, float, float, float]:
    """转正帧**像素**框 ``(x0,y0,x1,y1)`` → 原页帧像素框。

    只用于 90° 倍数的旋转，所以结果仍是轴对齐矩形：两个角点各自反变换后取
    ``min``/``max`` 即得（不需要多边形或旋转矩阵）。PP-StructureV3 的
    ``cell_box_list`` / ``rec_boxes`` 走这条。
    """
    theta = normalize_theta(theta)
    x0, y0, x1, y1 = (float(value) for value in box[:4])
    ax, ay = derotate_point(x0, y0, theta, rot_w=rot_w, rot_h=rot_h)
    bx, by = derotate_point(x1, y1, theta, rot_w=rot_w, rot_h=rot_h)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


def rotated_frame_size(theta: int, *, rot_w: float, rot_h: float) -> tuple[float, float]:
    """转正帧尺寸 → 原页帧尺寸（90/270 互换，0/180 不变）。

    像素框反变换之后，紧跟的「像素→页面」换算必须用**原页帧**尺寸当分母，
    否则格子在页面上的比例会整体走形。
    """
    return (rot_h, rot_w) if normalize_theta(theta) in (90, 270) else (rot_w, rot_h)


def page_angle(pruned_result: Any) -> int:
    """从 ``prunedResult`` 读 ``doc_preprocessor_res.angle``；缺字段/脏值 → 0。

    形状知识只写在这里（``doc_preprocessor_res`` 是 PaddleX 的命名，改版时改这一处）；
    ``apps/automation/services/ocr/paddleocr_api_service.py`` 有一份**镜像**解析
    （``parse_page_orientations``）——那边不能 import 本模块：``apps/pdf_splitting``
    的包里全是服务层，反向 import 会绕成环。两处都只是读同一个字段。
    """
    if not isinstance(pruned_result, dict):
        return 0
    preprocessor = pruned_result.get("doc_preprocessor_res")
    if not isinstance(preprocessor, dict):
        return 0
    return normalize_theta(preprocessor.get("angle"))


__all__ = [
    "THETAS",
    "derotate_pixel_box",
    "derotate_point",
    "derotate_rect",
    "normalize_theta",
    "page_angle",
    "rotated_frame_size",
]
