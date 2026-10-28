"""块级结构构建与能力探测

把各后端形状不一的 layout / 元素列表统一成 ``list[ParsedBlock]``，让下游质检、
复核界面只面对一套块词汇。

为什么单独一层：后端解析（像素→文本）和块结构（文本→可定位单元）是两件事。
Textin 用 ``elements`` + ``pages[].element_ids``，MinerU 用 ``content_list.json``，
本地后端只有文本行——三者都要能喂给同一个判定/复核链路，差异消化在这里。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.document_parsing.protocols.document_parser_protocol import (
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    BLOCK_TYPE_UNKNOWN,
    ParseCoverage,
    ParsedBlock,
    ParsedDocument,
    normalize_block_type,
)

logger = logging.getLogger(__name__)

#: 无需识别文本的块类型：图片块本来就可能是整幅插图，空文本属正常，
#: 不应据此推断「块解析不可用」。
_TEXT_OPTIONAL_BLOCK_TYPES: frozenset[str] = frozenset({"image"})

#: 判定「块结构真实可用」所需的非空文本块数量下限。
#: 1 个块可能是巧合（如整页只有一行标题），2 个起才说明分块确实在跑。
_MIN_TEXT_BLOCKS_FOR_COVERAGE = 2


def _positive_page_no(raw: Any) -> int | None:
    """把后端给的页码归一为正整数，非法值返回 None（不猜）。"""
    try:
        page_no = int(raw)
    except (TypeError, ValueError):
        return None
    return page_no if page_no > 0 else None


def _build_text_block(raw_text: Any, raw_type: Any, *, page_no: int | None, bbox: Any) -> ParsedBlock:
    """由「类型 + 文本 + 定位」三要素构造一个块（不含可信度）。

    可信度字段刻意保持 None：块结构构建阶段尚未做任何判定，
    在这里填 0 或 1 都是伪造数据。
    """
    return ParsedBlock(
        type=normalize_block_type(str(raw_type) if raw_type is not None else None),
        text=str(raw_text or "").strip(),
        bbox=bbox,
        page_no=page_no,
    )


def build_blocks_from_layout(layout: Any) -> list[ParsedBlock]:
    """从 ``layout.pages[].blocks`` 提取扁平块列表（Textin / MinerU 共用形状）。

    两个云端后端最终都把块放进 ``layout = {"page_count": n, "pages": [
    {"page_no": 1, "width": w, "height": h, "blocks": [...], "text": "..."}, ...]}``，
    因此提取逻辑统一，不必各后端各写一份。

    坏数据一律跳过而非抛错：块结构是增强信息，缺了它主链路（text/markdown）
    仍然可用，不该因为一个畸形 page 就让整次解析失败。

    Args:
        layout: 后端产出的布局字典，或 None。

    Returns:
        按页序、页内原序排列的块列表；无可用内容时返回空列表。
    """
    if not isinstance(layout, dict):
        return []
    pages = layout.get("pages")
    if not isinstance(pages, list):
        return []

    blocks: list[ParsedBlock] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_no = _positive_page_no(page.get("page_no"))
        for raw_block in page.get("blocks") or []:
            if not isinstance(raw_block, dict):
                continue
            blocks.append(
                _build_text_block(
                    raw_block.get("text"),
                    raw_block.get("type"),
                    page_no=page_no,
                    bbox=raw_block.get("bbox"),
                )
            )
    return blocks


def build_blocks_from_lines(lines: list[Any], page_no: int | None = None) -> list[ParsedBlock]:
    """从纯文本行构造块列表（本地后端兜底路径）。

    本地后端（PyMuPDF / RapidOCR）不产出结构化块，但逐行文本同样可以当作
    最小复核单元——复核律师看到的是「这一行可能认错了」，这比整页无标记好得多。
    代价是缺 bbox：无法从原图裁切局部送判定模型，因此能力位里 has_bbox=False。

    Args:
        lines: 文本行列表，空行会被丢弃。
        page_no: 所属页码（本地后端跨页拼接时可传 None）。

    Returns:
        文本类型块列表。
    """
    blocks: list[ParsedBlock] = []
    for line in lines:
        if not isinstance(line, str):
            continue
        text = line.strip()
        if not text:
            continue
        blocks.append(ParsedBlock(type=BLOCK_TYPE_TEXT, text=text, page_no=page_no))
    return blocks


def _resolve_page_geometry(layout: Any) -> tuple[bool, int]:
    """探测 layout 是否带页面宽高，并给出页数。

    API 层用页数补 extra，能力位用「有任一页同时给了宽高」判定。
    两个判断合并成一次遍历，避免同一份 layout 被反复扫。
    """
    if not isinstance(layout, dict):
        return False, 0
    pages = layout.get("pages")
    if not isinstance(pages, list):
        return False, 0

    has_geometry = False
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("width") and page.get("height"):
            has_geometry = True
            break

    page_count = _positive_page_no(layout.get("page_count")) or len(pages)
    return has_geometry, page_count


def detect_coverage(
    blocks: list[ParsedBlock] | None,
    layout: Any,
    *,
    has_confidence: bool = False,
) -> ParseCoverage:
    """探测后端实际提供了哪些块级能力。

    判定原则是**以数据为准，不以后端名称为准**：宁可承认没有，也不假设有。
    例如 Textin 理论上应该给 bbox，但如果某次返回的坐标全为 None，
    能力位就该是 False——否则下游裁图会拿到空区域并静默失败。

    Args:
        blocks: 已构建的块列表（None 表示后端未提供块）。
        layout: 后端原始 layout，用于探测页面宽高。
        has_confidence: 是否已有块带可信度（目前只有未来接入的判定层会置 True）。

    Returns:
        ParseCoverage 能力位。
    """
    if not blocks:
        _, page_count = _resolve_page_geometry(layout)
        return ParseCoverage(has_page_geometry=page_count > 0)

    text_blocks = [b for b in blocks if b.text or b.type in _TEXT_OPTIONAL_BLOCK_TYPES]
    has_blocks = len(text_blocks) >= _MIN_TEXT_BLOCKS_FOR_COVERAGE
    has_bbox = any(b.bbox is not None for b in blocks)
    has_geometry, _ = _resolve_page_geometry(layout)
    return ParseCoverage(
        has_blocks=has_blocks,
        has_bbox=has_bbox,
        has_confidence=has_confidence,
        has_page_geometry=has_geometry,
    )


def layout_page_count(layout: Any) -> int:
    """取 layout 里的页数（无 layout 时返回 0），供 metadata 补充。"""
    _, page_count = _resolve_page_geometry(layout)
    return page_count


def attach_blocks[ParsedT: ParsedDocument](parsed: ParsedT, *, allow_line_fallback: bool = False) -> ParsedT:
    """为 ParsedDocument 补齐 ``blocks`` 与 ``coverage``（原地补，返回同一对象）。

    宿主只调用这一个函数，具体用 layout 提取还是按行兜底由本模块决定。

    Args:
        parsed: ParsedDocument 实例。
        allow_line_fallback: 后端无 layout 时，是否用 ``parsed.text`` 按行切开兜底。
            仅本地后端应传 True；云端后端拿不到 layout 说明这次返回异常，
            用文本行冒充块会掩盖问题。

    Returns:
        传入的 ParsedDocument（已补齐 blocks / coverage）。
    """
    blocks = build_blocks_from_layout(parsed.layout)
    if not blocks and allow_line_fallback:
        blocks = build_blocks_from_lines(str(parsed.text or "").splitlines())

    parsed.blocks = blocks
    parsed.coverage = detect_coverage(blocks, parsed.layout)
    if not parsed.coverage.has_blocks and blocks:
        logger.info(
            "块级结构不足（%d 块，文本块未达 %d 个），按不可用处理: method=%s",
            len(blocks),
            _MIN_TEXT_BLOCKS_FOR_COVERAGE,
            parsed.parse_method,
        )
    return parsed


def blocks_summary(blocks: list[ParsedBlock] | None) -> dict[str, Any]:
    """块的统计摘要（落 metadata，供排查与前端展示）。"""
    if not blocks:
        return {"block_count": 0, "block_types": {}, "review_needed": 0}
    type_counts: dict[str, int] = {}
    for block in blocks:
        type_counts[block.type] = type_counts.get(block.type, 0) + 1
    return {
        "block_count": len(blocks),
        "block_types": type_counts,
        "review_needed": sum(1 for b in blocks if b.needs_review),
    }


def block_to_dict(block: ParsedBlock) -> dict[str, Any]:
    """块 → 可 JSON 化的字典（API 透传 / 落库用）。

    ``confidence`` 保持原值：None 必须原样透出，不能被压成 0。
    """
    return {
        "type": block.type,
        "text": block.text,
        "bbox": block.bbox,
        "page_no": block.page_no,
        "confidence": block.confidence,
        "needs_review": block.needs_review,
        "review_reason": block.review_reason,
    }


__all__ = [
    "BLOCK_TYPE_TABLE",
    "BLOCK_TYPE_UNKNOWN",
    "attach_blocks",
    "block_to_dict",
    "blocks_summary",
    "build_blocks_from_layout",
    "build_blocks_from_lines",
    "detect_coverage",
    "layout_page_count",
]
