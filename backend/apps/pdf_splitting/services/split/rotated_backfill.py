"""转正页回填：把「PaddleOCR-VL 认对了的那几页」真正换进正文。

## 解决什么（实测案例，不是假设）

双引擎的 PaddleOCR-VL 结果以前**只用于比对**（``engine_disagreements``），正文永远来自
主引擎。job ``523fabce`` 的 p52 就是代价：内容躺倒 90°、``/Rotate=0``，MinerU 返回
「成功」但文本全错——而 VL 那一次（开方向分类）认对了 689 字、自报 ``angle=270``。
正文至今是乱码，因为 VL 的结果没有任何路径进正文。

本模块只做一件事：**候选页**（VL 报 ``angle ∈ {90,180,270}``，即服务端为了识别把页面
转正过）在 VL 侧有可用结果时，用 VL 的文本（有块时连版面一起）**替换**该页正文。

## 判据为什么是 angle，而不是「这段文本看着像乱码」

「像不像乱码」没有可靠判据（`page_quality` 的图形页 / 稀疏页只是提示）。``angle≠0``
是 VL 自己报的**可复核事实**：这一页在原页帧里是躺倒的，主引擎没做方向分类，它给出的
正文本身就不可信。所以：

· ``angle == 0`` 的页（绝大多数）**逐位不变**——这是本模块的红线，任何改动都会让
  6843 个既有用例里的正文发生变化；
· VL 整体失败（如 HTTP 500）时 ``angles`` 是空表 → 一个候选页都没有 → 任何页都不受影响
  （「没有数据」与「数据说没转正」在这里得到同一个安全结果）。

## 为什么有块时必须连版面一起换

正文与版面必须同源：只换 text 而保留主引擎的 ``layout``，Markdown 会来自 VL、绿框却来自
MinerU，同一页的两份产物指在不同的地方（表格格子尤其明显）。所以有块 → text + layout
一起换；无块 → **只**换 text，``layout`` 原样留着（那个对象连引用都不换），原因记
``layout_kept``，让「为什么这页框还是旧的」在 summary 里查得到。

## 为什么只有一个公开入口

``apply_rotated_backfill`` 是唯一入口，调用点只有一处：``service.cross_check_stage``。
那里是**同时**拿得到 ``pages`` 与 ``DualEngineOutcome`` 的唯一位置（双引擎已拆成独立
阶段，取字阶段手里根本没有 VL 结果）。``tests/ci/unit/pdf_splitting/test_rotated_backfill.py``
有一条守卫用例按 AST 断言「全仓只有这一处调用」——将来哪个入口也需要回填，请复用本模块
而不是复制一份判据（复制出来的第二份判据迟早与第一份漂移，而漂移的表现是「同一份卷宗
在不同入口下正文不一样」）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any

from .dual_engine import ENGINE_PADDLEOCR_VL
from .ocr_handler import vl_blocks_layout
from .pipeline import build_page_descriptor
from .split_models import PageDescriptor

logger = logging.getLogger("apps.pdf_splitting")

#: 回填后的页级取字来源标记。自由字符串（``PageDescriptor.source_method`` 没有 choices
#: 校验），但它必须是**新值**：``cloud_backend_of_method`` 只认 ``mineru`` / ``textin``
#: 前缀，所以这个值不会被误判成某个云端平台的坐标系来源。
SOURCE_METHOD_VL_ROTATION = "paddleocr_vl_rotation"

#: 服务端为识别把页面转正过的角度集合（逆时针为正，见 ``page_rotation``）。
_ROTATED_ANGLES = (90, 180, 270)

#: 跳过 / 部分跳过该页的原因。每个跳过都必须是这里的一个值，并且进 summary——
#: 静默跳过会让「这页为什么还是乱码」只能靠猜。
REASON_DISABLED = "disabled"
REASON_ALREADY_BACKFILLED = "already_backfilled"
REASON_VL_EMPTY = "vl_empty"
REASON_LAYOUT_KEPT = "layout_kept"

#: 回填会改到的 ``PageDescriptor`` 字段。
#:
#: 回写 ``pages.json`` 时按这个清单逐字段写回（见 ``service._write_back_pages``）：
#: 正文与它的派生物（normalized / head / 规则候选分）必须一起换，否则规则分段看到的
#: 是「新正文 + 旧候选分」。``layout_title`` 跟着 ``layout`` 一起换，不留旧标题。
BACKFILL_FIELDS: tuple[str, ...] = (
    "text",
    "normalized_text",
    "head_text",
    "top_candidates",
    "layout",
    "layout_title",
    "source_method",
    "ocr_failed",
)

_PAGE_FIELDS = frozenset(item.name for item in fields(PageDescriptor))


@dataclass(frozen=True)
class RotatedBackfillResult:
    """一次回填的判决：哪些页换了正文，哪些页没换及原因。

    ``skipped`` 里也可能出现**已回填但只换了 text** 的页（原因 ``layout_kept``）：
    那是「换了一半」的如实记账，不是失败。
    """

    applied: tuple[int, ...] = ()
    skipped: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class VlPageView:
    """VL 侧的逐页数据，三个表都以**页号**为键（页号口径见 ``_run_paddleocr_vl``）。"""

    angles: dict[int, int] = field(default_factory=dict)
    text: dict[int, str] = field(default_factory=dict)
    blocks: dict[int, list[Any]] = field(default_factory=dict)


def vl_page_view(outcome: Any) -> VlPageView:
    """从 ``DualEngineOutcome`` 取出 VL 这一侧的逐页角度 / 文本 / 块。

    VL 整体失败时三张表都是空的（``engine_pages[VL]`` 为空 dict、角度空 dict、
    没有块），于是 ``plan_backfill`` 找不到任何候选页——**失败不影响任何页**。
    """
    engine_pages = getattr(outcome, "engine_pages", None) or {}
    angles_by_engine = getattr(outcome, "engine_page_angles", None) or {}
    blocks_by_engine = getattr(outcome, "blocks_by_engine", None) or {}

    blocks: dict[int, list[Any]] = {}
    for block in blocks_by_engine.get(ENGINE_PADDLEOCR_VL) or []:
        page_no = int(getattr(block, "page_no", 0) or 0)
        blocks.setdefault(page_no, []).append(block)
    return VlPageView(
        angles={int(key): int(value) for key, value in (angles_by_engine.get(ENGINE_PADDLEOCR_VL) or {}).items()},
        text=dict(engine_pages.get(ENGINE_PADDLEOCR_VL) or {}),
        blocks=blocks,
    )


def pages_from_raw(raw_pages: Iterable[Mapping[str, Any]]) -> list[PageDescriptor]:
    """``pages.json`` 的 raw dict → ``PageDescriptor``（只读方向）。

    未知键在这里被忽略（dataclass 收不下它），但**回写不经过本函数**：
    ``service._write_back_pages`` 改的是 raw dict 本身，所以将来版本新加的字段
    不会被「读成 dataclass 再序列化」这条路丢掉。
    """
    return [PageDescriptor(**{key: value for key, value in item.items() if key in _PAGE_FIELDS}) for item in raw_pages]


def plan_backfill(
    pages: Sequence[PageDescriptor],
    *,
    angles: Mapping[int, int],
    vl_text: Mapping[int, str],
    vl_blocks: Mapping[int, Sequence[Any]],
    enabled: bool,
) -> RotatedBackfillResult:
    """判决每一页：回填 / 不动 / 跳过并记原因。**不改任何东西**。

    判定顺序（前一条命中就不再往下看）：

    1. ``angle not in {90,180,270}`` → 不是候选页，**不记账也不碰**：这类页占绝大多数，
       给每页记一条 skip 只会把 summary 撑成噪声，而它们本来就该逐位不变；
    2. 已经是 ``paddleocr_vl_rotation`` → ``already_backfilled``：幂等，不重复改；
    3. 开关关 → ``disabled``：整页不动（回滚到改动前的唯一手段）；
    4. VL 该页文本为空 / 全空白 → ``vl_empty``：**绝不用空文本覆盖**（那等于把
       收费换来的正文删掉）；
    5. 到这里的页都要换 text；VL 该页没有块则另记 ``layout_kept``，版面原样留。
    """
    applied: list[int] = []
    skipped: dict[int, str] = {}
    for page in pages:
        angle = int(angles.get(page.page_no, 0) or 0)
        if angle not in _ROTATED_ANGLES:
            continue
        if page.source_method == SOURCE_METHOD_VL_ROTATION:
            skipped[page.page_no] = REASON_ALREADY_BACKFILLED
            continue
        if not enabled:
            skipped[page.page_no] = REASON_DISABLED
            continue
        if not str(vl_text.get(page.page_no) or "").strip():
            skipped[page.page_no] = REASON_VL_EMPTY
            continue
        applied.append(page.page_no)
        if not vl_blocks.get(page.page_no):
            skipped[page.page_no] = REASON_LAYOUT_KEPT
    return RotatedBackfillResult(applied=tuple(applied), skipped=skipped)


def apply_backfill(
    pages: Sequence[PageDescriptor],
    plan: RotatedBackfillResult,
    *,
    vl_text: Mapping[int, str],
    vl_blocks: Mapping[int, Sequence[Any]],
    template_key: str = "",
) -> None:
    """按判决**就地**改 ``PageDescriptor``（调用方先 ``plan_backfill`` 拿判决）。

    派生字段一律由 ``build_page_descriptor`` 重算，不在这里手写第二份推导：规则候选分
    （``top_candidates``）也是从正文算出来的，正文换了而候选分不换，规则分段会拿
    「新正文 + 旧候选分」判类型。``ocr_failed`` 一并置 False——这页现在有字了，
    留着 True 会让下游把它当成「未取到文字」。

    无块时 ``layout`` 与 ``layout_title`` **一个字节都不写**（连对象引用都不换），
    这是「正文换了、框还是原来的」那条路径的唯一实现。
    """
    wanted = set(plan.applied)
    for page in pages:
        if page.page_no not in wanted:
            continue
        text = str(vl_text.get(page.page_no) or "").strip()
        blocks = vl_blocks.get(page.page_no) or []
        layout = vl_blocks_layout(blocks, page_no=page.page_no, text=text)
        fresh = build_page_descriptor(
            page_no=page.page_no,
            text=text,
            source_method=SOURCE_METHOD_VL_ROTATION,
            ocr_failed=False,
            template_key=template_key,
            layout=layout,
        )
        page.text = fresh.text
        page.normalized_text = fresh.normalized_text
        page.head_text = fresh.head_text
        page.top_candidates = fresh.top_candidates
        page.ocr_failed = fresh.ocr_failed
        page.source_method = fresh.source_method
        if layout is not None:
            page.layout = fresh.layout
            page.layout_title = fresh.layout_title


def apply_rotated_backfill(
    pages: Sequence[PageDescriptor],
    *,
    angles: Mapping[int, int],
    vl_text: Mapping[int, str],
    vl_blocks: Mapping[int, Sequence[Any]],
    enabled: bool,
    template_key: str = "",
) -> RotatedBackfillResult:
    """**唯一公开入口**：判决 + 就地回填 + 留痕日志。返回判决供 summary 使用。

    ``enabled`` 由调用方从 ``table_geometry_switches.rotated_page_use_vl_text_enabled()``
    读一次再传进来：本模块不做任何 IO，读配置的失败语义（读不到走默认值 + 留痕）
    只在开关模块里有一份。
    """
    plan = plan_backfill(pages, angles=angles, vl_text=vl_text, vl_blocks=vl_blocks, enabled=enabled)
    apply_backfill(pages, plan, vl_text=vl_text, vl_blocks=vl_blocks, template_key=template_key)
    logger.info(
        "pdf_split_rotated_backfill_planned" if plan.applied else "pdf_split_rotated_backfill_noop",
        extra={
            "enabled": enabled,
            "pages_applied": list(plan.applied),
            "skipped": {str(page_no): reason for page_no, reason in sorted(plan.skipped.items())},
        },
    )
    return plan


def summary_block(result: RotatedBackfillResult, *, enabled: bool, error: str = "") -> dict[str, Any]:
    """summary 里的 ``rotated_backfill`` 区块（形状固定，前端/排障都按这几个键读）。

    ``skipped`` 与 ``skipped_counts`` 是两件事：前者答「哪一页为什么没换」，后者答
    「一共跳了几页、各是什么原因」。只有计数的话，出问题还得翻日志才知道是哪一页。
    """
    counts: dict[str, int] = {}
    for reason in result.skipped.values():
        counts[reason] = counts.get(reason, 0) + 1
    block: dict[str, Any] = {
        "enabled": enabled,
        "pages_applied": list(result.applied),
        "skipped": {str(page_no): reason for page_no, reason in sorted(result.skipped.items())},
        "skipped_counts": counts,
    }
    if error:
        block["error"] = error
    return block


def backfill_report(
    result: RotatedBackfillResult,
    *,
    angles: Mapping[int, int],
    chars_before: Mapping[int, int],
    pages: Sequence[PageDescriptor],
    enabled: bool,
    written_at: str,
) -> dict[str, Any]:
    """``analysis/rotated_backfill.json`` 的载荷：**哪几页被换过**的唯一凭据。

    只留字数变化，不留正文：正文已经在 pages.json 里，再存一份是重复；而「换前 32 个字、
    换后 689 个字」足够一眼判断回填是不是真的把乱码换掉了。

    ``skipped`` 里的 ``layout_kept`` 意味着「正文换了、版面没换」——排查「这页正文对但
    框还是歪的」时先看这个键。
    """
    by_page = {page.page_no: page for page in pages}
    return {
        "enabled": enabled,
        "written_at": written_at,
        "applied": [
            {
                "page": page_no,
                "angle": int(angles.get(page_no, 0) or 0),
                "text_chars_before": int(chars_before.get(page_no, 0)),
                "text_chars_after": len(str(by_page[page_no].text or "")) if page_no in by_page else 0,
                "layout_replaced": result.skipped.get(page_no) != REASON_LAYOUT_KEPT,
            }
            for page_no in result.applied
        ],
        "skipped": {str(page_no): reason for page_no, reason in sorted(result.skipped.items())},
    }


__all__ = [
    "BACKFILL_FIELDS",
    "REASON_ALREADY_BACKFILLED",
    "REASON_DISABLED",
    "REASON_LAYOUT_KEPT",
    "REASON_VL_EMPTY",
    "SOURCE_METHOD_VL_ROTATION",
    "RotatedBackfillResult",
    "VlPageView",
    "apply_backfill",
    "apply_rotated_backfill",
    "backfill_report",
    "pages_from_raw",
    "plan_backfill",
    "summary_block",
    "vl_page_view",
]
