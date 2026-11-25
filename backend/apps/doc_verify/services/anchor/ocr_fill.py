"""扫描页取字（tier ≥ 1）：把「一个字都没有」的页 OCR 成文字，补进正文。

## 为什么只在回传件侧补

基线侧永不 OCR（理由见 :mod:`apps.doc_verify.services.anchor.extract` 模块文档）：
出站件是数字原稿，取字就是取 PDF 文本层；回传件是扫描 / 拍照件，没有文本层就
一个字都比不了，只能给灰色「未发现差异」。本层把「比不了」变成「可以比」，
且只有回传件一侧带识别噪声，基线侧仍是原稿文本。

## 三条硬语义（上层是按**页下标**比对的）

1. **只补空页**：已经有字的页一律不重 OCR——重认会把原本正确的字换成识别误差。
2. **输出段数恒等于 ``page_count``**：逐页用 ``\\f`` 拼接，没补上的页留空段。
   少一段就整份错位（第 3 页的断言会打到第 2 页的正文上）。
3. **失败分级，两种都不抛异常**：引擎不可用 → ``engine="unavailable"``（上层据此报
   灰色「无法核对」，不能给绿灯，也不该 500）；单页失败 → 只记 ``pages_failed``，
   其它页照常识别。OCR 是这一层唯一会「抖动」的东西，抖动不该让整次核对崩掉。

## 只覆盖 PDF 的栅格化

:func:`_ocr_page` 按 PDF 语义渲染。图片 / docx 回传件不属本层范围：它们会落进
``pages_failed``（正文仍为空 → 上层灰色），不会静默变成「未发现差异」。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pymupdf

from apps.doc_verify.services.anchor.extract import PAGE_TEXT_SEPARATOR

logger = logging.getLogger(__name__)

#: OCR 渲染 DPI。口径与 :mod:`apps.pdf_splitting.services.split.ocr_handler` 的
#: BALANCED 档（200dpi）对齐：同一份扫描页在两条 lane 上取到的字，不该因为
#: 分辨率不同而分化（那边 220dpi 的 ACCURATE 档是「精度优先」的显式选择，不是默认）
OCR_RENDER_DPI = 200

#: 单次填充默认最多 OCR 多少页：扫描件的页数没有上界，而每一页都是秒级开销。
#: 可用环境变量覆盖（见 :func:`_resolve_page_budget`）
DEFAULT_OCR_PAGE_BUDGET = 10

#: 覆盖默认页数上限的环境变量名
PAGE_BUDGET_ENV = "FACHUAN_DOC_VERIFY_OCR_PAGES"

#: 引擎跑通了本地 OCR
ENGINE_LOCAL = "local"
#: 引擎不可用（import 失败 / 初始化异常 / 模型缺失）：上层只能报灰色「无法核对」
ENGINE_UNAVAILABLE = "unavailable"

#: OCR 链路上可能抛的具体异常族，直接写在 ``except`` 里（仓库禁止宽 ``except Exception``）：
#: ``ImportError`` = rapidocr 没装；``RuntimeError`` / ``OSError`` = onnxruntime 会话、
#: 模型文件或输入数据有问题；``ValueError`` = 引擎参数 / 图像不认。pymupdf 的
#: ``FileDataError`` 也继承 ``RuntimeError``（同一条事实见 extract.py 的 ``_PYMUPDF_ERRORS``）
_OCR_ERRORS = (ImportError, RuntimeError, ValueError, OSError)


class _OcrUnavailable(Exception):
    """引擎拿不到或建不起来——**不是**「这一页没认出字」，两者上层处置完全不同。"""


def _resolve_page_budget() -> int:
    """环境变量 → 默认页数上限；非法值（非整数 / 负数）回落 :data:`DEFAULT_OCR_PAGE_BUDGET`。

    负数为什么按非法处理：参数口径里 ``page_budget <= 0`` 是「一页都不 OCR」，
    但环境变量里写负数多半是想写「不限」，而「不限」的真实代价是整份几十页卷宗
    全部 OCR。安全方向是回落到默认上限，并在日志里说清。
    """
    raw = os.environ.get(PAGE_BUDGET_ENV, "").strip()
    if not raw:
        return DEFAULT_OCR_PAGE_BUDGET
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r 不是整数，回落默认 %d 页", PAGE_BUDGET_ENV, raw, DEFAULT_OCR_PAGE_BUDGET)
        return DEFAULT_OCR_PAGE_BUDGET
    if value < 0:
        logger.warning("%s=%r 是负数（不是「不限」），回落默认 %d 页", PAGE_BUDGET_ENV, raw, DEFAULT_OCR_PAGE_BUDGET)
        return DEFAULT_OCR_PAGE_BUDGET
    return value


#: 默认上限。模块导入时解析一次即可：它是**函数默认参数**，运行期改环境变量本来就不会生效
OCR_PAGE_BUDGET = _resolve_page_budget()


@dataclass(frozen=True)
class OcrFillResult:
    """一次填充的结果：逐页文本 + 逐页处置 + 引擎状态。

    ``text`` 的段数**恒等于** ``page_count``（按 ``\\f`` 切分），页码与段下标一一对应；
    例外只有 ``engine="unavailable"``：那时 ``text`` 原样返回未改动的 ``existing_text``。
    """

    text: str
    """逐页用 ``\\f`` 拼接；未填的页留空段（段数 = page_count）"""

    pages_attempted: tuple[int, ...]
    """真正交给引擎的页（1-based，按尝试顺序；hint 页排在最前）"""

    pages_filled: tuple[int, ...]
    """引擎跑通并回写了文本的页。引擎返回空串也算跑通——页面本身可能真的没字"""

    pages_failed: tuple[int, ...]
    """渲染或识别抛异常的页（1-based，按尝试顺序）"""

    budget_exhausted: bool
    """还有需要 OCR 的页没轮到（页数上限用尽）；``engine="unavailable"`` 时恒为 False"""

    engine: str
    """``"local"`` | ``"unavailable"``"""


def fill_text_with_ocr(
    data: bytes,
    *,
    page_count: int,
    existing_text: str,
    page_budget: int = OCR_PAGE_BUDGET,
    hint_pages: Sequence[int] = (),
) -> OcrFillResult:
    """把 ``existing_text`` 里没字的页用本地 OCR 补上，返回按页对齐的新文本。

    选页顺序：先 ``hint_pages``（去重、越界与有字的页剔除），再按页码升序补，
    最多 ``page_budget`` 页；``page_budget <= 0`` 表示这次一页都不 OCR（只算账）。
    """
    page_texts = _split_page_texts(existing_text, page_count)
    pending = _pages_without_text(page_texts)
    selected = _select_pages(pending, hint_pages=hint_pages, page_budget=page_budget)
    if not selected:
        # 没有要 OCR 的页：不探测引擎（探测会白建一次 ONNX 会话），
        # 也就没有任何「引擎不可用」的证据，engine 记 local
        return OcrFillResult(
            text=_join_page_texts(page_texts),
            pages_attempted=(),
            pages_filled=(),
            pages_failed=(),
            budget_exhausted=bool(pending),
            engine=ENGINE_LOCAL,
        )
    return _fill_pages(
        data=data,
        page_texts=page_texts,
        selected=selected,
        pending_count=len(pending),
        existing_text=existing_text,
    )


def _fill_pages(
    *,
    data: bytes,
    page_texts: list[str],
    selected: Sequence[int],
    pending_count: int,
    existing_text: str,
) -> OcrFillResult:
    """逐页 OCR 并就地回写 ``page_texts``；单页失败只记不抛。"""
    attempted: list[int] = []
    filled: list[int] = []
    failed: list[int] = []
    for page_index in selected:
        attempted.append(page_index)
        try:
            text = _ocr_page(data, page_index)
        except _OcrUnavailable as exc:
            if not filled and not failed:
                return _unavailable_result(existing_text, exc)
            # 已经有过跑通的页 → 引擎显然是活的，这只是一页的故障
            logger.warning("第 %d 页 OCR 引擎报错（此前已有页跑通），按单页失败处理：%s", page_index, exc)
            failed.append(page_index)
            continue
        except _OCR_ERRORS as exc:
            logger.warning("第 %d 页 OCR 失败，继续识别其它页：%s", page_index, exc)
            failed.append(page_index)
            continue
        page_texts[page_index - 1] = text
        filled.append(page_index)
    return OcrFillResult(
        text=_join_page_texts(page_texts),
        pages_attempted=tuple(attempted),
        pages_filled=tuple(filled),
        pages_failed=tuple(failed),
        budget_exhausted=len(selected) < pending_count,
        engine=ENGINE_LOCAL,
    )


def _unavailable_result(existing_text: str, exc: BaseException) -> OcrFillResult:
    """引擎不可用：正文原样退回，一页都不认账（上层据此报灰色「无法核对」）。"""
    logger.warning("回传件 OCR 引擎不可用，本次未补任何页（上层只能报灰色「无法核对」）：%s", exc)
    return OcrFillResult(
        text=existing_text,
        pages_attempted=(),
        pages_filled=(),
        pages_failed=(),
        budget_exhausted=False,
        engine=ENGINE_UNAVAILABLE,
    )


def _split_page_texts(existing_text: str, page_count: int) -> list[str]:
    """``existing_text`` → 恰好 ``page_count`` 段，段下标即页下标。"""
    segments = (existing_text or "").split(PAGE_TEXT_SEPARATOR)
    if page_count <= 0:
        if (existing_text or "").strip():
            logger.warning("回传件页数为 %d 却带着正文，无法按页对齐，正文丢弃", page_count)
        return []
    page_texts = segments[:page_count]
    extra = segments[page_count:]
    if any(text.strip() for text in extra):
        # 段数比页数多：拒绝拿「看起来完整」的正文去错位比对，多出来的部分明确丢掉
        logger.warning("回传件正文切出 %d 段，多于页数 %d，多出的段落丢弃以免错位", len(segments), page_count)
    page_texts.extend([""] * (page_count - len(page_texts)))
    return page_texts


def _pages_without_text(page_texts: Sequence[str]) -> tuple[int, ...]:
    """需要 OCR 的页（1-based，升序）：整段为空或整段缺失。"""
    return tuple(index for index, text in enumerate(page_texts, start=1) if not text.strip())


def _select_pages(
    pending: Sequence[int],
    *,
    hint_pages: Sequence[int],
    page_budget: int,
) -> tuple[int, ...]:
    """hint 页优先 + 页码升序补齐，最多 ``page_budget`` 页。

    hint 的意义：上层已经从比对里知道「差异出在第 N 页」，那几页先取字，
    页数上限用尽时优先牺牲没被告状的页。
    """
    if page_budget <= 0 or not pending:
        return ()
    pending_set = set(pending)
    ordered: list[int] = []
    seen: set[int] = set()
    for page_index in hint_pages:
        # 越界（不在 pending 里）、重复、已经有字的页都在这一步被剔除
        if page_index in pending_set and page_index not in seen:
            seen.add(page_index)
            ordered.append(page_index)
    ordered.extend(page_index for page_index in pending if page_index not in seen)
    return tuple(ordered[:page_budget])


def _join_page_texts(page_texts: Sequence[str]) -> str:
    return PAGE_TEXT_SEPARATOR.join(page_texts)


def _ocr_page(data: bytes, page_index: int) -> str:
    """第 ``page_index`` 页（1-based）的**唯一** OCR 调用点。

    单独成函数的理由是可测性：用例整段替换它（``monkeypatch``）就能覆盖选页 / 预算 /
    失败分级，不必跑真引擎（首次建 ONNX 会话约 20s，模型文件也不进 CI）。

    引擎拿不到 / 建不起来抛 :class:`_OcrUnavailable`（→ 整轮判不可用）；
    渲染或识别失败抛 ``_OCR_ERRORS`` 里的具体异常（→ 只把这一页记进 ``pages_failed``）。

    先渲染后取引擎：栅格化是「这份字节能不能按页取字」的第一道关，它失败时
    没必要去建（首次约 20s 的）ONNX 会话。
    """
    image_png = _render_page_png(data, page_index)
    ocr_service = _ocr_service()
    return str(ocr_service.recognize_bytes(image_png) or "").strip()


def _ocr_service() -> Any:
    """拿到 OCR 服务，并**当场把引擎建起来**。

    为什么必须在这一步建：模型缺失 / 会话初始化异常与「这一页没认出字」在
    ``recognize_bytes`` 里长得一样，都是抛异常；若不提前建，模型缺失会被记成
    「每页都失败 → 只是没认出字」，而契约要求 ``engine="unavailable"``（灰色「无法核对」）。
    提前建的代价只有一次：引擎本身是进程级单例（``ocr_service.get_ocr_engine`` 有锁）。

    入口与其他调用方一致走 ``ServiceLocator``（同 ``apps/evidence/services/ai`` 一线），
    再触发底层 ``OCRService.ocr`` 惰性属性把 ``get_ocr_engine()`` 跑起来。
    """
    try:
        from apps.core.interfaces import ServiceLocator

        service = ServiceLocator.get_ocr_service()
        # 适配器（OCRServiceAdapter）里真正的引擎持有者是 ``.service``；直接注入
        # OCRService 实现时就是它自己——两种都能取到 ``.ocr`` 属性
        engine_holder = getattr(service, "service", service)
        getattr(engine_holder, "ocr", None)  # 触发引擎初始化（模型在这里加载 / 报错）
        return service
    except _OCR_ERRORS as exc:
        raise _OcrUnavailable(f"OCR 服务不可用（import 失败 / 初始化异常 / 模型缺失）：{exc}") from exc


def _render_page_png(data: bytes, page_index: int) -> bytes:
    """按 OCR 口径把一页栅格化成 PNG 字节。**不落临时文件**：``recognize_bytes`` 吃字节。"""
    with pymupdf.open(stream=data, filetype="pdf") as document:
        page_total = int(document.page_count)
        if not 1 <= page_index <= page_total:
            raise ValueError(f"页码越界：第 {page_index} 页不在 1..{page_total}")
        matrix = pymupdf.Matrix(OCR_RENDER_DPI / 72, OCR_RENDER_DPI / 72)
        pixmap = document.load_page(page_index - 1).get_pixmap(matrix=matrix)
        return bytes(pixmap.tobytes("png"))  # pymupdf 无类型标注，转一层收窄回 bytes
