"""字段级裁块核验：把「页图 + 千分比 bbox + 候选值」变成一张可判定的裁块。

## 这一层为什么存在

判定器（``disagreement_judge.judge_candidates``）只看一张图，给的 ``p`` 是「图里的字 ==
这个候选值」的概率。实测（2026-11-25，同一张身份证块、同一个 18 位号码）：

- 只送号码 ``110101198001011234`` → ``p = 0.0011``；
- 连图上的前缀词 ``公民身份号码 110101198001011234`` → ``p = 0.3892``。

**同一个裁块、同一个字段，只差候选怎么取，p 差 350 倍。** 于是本层只做两件事：

1. 把 bbox 裁成**不多不少**那一块（裁宽了就带进相邻字，带进去一个词，p 一样掉回噪声区）；
2. 把「候选必须与裁块同域」这条纪律钉在调用方读得到的位置（见 ``verify_field`` 与
   ``candidates_from_block`` 的 docstring）。

**本层不替调用方补前缀。** 补什么前缀是业务语义（「公民身份号码」还是「身份证号」），
猜错了比不补更危险：p 会从噪声区一路涨到看着可信，而人无从发现那是猜出来的。

## 只收千分比，不收像素

``bbox_milli`` 是千分比四点 ``[x0, y0, x1, y1]``（页宽/页高各视作 1000）：MinerU、
DeepSeek rich 标记、PaddleOCR-VL 的版面都出这一种。后端不变量是「一份文档只有一个 bbox
量纲」（``bbox.resolve_bbox_unit``），所以坐标越出千分比量级时**拒掉**（``PERMILLE_LIMIT``），
不去猜它是不是像素——量纲混用在仓库里出过事故（``dual_engine`` 模块头的「整层框全空/全错位」）。

## 为什么不自动上采样

正文 200dpi 实测已够（判定 0.946/0.996），拉到 400dpi 不掉分：**分辨率不是瓶颈，同域才是。**
所以 ``upscale`` 默认 1.0。放大只多传字节、更慢，还会让裁块尺寸与原图坐标对不上，
人工抽屉里那个框就画不准了。
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageStat

from .disagreement_judge import DOMAIN_TEXT, judge_candidates

#: 千分比坐标的量纲上界（含合理越界余量）。千分比的理论上界是 1000，引擎偶尔给出
#: 轻微越界值（1003 之类），那些交给 clamp 兜；而绝对像素框在 200dpi 渲染下宽高都远超
#: 2000（``dual_engine._MINERU_ABSOLUTE_PIXEL_FLOOR`` 的实测口径）。落在门槛之内的像素框
#: 认不出来——那意味着整块挤在页面左上角，本就该由调用方先收敛量纲，本层不猜。
PERMILLE_LIMIT = 2000.0

#: 千分比的进制：页宽/页高各视作多少个单位。
_PERMILLE = 1000.0

#: 块的最小边长（px）。印刷体最小的字符笔画也要 8px 上下，2px 以下只可能是「坐标塌了」，
#: 送去判定只会得到「图里没有字」，白花一次请求（``bad_bbox``）。
MIN_BLOCK_PX = 2

#: 裁块判为「纯白」的亮度下限（0–255）：所有像素都 ≥ 250。不按 255 判是因为扫描件空白区
#: 带 JPEG 噪点（实测 250–254），按 255 判会把真空白判成「有内容」；250 仍能拦住任何一笔墨迹。
CROP_WHITE_MIN_LUMA = 250

#: 裁块判为「纯黑」的亮度上限：所有像素都 ≤ 5。整块遮黑、或裁块落在页外补出来的黑边都是这种。
CROP_BLACK_MAX_LUMA = 5


@dataclass(frozen=True)
class FieldVerification:
    """一次字段核验的结果（含**实际送出去的那张图**，人工抽屉照它显示）。"""

    #: ``"accept"`` / ``"human"``，与 ``Judgement.decision`` 同一口径。
    decision: str
    #: 被采纳的候选原文；未采纳时为 None。
    winner: str | None
    #: ``Judgement.reason`` 原样透传；本层自己拒绝时为 ``"bad_bbox"`` / ``"crop_empty"``。
    reason: str
    #: 送进判定器的那张 PNG（供人工抽屉展示）。``bad_bbox`` 时没有图，为 None；
    #: ``crop_empty`` 时照给——人工要能看见「这块是白的」，才判得下去这单。
    crop_bytes: bytes | None
    #: 裁块在**页图像素**坐标系里的矩形（左上右下），未乘 ``upscale``：抽屉要画的是页面上的位置。
    crop_bbox_px: tuple[int, int, int, int] | None
    #: 原样保留的 ``Judgement``；本层自己拒绝时为 None。
    judgement: Any | None


def verify_field(
    page_image: bytes,
    bbox_milli: Sequence[float],
    candidates: Sequence[str],
    *,
    domain: str = DOMAIN_TEXT,
    pad_ratio: float = 0.25,
    upscale: float = 1.0,
) -> FieldVerification:
    """裁出 bbox 那一块，连同候选值一起送判定。

    Args:
        page_image: 整页图（PNG/JPEG…）的**原始字节**，200dpi 渲染即可，不需要为「读更清」调高。
        bbox_milli: **千分比**四点 ``[x0, y0, x1, y1]``。绝对像素坐标不接受（见模块头）。
        candidates: 候选文本。**必须取自同一裁块范围内的文本**：要连图里印的前缀词一起送
            （``公民身份号码 110101198001011234``），只截号码或数字会让 p 掉进噪声区
            （实测 0.3892 → 0.0011）。本层不改写它，也不替你补前缀。
        domain: 传给判定器的文档域，默认 ``DOMAIN_TEXT``。证件类由判定器按域拒绝，本层不管。
        pad_ratio: 内边距 = ``pad_ratio × 块高``，上下左右各外扩一份。太小会切掉相邻字
            （切掉的字正是「同域」要保住的那部分），再夹回页内。
        upscale: 裁块放大倍数，默认 1.0（不放大，理由见模块头）。

    Returns:
        ``FieldVerification``；``decision``/``winner``/``reason`` 来自判定器，
        或本层两种「不用问」的情形：``bad_bbox``（框不可用）与 ``crop_empty``（裁块没墨迹）。
        这两种都**不发请求**。

    Raises:
        ValueError: ``pad_ratio`` 为负或 ``upscale`` 非正——调用方写错了参数，不猜它想要什么。
    """
    if pad_ratio < 0:
        raise ValueError(f"pad_ratio 不能为负（内边距只会外扩）：{pad_ratio}")
    if upscale <= 0:
        raise ValueError(f"upscale 必须为正：{upscale}")

    with Image.open(io.BytesIO(page_image)) as page:
        page.load()
        block_px = _block_rect_px(bbox_milli, page.size)
        if block_px is None:
            return _bad_bbox()
        crop_px = _crop_rect_px(block_px, page.size, pad_ratio)
        if crop_px is None:
            # 框整块落在页外：夹回页内什么都不剩，同样是「坐标坏了」而不是「这块是空的」
            return _bad_bbox()
        crop = _scaled(page.crop(crop_px), upscale)
        crop_png = _png_bytes(crop)
        if _is_blank(crop):
            return FieldVerification(
                decision="human",
                winner=None,
                reason="crop_empty",
                crop_bytes=crop_png,
                crop_bbox_px=crop_px,
                judgement=None,
            )

    judgement = judge_candidates(crop_png, list(candidates), domain=domain)
    return FieldVerification(
        decision=judgement.decision,
        winner=judgement.winner,
        reason=judgement.reason,
        crop_bytes=crop_png,
        crop_bbox_px=crop_px,
        judgement=judgement,
    )


def candidates_from_block(block_text: str, fields: Sequence[str]) -> list[str]:
    """块文本 + 其中出现过的字段值 → 候选列表（块文本**永远排第一**，去重保序）。

    这是「同域」纪律的工具化：候选必须是**这一块图里印着的那些字**。块文本本身就是那块图
    的全部内容，所以它永远第一；``fields`` 只有在块文本里**真的出现过**才追加——没出现说明
    这块不是那一段，塞进去等于拿 A 处的图判 B 处的值，p 必然掉进噪声区。

    用法（调用方据此把候选喂给 ``verify_field``）：

    ```python
    block = "公民身份号码 110101198001011234"
    candidates = candidates_from_block(block, ["110101198001011234", "张三"])
    # → ["公民身份号码 110101198001011234", "110101198001011234"]（"张三" 不在这块里，不收）
    ```

    空块文本返回空列表：没有文字就没有可判定的候选（空串当候选只会让判定器空跑一次）。
    """
    block = block_text.strip()
    if not block:
        return []
    candidates = [block]
    for field in fields:
        value = field.strip()
        if not value or value in candidates or value not in block:
            continue
        candidates.append(value)
    return candidates


def _bad_bbox() -> FieldVerification:
    """框不可用：没有裁块、没有判定，直接进人工。"""
    return FieldVerification(
        decision="human",
        winner=None,
        reason="bad_bbox",
        crop_bytes=None,
        crop_bbox_px=None,
        judgement=None,
    )


def _block_rect_px(bbox_milli: Sequence[float], page_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    """千分比四点 → 页图像素矩形；不是可用的千分比框时返回 None。

    ``px = milli / 1000 × 页边长``——x 除以页宽、y 除以页高，两者各自的基准边长不同，
    拿短边或对角线当公分母就会把框压扁。
    """
    if len(bbox_milli) < 4:
        return None
    try:
        x0, y0, x1, y1 = (float(value) for value in bbox_milli[:4])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)):
        return None
    # 坐标量级越出千分比 → 只可能是像素或其他单位，不猜（量纲混用会得到「看着像真的错框」）
    if max(abs(value) for value in (x0, y0, x1, y1)) > PERMILLE_LIMIT:
        return None
    # 反向框不是「左右对调就能用」：x1 < x0 说明读到的是两个不同块的坐标，排序只会伪造一个框
    if x1 <= x0 or y1 <= y0:
        return None

    page_width, page_height = page_size
    left = round(x0 / _PERMILLE * page_width)
    top = round(y0 / _PERMILLE * page_height)
    right = round(x1 / _PERMILLE * page_width)
    bottom = round(y1 / _PERMILLE * page_height)
    if right - left <= MIN_BLOCK_PX or bottom - top <= MIN_BLOCK_PX:
        return None
    return (left, top, right, bottom)


def _crop_rect_px(
    block_px: tuple[int, int, int, int],
    page_size: tuple[int, int],
    pad_ratio: float,
) -> tuple[int, int, int, int] | None:
    """块矩形四边各外扩 ``pad_ratio × 块高``，再夹回页内；夹完什么都不剩时返回 None。

    **必须自己夹**：``Image.crop`` 遇到越界矩形不报错，而是把界外部分补成黑/透明——
    补出来的黑边在判定器眼里就是「图上有一块内容」，于是「框画到页外」这种坐标错误
    会伪装成一次正常的字段核验。
    """
    left, top, right, bottom = block_px
    page_width, page_height = page_size
    pad = pad_ratio * (bottom - top)
    crop_left = max(0, round(left - pad))
    crop_top = max(0, round(top - pad))
    crop_right = min(page_width, round(right + pad))
    crop_bottom = min(page_height, round(bottom + pad))
    if crop_right <= crop_left or crop_bottom <= crop_top:
        return None
    return (crop_left, crop_top, crop_right, crop_bottom)


def _scaled(crop: Image.Image, upscale: float) -> Image.Image:
    """按 ``upscale`` 缩放裁块；1.0 原样返回（本层不自动放大）。"""
    if upscale == 1.0:
        return crop
    width, height = crop.size
    return crop.resize((max(1, round(width * upscale)), max(1, round(height * upscale))), Image.Resampling.LANCZOS)


def _is_blank(crop: Image.Image) -> bool:
    """裁块是不是「没有墨」：纯白或纯黑（阈值见 ``CROP_*_LUMA``）。

    用**灰度**极值判，不看均值：一块白底上只有一行细字，均值仍然接近白，而极值会被那行字
    拉到 0——这正是要区分的「有内容」。
    """
    low, high = ImageStat.Stat(crop.convert("L")).extrema[0]
    return high <= CROP_BLACK_MAX_LUMA or low >= CROP_WHITE_MIN_LUMA


def _png_bytes(image: Image.Image) -> bytes:
    """裁块 → PNG 字节（判定器与人工抽屉吃同一份字节）。"""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


__all__ = [
    "CROP_BLACK_MAX_LUMA",
    "CROP_WHITE_MIN_LUMA",
    "MIN_BLOCK_PX",
    "PERMILLE_LIMIT",
    "FieldVerification",
    "candidates_from_block",
    "verify_field",
]
