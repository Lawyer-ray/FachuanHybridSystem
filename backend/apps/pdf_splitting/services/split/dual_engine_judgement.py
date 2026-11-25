"""把双引擎分歧接到打分裁定器：分歧 → 裁块 → 判定 → 附注。

## 为什么接线点在这里

``dual_engine_runner.run_dual_engine`` 是**唯一同时具备三样东西**的地方：

1. 两个引擎对**同一处**文字的两种读法（``EngineDisagreement.variants``，含全文）；
2. 每种读法在原页上的**归一化矩形**（``link_disagreement_to_blocks`` 算出来的两侧框）；
3. 原 PDF（``source``，分歧的 ``page_no`` 已经是**原卷页码**，不是切片页码）。

少任何一样都判不了：没有两种读法就没有分歧；没有框就只能整页送去判（整页送等于让
判定器自己找位置，那是「再识别一次」，正是 §8.4 否掉盲读 VLM 的理由）；没有原页就裁不出块。

## 三条硬约束（都来自实测，见简报 §11）

1. **候选必须与裁块同域。** 同一张身份证块，只送号码 ``p=0.0011``，带上图里的前缀词
   ``p=0.3892``（350 倍）。所以候选直接取变体全文 ``EngineVariant.body``——它本来就是
   「这一行的完整读法」，与框覆盖的范围天然同域。
2. **证件/账号类不送。** 可读分辨率下必被 ``content_policy_violation`` 拒；这类字段的
   正确性靠 L1 校验位（Mod-11 / Mod-31 / Luhn），不靠模型打分。
3. **框必须是同一行。** 两侧框若在竖直方向明显不重叠（一个在上行、一个在下行），并集
   会横跨两行，裁块里就多了不该有的字 —— 宁可不判。

## 旋转换算

``EngineBlock.rect`` 是**该引擎看到的页图**里的归一化坐标。PaddleOCR-VL 会为了识别把
页转正（``engine_page_angles[vl][页]``，逆时针为正）；这种页上 VL 报的框在**转正后的
坐标系**里，直接拿去裁原图会错位。所以按「用哪个引擎的框，就把渲染图转同样的角度」
来对齐，两侧角度不同则放弃判定（``angle_mismatch``）而不是硬裁一个错位的块。

## 产物

返回 ``{disagreement_key: 附注 dict}``，由 ``disagreements_to_dicts`` 挂在每条分歧的
``judge`` 键下。**不删除任何分歧**：判成 accept 的也照样留在列表里，只是多一个
「已自动裁定 + 分数」的标记。理由——把一条律师本来要看的分歧悄悄从列表里拿掉，
等于替他拍板且他不自知；这与 ``boundary_disagreement``「只提示、交人裁定」是同一条纪律。
"""

from __future__ import annotations

import io
import logging
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import Image

from .disagreement_judge import BLOCKED_DOMAINS, DOMAIN_TEXT, is_enabled
from .dual_engine import EngineDisagreement, disagreement_key
from .field_verification import verify_field

logger = logging.getLogger("apps.pdf_splitting")

#: 裁块渲染的 dpi。实测正文 200dpi 已够（判定 0.946 / 0.996），400dpi 不掉分；
#: 提高 dpi 只增加渲染与上传开销，不会让判定更准。
JUDGE_RENDER_DPI = 200

#: 单次双引擎任务最多判多少条分歧。60 条 ≈ 120 次打分调用（每条两候选），
#: 2 并发 × 中位 1.2s ≈ 1.5 分钟内完成；超出的条目原样留人工，只记一条 warning。
MAX_JUDGED_DISAGREEMENTS = 60

#: 两侧框在竖直方向的重叠比例下限。低于它说明两个框压根不是同一行（并集会把两行
#: 都裁进来，候选文本就对不上了），此时宁可不判。
MIN_VERTICAL_OVERLAP = 0.3

