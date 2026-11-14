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


#: 拆格门槛：整表高度超过页面这个比例才拆。
#:
#: 为什么不是「有 table 就拆」：一两行的小表格拆开没有意义（每个框都很小，
#: 反而让绿框密度过高、读不清）。实测 152 个 table 块里 114 个高度 >25%，
#: 那些才是「一个大框罩住十几行」、律师点不中具体某一格的真问题。
_TABLE_SPLIT_MIN_HEIGHT_RATIO = 0.18

#: 拆成**单元格**的上限：超过就退回「按行拆」。
#:
#: 实测 164 页卷宗里，单元格数存在**明显断层**：
#:   流水类长表  247 / 256 / 274 / 295 / 307×5 / 974 / 1341 / 1627 / 2046
#:   表单类中等表  65 / 68 / 69 / 80 / 88 / 92
#: 断层就落在 92 与 247 之间。取 120 做分界，两类都能干净分开。
#:
#: 为什么长表只拆到行：逐格拆会把全卷块数从 1147 撑到 6062（5.3 倍），前端渲染
#: 几千个绝对定位框会明显卡顿；而且流水的单格本身无点击价值——律师要看的是「哪一行」。
_TABLE_CELL_SPLIT_MAX = 120

#: 拆成**行**的上限：再超过就整体保留。
#:
#: 237 行的超长表格拆行意义也不大（每行只有 3px 高，点不中），
#: 而且块数同样会爆。这类表在卷宗里就是流水，律师靠原文检索而非点框。
_TABLE_ROW_SPLIT_MAX = 80


def _table_cell_count(html: str) -> int:
    """表格的单元格总数（用于决定拆到格还是拆到行）。"""
    return sum(len(_CELL_RE.findall(row_html)) for row_html in _TR_RE.findall(html))


def _split_table_into_cells(
    *,
    page_no: int,
    rect: dict[str, Any],
    html: str,
    unit: str,
    by_row_only: bool = False,
) -> list[dict[str, Any]]:
    """把一个大表格块按行列均分，拆成逐格块。

    ## 为什么可以均分

    MinerU 对表格只给**整表 bbox**，不给逐格坐标。但它在 ``table_body`` 里给了
    完整的 HTML 结构（行列齐全）。等宽表格按行列数均分整表矩形，落点误差只在
    半格以内 —— 律师要的是「点中这一格」而不是像素级精确，这个精度够用。

    实测 p22：17 行 × 4 列全部对齐，bbox=[192,154,790,554]，
    每格约 149.5 × 23.5 px。

    ## 为什么拆格而不是拆行

    律师的痛点是「我要点在『*房产证编号』这一格上，不要框住整张表」。
    只拆到行仍然要在一行四格里挑，还是点不准。拆到单元格才是真正可点击的粒度。

    ## by_row_only：长表格只拆到行

    超过 ``_TABLE_CELL_SPLIT_MAX`` 格的长表（银行流水类）逐格拆会把块数撑爆
    （实测全卷 1147 → 6062），且流水的单格本身无点击价值。这类表按行合并成
    一个块，每行保留该行全部单元格的文字拼接——律师点中「哪一行」就够用了。

    ## 返回空列表的条件（调用方保留原整块）

    - 行/列数算不出来
    - 行数超过 ``_TABLE_ROW_SPLIT_MAX``
    - 所有格子文字都为空
    """
    rows = _TR_RE.findall(html)
    if not rows:
        return []

    parsed: list[list[str]] = []
    for row_html in rows:
        cells = [_TAG_RE.sub("", cell).strip() for cell in _CELL_RE.findall(row_html)]
        if cells:
            parsed.append(cells)
    if not parsed:
        return []

    row_count = len(parsed)
    col_count = max(len(cells) for cells in parsed)
    if row_count <= 0 or col_count <= 0 or row_count > _TABLE_ROW_SPLIT_MAX:
        return []

    x0, y0 = float(rect["x"]), float(rect["y"])
    total_w, total_h = float(rect["w"]), float(rect["h"])
    cell_w = total_w / col_count
    cell_h = total_h / row_count

    out: list[dict[str, Any]] = []

    if by_row_only:
        # 长表（流水）：一行一个块，文字是该行各格拼起来的
        for row_index, cells in enumerate(parsed):
            row_text = " ".join(cell for cell in cells if cell).strip()
            if not row_text:
                continue
            out.append(
                {
                    "page": page_no,
                    "type": "table_row",
                    "text": row_text,
                    "rect": {
                        "x": round(x0, 4),
                        "y": round(y0 + cell_h * row_index, 4),
                        "w": round(total_w, 4),
                        "h": round(cell_h * 0.92, 4),
                        "approx": True,
                    },
                }
            )
        return out

    for row_index, cells in enumerate(parsed):
        for col_index, text in enumerate(cells):
            if not text:
                continue
            out.append(
                {
                    "page": page_no,
                    "type": "table_cell",
                    "text": text,
                    "rect": {
                        "x": round(x0 + cell_w * col_index, 4),
                        "y": round(y0 + cell_h * row_index, 4),
                        # 每格留 1px 级的缝：相邻格边框不重叠，律师看得出是两格
                        "w": round(cell_w * 0.97, 4),
                        "h": round(cell_h * 0.94, 4),
                        # 均分推算出来的，不是量出来的 —— 前端画虚线，不谎报精度
                        "approx": True,
                    },
                }
            )
    return out


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
            # 大表格拆成逐格块：一个大框罩住十几行时，律师点不中具体某一格。
            # 实测 152 个 table 块里 114 个高度 >25% 页面，这是普遍的体验问题。
            if block_type == "table" and float(rect["h"]) >= _TABLE_SPLIT_MIN_HEIGHT_RATIO:
                table_html = str(block.get("table_body") or block.get("table_structure") or "")
                cells = _split_table_into_cells(
                    page_no=page.page_no,
                    rect=rect,
                    html=table_html,
                    unit=unit,
                    by_row_only=_table_cell_count(table_html) > _TABLE_CELL_SPLIT_MAX,
                )
                if cells:
                    out.extend(cells)
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
