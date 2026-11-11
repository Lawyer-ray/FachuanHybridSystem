"""分段 Markdown 重建：把每段的逐页取字结果重组成 AI 友好的 Markdown。

取字层两条路径的产出结构不同，这里统一收敛：
- 云端解析（MinerU / TextIn）：PageDescriptor.layout.blocks 带 block 类型、
  标题层级（MinerU text_level）与表格数据（MinerU table_body / TextIn
  table_structure，HTML）——按版面块重建标题 / 段落 / GFM 表格；
- 本地 OCR / PDF 文本层：只有页文本——按原文输出（保留换行），页间空行。

不存 DB（零迁移）：产物落 job 目录 analysis/segments_md.json，
经 job API 的 content_md 字段透出，供下游 AI 流程直接消费。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .bbox import normalize_bbox, resolve_bbox_unit
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")

_TITLE_TYPES = {"title", "text_level_title", "heading", "标题"}
_NOISE_TYPES = {"header", "footer", "page_number", "image", "equation", "watermark"}

_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def build_segments_markdown(
    drafts: list[SegmentDraft],
    pages: list[PageDescriptor],
    *,
    bbox_backend: str | None = None,
) -> list[dict[str, Any]]:
    """为每个分段生成 Markdown 描述（order / 页区间 / 正文 / 定坐标块）。

    ``positioned`` 是「识别定位」的数据：每个正文块 + 它在原页上的归一化矩形。
    前端拿它做"点右栏字段 → 原文绿框"的双向对照。没有坐标的后端（本地 OCR）
    给空列表，而不是给一堆没框的块让前端白渲染。
    """
    page_by_no = {page.page_no: page for page in pages}
    results: list[dict[str, Any]] = []
    for draft in drafts:
        seg_pages = [page_by_no[no] for no in range(draft.page_start, draft.page_end + 1) if no in page_by_no]
        title = re.sub(r"\.pdf$", "", draft.filename or "", flags=re.IGNORECASE).strip() or "未命名材料"
        results.append(
            {
                "order": draft.order,
                "page_start": draft.page_start,
                "page_end": draft.page_end,
                "markdown": build_segment_markdown(title, seg_pages),
                "positioned": build_positioned_blocks(seg_pages, bbox_backend=bbox_backend),
            }
        )
    return results


def build_positioned_blocks(
    pages: list[PageDescriptor],
    *,
    bbox_backend: str | None = None,
) -> list[dict[str, Any]]:
    """页 → 可定位块列表（只含能对上坐标的正文块）。

    每个块：``{page, type, text, rect:{x,y,w,h,approx}}``。
    ``rect`` 统一为 0–1 归一化，前端直接 ``left: x*100%`` 就能画。
    坐标换算不出来（无页面尺寸 / 后端不给坐标）的块**整条丢弃**：
    没框的块在前端只能当普通文本展示，那还不如留在 markdown 里。
    """
    unit = resolve_bbox_unit(bbox_backend)
    if unit == "unknown":
        return []
    out: list[dict[str, Any]] = []
    for page in pages:
        layout = page.layout if isinstance(page.layout, dict) else {}
        blocks = layout.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower()
            text = str(block.get("text") or "").strip()
            if block_type in _NOISE_TYPES or not text:
                continue
            rect = normalize_bbox(
                block.get("bbox"),
                unit=unit,
                page_width=layout.get("width"),
                page_height=layout.get("height"),
            )
            if rect is None:
                continue
            entry: dict[str, Any] = {
                "page": page.page_no,
                "type": block_type or "text",
                "text": text,
                "rect": rect,
            }
            # Office 的结构定位（段落序 / 行列）一并透出：它对"定位"是确定的，
            # 而矩形只是整页近似。两者不冲突，前端按需用。
            locator = block.get("locator")
            if isinstance(locator, dict):
                entry["locator"] = locator
            out.append(entry)
    return out


def build_segment_markdown(title: str, pages: list[PageDescriptor]) -> str:
    parts = [f"# {title}"]
    for page in pages:
        chunk = _page_markdown(page)
        if chunk:
            parts.append(chunk)
    return "\n\n".join(parts).strip() + "\n"


def _page_markdown(page: PageDescriptor) -> str:
    blocks = (page.layout or {}).get("blocks") if isinstance(page.layout, dict) else None
    if isinstance(blocks, list) and blocks:
        rendered = [chunk for chunk in (_block_markdown(block) for block in blocks) if chunk]
        if rendered:
            return "\n\n".join(rendered)
    return (page.text or "").strip()


def _block_markdown(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    block_type = str(block.get("type") or "").strip().lower()
    text = str(block.get("text") or "").strip()
    if block_type in _NOISE_TYPES or not text:
        return ""

    if block_type == "table":
        table_md = _html_table_to_markdown(str(block.get("table_body") or block.get("table_structure") or ""))
        return table_md or text

    text_level: Any = block.get("text_level")
    if block_type in _TITLE_TYPES or text_level not in (None, "", 0, "0"):
        try:
            level = max(2, min(int(text_level) + 1, 6)) if str(text_level).lstrip("-").isdigit() else 2
        except (TypeError, ValueError):
            level = 2
        return f"{'#' * level} {text}"
    return text


def _html_table_to_markdown(html: str) -> str:
    """容忍残缺的 HTML 表格 → GFM 表格；解析不出行时返回空串走纯文本兜底。"""
    if not html:
        return ""
    rows: list[list[str]] = []
    for row_html in _TR_RE.findall(html):
        cells = [_TAG_RE.sub("", cell).replace("|", "\\|").strip() for cell in _CELL_RE.findall(row_html)]
        cells = [re.sub(r"\s+", " ", cell) for cell in cells]
        if cells:
            rows.append(cells)
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header, *body = normalized
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + " --- |" * width,
        *("| " + " | ".join(row) + " |" for row in body),
    ]
    return "\n".join(lines)