#: 单条候选的字符上界。实测判定器在**单行**裁块上给 0.946–0.996（案号 / 金额），
#: 但在**多行块**上清一色落到 prob_low（真实卷宗的抵押登记表实测 3/3）——多行裁块里
#: 夹着表格线、印章、相邻字段，模型没法给出「这段字就是这张图」的高概率。
#: 超过这个长度的候选必然是整段/整块，判了也是白花两次调用，所以提前判「不适用」。
MAX_JUDGEABLE_CHARS = 200

#: 两侧候选长度比的上界。差 4 倍以上说明两个引擎压根没切到同一处（一个是一行、
#: 一个是整段），这种「分歧」不是同一处的两种读法，判不出有意义的结论。
MAX_CANDIDATE_LENGTH_RATIO = 4.0

#: 两侧框的高度比上界。同一行的高度必然接近；差 2.5 倍以上说明一个框住一行、
#: 另一个框住两行（实测抵押登记表就是这么配错的），并集裁块与两侧候选都不同域。
MAX_BOX_HEIGHT_RATIO = 2.5

#: 归一化矩形允许的轻微越界（引擎偶尔给出 1.003 之类的值）。
_RECT_EPSILON = 0.02

#: 身份证：18 位，出生日期段合法。只用来**识别域**（决定要不要送判定），
#: 真正的校验位判定在 L1 闸门里做，这里不重复实现。
_ID_CARD_RE = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
#: 统一社会信用代码：18 位数字 + 大写字母（不含 I O Z S V）。
_USCC_RE = re.compile(r"(?<![0-9A-Z])[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Z])")
#: 银行卡/账号：16–19 位纯数字（前面通常带「账号/卡号/账户」锚点）。
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
_ACCOUNT_ANCHORS = ("账号", "帐号", "卡号", "账户", "帐户", "开户")

#: 判定的附注里保留的分数字段（其余一律不落盘）。
_SCORE_FIELDS = ("verdict", "prob_yes")

#: 渲染/裁块阶段**可预期**的失败：问题在源文件或坐标，不在判定器。
_CROP_ERRORS = (OSError, ValueError, RuntimeError, fitz.FileDataError)

#: 编排层兜底用的异常族（判定整体失败时双引擎任务仍要能出结果）。
_JUDGE_ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError)


@dataclass(frozen=True)
class _Crop:
    """一处分歧的裁块原料：框（千分比）+ 该框所在坐标系的旋转角。"""

    bbox_milli: list[float]
    angle: int
    source: str


def infer_domain(text: str) -> str:
    """从文本形态推断字段域，只为决定「要不要送判定」。

    刻意**保守**：只有能确定是证件/账号类的才拦（拦错了只是少一条自动裁定，人还得看），
    其余一律落 ``text``。案号（``（20XX）粤01民初某某号``）必须是 ``text`` —— 它不含
    16 位以上连续数字、也不匹配 USCC 字符集，所以自然落空。

    Args:
        text: 候选文本（通常是两引擎读法拼起来的上下文）。

    Returns:
        ``id_card`` / ``uscc`` / ``bank_card`` / ``account_no`` / ``text``。
    """
    value = str(text or "")
    if _ID_CARD_RE.search(value):
        return "id_card"
    if _USCC_RE.search(value):
        return "uscc"
    if _LONG_DIGITS_RE.search(value):
        return "account_no" if any(anchor in value for anchor in _ACCOUNT_ANCHORS) else "bank_card"
    return DOMAIN_TEXT


def _rect_of(block: Mapping[str, Any]) -> list[float] | None:
    """``engine_block_to_dict`` 的 ``rect``（归一化 0–1）→ 千分比四点；不可信用返回 None。"""
    if bool(block.get("approx")):
        # 近似推出来的框（缺页面尺寸时）不许拿来裁图：宁可少判一条，也不能裁错位置。
        return None
    rect = block.get("rect") or {}
    try:
        x = float(rect["x"])
        y = float(rect["y"])
        w = float(rect["w"])
        h = float(rect["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    x0, y0 = x, y
    x1, y1 = x + w, y + h
    if x0 < -_RECT_EPSILON or y0 < -_RECT_EPSILON or x1 > 1 + _RECT_EPSILON or y1 > 1 + _RECT_EPSILON:
        return None
    return [x0 * 1000.0, y0 * 1000.0, x1 * 1000.0, y1 * 1000.0]


def _vertical_overlap(left: Sequence[float], right: Sequence[float]) -> float:
    """两个千分比矩形在竖直方向的重叠比例（相对较矮的那个）。"""
    left_h = left[3] - left[1]
    right_h = right[3] - right[1]
    shorter = min(left_h, right_h)
    if shorter <= 0:
        return 0.0
    overlap = min(left[3], right[3]) - max(left[1], right[1])
    return max(0.0, overlap) / shorter


def _build_crop(
    blocks: Sequence[Mapping[str, Any]],
    page_angles: Mapping[str, Mapping[int, int]],
    page_no: int,
) -> _Crop | None:
    """把两侧框合成一个裁块框；不可信时返回 None。

    取**并集**而不是交集：交集可能把一个数字切掉一半，那比多带一点边距严重得多
    （实测「候选与裁块不同域」会让分数掉 350 倍，而多带边距只是让模型多看到几个字）。
    """
    usable: list[tuple[str, list[float]]] = []
    for block in blocks:
        rect = _rect_of(block)
        if rect is not None:
            usable.append((str(block.get("engine") or ""), rect))
    if not usable:
        return None

    angles = {int(page_angles.get(engine, {}).get(page_no, 0) or 0) for engine, _rect in usable}
    if len(angles) > 1:
        # 两个引擎对同一页报的角度不同：说明它们看到的坐标系不是同一个，硬裁必错位。
        return None
    angle = angles.pop()

    union = [
        min(rect[0] for _engine, rect in usable),
        min(rect[1] for _engine, rect in usable),
        max(rect[2] for _engine, rect in usable),
        max(rect[3] for _engine, rect in usable),
    ]
    if len(usable) > 1:
        first, second = usable[0][1], usable[1][1]
        if _vertical_overlap(first, second) < MIN_VERTICAL_OVERLAP:
            # 一个在上行、一个在下行：并集横跨两行，候选文本必然与裁块不同域。
            return None
        heights = sorted((first[3] - first[1], second[3] - second[1]))
        if heights[0] > 0 and heights[1] / heights[0] > MAX_BOX_HEIGHT_RATIO:
            # 一行 vs 两行：粒度都对不上，并集裁块与两侧候选都不在一个域里。
            return None
    return _Crop(bbox_milli=union, angle=angle, source="+".join(engine or "?" for engine, _rect in usable))


def _render_page(pdf_path: Path, page_no: int, dpi: int, angle: int) -> bytes:
    """渲染整页为 PNG；``angle`` 非 0 时按同角度旋转，与本引擎的坐标系对齐。"""
    with fitz.open(pdf_path.as_posix()) as doc:
        if page_no < 1 or page_no > doc.page_count:
            raise ValueError(f"页号越界: {page_no}/{doc.page_count}")
        pix = doc[page_no - 1].get_pixmap(dpi=dpi)
        payload = pix.tobytes("png")
    if not angle:
        return payload
    # 引擎为识别把页**逆时针**转了 angle 度，它的框就在那个朝向里；我们照做一遍即可对齐。
    with Image.open(io.BytesIO(payload)) as image:
        rotated = image.rotate(angle % 360, expand=True)
        out = io.BytesIO()
        rotated.save(out, format="PNG")
        return out.getvalue()


def judge_disagreements(
    *,
    pdf_path: Path | str,
    disagreements: Sequence[EngineDisagreement],
    blocks_by_disagreement: Mapping[tuple[int, str, str], Sequence[Mapping[str, Any]]],
    page_angles: Mapping[str, Mapping[int, int]] | None = None,
    dpi: int = JUDGE_RENDER_DPI,
    max_judged: int = MAX_JUDGED_DISAGREEMENTS,
) -> dict[tuple[int, str, str], dict[str, Any]]:
    """对每条分歧跑一次判定，返回 ``{disagreement_key: 附注}``。

    关闭 / 没有可判条目时返回空 dict —— 此时**连一页都不渲染**（``is_enabled`` 前置短路）。

    Args:
        pdf_path: 原 PDF（分歧的 ``page_no`` 是原卷页码）。
        disagreements: ``compare_pages`` 的产物。
        blocks_by_disagreement: ``{disagreement_key: [两侧块 dict]}``，来自 runner。
        page_angles: ``{引擎: {页号: 角度}}``，来自 runner 的 ``engine_page_angles``。
        dpi: 裁块渲染精度。
        max_judged: 本次最多判多少条（成本闸门）。

    Returns:
        每条被处理过的分歧一条附注；带 ``decision`` / ``reason`` / ``domain`` / ``ratio`` /
        ``scores``（只留 verdict 与概率）/ ``latency_ms`` / ``bbox_source``。
    """
    if not disagreements or not is_enabled():
        return {}

    angles = page_angles or {}
    # 同一页只渲染一次：一份卷宗的分歧高度集中在少数几页（实测表格/流水页最密）。
    page_cache: dict[tuple[int, int], bytes] = {}
    annotations: dict[tuple[int, str, str], dict[str, Any]] = {}
    judged = 0
    started = time.monotonic()

    for item in disagreements:
        if judged >= max_judged:
            logger.warning(
                "pdf_split_judge_budget_exhausted",
                extra={"judged": judged, "total": len(disagreements), "max_judged": max_judged},
            )
            break
        key = disagreement_key(item)
        candidates = _candidates_of(item)
        if len(candidates) < 2:
            continue
        skip_reason = _skip_reason(candidates)
        if skip_reason is not None:
            annotations[key] = _annotation(
                decision="human",
                winner=None,
                reason=skip_reason,
                domain=infer_domain(" ".join(candidates)),
                ratio=None,
                scores=[],
                latency_ms=0.0,
                bbox_source="none",
            )
            continue

        domain = infer_domain(" ".join(candidates))
        if domain in BLOCKED_DOMAINS:
            # 证件/账号类：一次请求都不发，也一次都不渲染。留个附注说明「为什么这条没判」，
            # 否则前端看到「没有 judge 字段」无从区分「不适用」与「判失败了」。
            annotations[key] = _annotation(
                decision="human",
                winner=None,
                reason="domain_blocked",
                domain=domain,
                ratio=None,
                scores=[],
                latency_ms=0.0,
                bbox_source="none",
            )
            continue

        crop = _build_crop(blocks_by_disagreement.get(key, ()), angles, item.page_no)
        if crop is None:
            annotations[key] = _annotation(
                decision="human",
                winner=None,
                reason="no_usable_box",
                domain=domain,
                ratio=None,
                scores=[],
                latency_ms=0.0,
                bbox_source="none",
            )
            continue

        page_started = time.monotonic()
        try:
            cache_key = (item.page_no, crop.angle)
            page_png = page_cache.get(cache_key)
            if page_png is None:
                page_png = _render_page(Path(pdf_path), item.page_no, dpi, crop.angle)
                page_cache[cache_key] = page_png
            verification = verify_field(
                page_image=page_png,
                bbox_milli=crop.bbox_milli,
                candidates=candidates,
                domain=domain,
            )
        except _CROP_ERRORS as exc:
            # 裁块阶段的可预期失败（源文件读不了 / 页号越界 / 坐标越界）：这一条留人工。
            logger.warning(
                "pdf_split_judge_crop_failed",
                extra={"page_no": item.page_no, "error_type": type(exc).__name__},
            )
            annotations[key] = _annotation(
                decision="human",
                winner=None,
                reason="crop_failed",
                domain=domain,
                ratio=None,
                scores=[],
                latency_ms=round((time.monotonic() - page_started) * 1000, 2),
                bbox_source=crop.source,
            )
            continue

        judged += 1
        judgement = verification.judgement
        annotations[key] = _annotation(
            decision=verification.decision,
            winner=verification.winner,
            reason=verification.reason,
            domain=domain,
            ratio=getattr(judgement, "ratio", None),
            scores=list(getattr(judgement, "scores", ()) or ()),
            latency_ms=round((time.monotonic() - page_started) * 1000, 2),
            bbox_source=crop.source,
        )

    if annotations:
        accepted = sum(1 for a in annotations.values() if a["decision"] == "accept")
        logger.info(
            "pdf_split_judge_done",
            extra={
                "total": len(disagreements),
                "annotated": len(annotations),
                "judged": judged,
                "accepted": accepted,
                "elapsed_s": round(time.monotonic() - started, 2),
            },
        )
    return annotations


def _skip_reason(candidates: Sequence[str]) -> str | None:
    """这一条根本不该判吗？（判了只会浪费两次调用，且结论必然是 prob_low）

    Returns:
        ``multiline_block`` / ``length_mismatch``；可判时返回 None。
    """
    longest = max(len(text) for text in candidates)
    if longest > MAX_JUDGEABLE_CHARS:
        return "multiline_block"
    shortest = min(len(text) for text in candidates if text.strip())
    if shortest and longest / shortest > MAX_CANDIDATE_LENGTH_RATIO:
        return "length_mismatch"
    return None


def _candidates_of(item: EngineDisagreement) -> list[str]:
    """从一条分歧取出候选文本（两引擎的**全文**，去重保序）。

    用 ``body``（全文）而不是 ``text``（截到 120 字的摘要）：摘要带省略号，与裁块
    不同域，会直接把分数打到噪声区。
    """
    out: list[str] = []
    for variant in item.variants:
        body = str(variant.body or "").strip()
        if body and body not in out:
            out.append(body)
    return out


def _annotation(
    *,
    decision: str,
    winner: str | None,
    reason: str,
    domain: str,
    ratio: float | None,
    scores: Sequence[Any],
    latency_ms: float,
    bbox_source: str,
) -> dict[str, Any]:
    """组一条落盘附注。``scores`` 只保留 verdict 与概率，不留候选文本（summary 已有全文）。"""
    rows: list[dict[str, Any]] = []
    for score in scores:
        row: dict[str, Any] = {}
        for field_name in _SCORE_FIELDS:
            value = getattr(score, field_name, None)
            if value is not None:
                row[field_name] = round(float(value), 6) if field_name == "prob_yes" else value
        if row:
            rows.append(row)
    return {
        "decision": decision,
        "winner": winner,
        "reason": reason,
        "domain": domain,
        "ratio": None if ratio is None else round(float(ratio), 4),
        "scores": rows,
        "latency_ms": latency_ms,
        "bbox_source": bbox_source,
    }


def summarize(annotations: Mapping[tuple[int, str, str], Mapping[str, Any]]) -> dict[str, Any]:
    """把附注汇总成一个可落 summary 的小 dict（前端/排障用）。"""
    reasons: dict[str, int] = {}
    accepted = 0
    for annotation in annotations.values():
        reason = str(annotation.get("reason") or "")
        reasons[reason] = reasons.get(reason, 0) + 1
        if annotation.get("decision") == "accept":
            accepted += 1
    return {
        "annotated": len(annotations),
        "accepted": accepted,
        "human": len(annotations) - accepted,
        "reasons": reasons,
    }
