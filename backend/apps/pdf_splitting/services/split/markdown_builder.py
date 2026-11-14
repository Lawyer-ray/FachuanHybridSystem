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


#: 单个单元格：捕获 rowspan / colspan 属性值（缺失即 1）
_CELL_WITH_SPAN_RE = re.compile(r"<t([dh])([^>]*)>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_ROWSPAN_RE = re.compile(r"rowspan\s*=\s*[\"']?(\d+)", re.IGNORECASE)
_COLSPAN_RE = re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.IGNORECASE)


def _parse_grid(html: str) -> list[tuple[int, int, int, int, str]]:
    """把 HTML 表格解析成网格占位：``[(row, col, rowspan, colspan, text), ...]``。

    ## 为什么必须处理 rowspan / colspan

    实测 164 页卷宗里 **82 个表格块有 67 个（82%）带合并单元格**。
    不带 span 处理就按「行列均分」切，框会整片错位。合并单元格的典型形态：

    ```html
    <tr><td rowspan="2">照片</td><td colspan="2">结婚申请,符合…</td></tr>
    <tr><td>登记机关</td><td>…</td></tr>
    ```

    首行只有 2 个 td，但第二行有 2 个 td，且首行的第二个 td 跨 2 列 ——
    若直接 `col_count = max(每行td数)`，会算出 2 列、把「结婚申请」那句
    按 1 列宽去画，实际它横跨 2 列。

    注意：上面这个 p29 结婚证页**整页都不拆**（格子里是照片 + 整页只有 3 行），
    由 ``_split_is_trustworthy`` 拦下。span 算法仍然必须正确 —— 它对
    真表单（p22 押品表、p145 不动产权证）是决定框位置的唯一依据。

    ## 算法

    逐行推进，维护每列已占用的行号；遇到 span 就占位并跳过。这是标准 HTML 表格
    占位算法，与浏览器渲染表格的方式一致。
    """
    grid: list[tuple[int, int, int, int, str]] = []
    #: 占位表：``occupied[(row, col)] = True``
    occupied: dict[tuple[int, int], bool] = {}

    for row_index, row_html in enumerate(_TR_RE.findall(html)):
        col_cursor = 0
        for match in _CELL_WITH_SPAN_RE.finditer(row_html):
            _tag, attrs, inner = match.group(1), match.group(2), match.group(3)
            rowspan = int((_ROWSPAN_RE.search(attrs) or [0, "1"])[1])
            colspan = int((_COLSPAN_RE.search(attrs) or [0, "1"])[1])
            rowspan = max(1, rowspan)
            colspan = max(1, colspan)

            # 找到本行第一个未占用的列
            while occupied.get((row_index, col_cursor)):
                col_cursor += 1

            text = _TAG_RE.sub("", inner).strip()
            grid.append((row_index, col_cursor, rowspan, colspan, text))
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied[(row_index + dr, col_cursor + dc)] = True
            col_cursor += colspan

    return grid


def _grid_col_count(grid: list[tuple[int, int, int, int, str]]) -> int:
    """网格的真实列数（由最右侧被占用的列 +1 得出，不受 colspan 干扰）。"""
    return max((col + colspan for _r, col, _rs, colspan, _t in grid), default=0)


def _grid_row_count(html: str) -> int:
    """网格的真实行数（HTML 的 <tr> 数；rowspan 不改变行数，只是格子更高）。"""
    return len(_TR_RE.findall(html))


#: 拆格后**单格**面积的容忍上限（占页面面积比例）。
#:
#: 为什么不是「表格大就拆」：均分只有在「表格本身就是页面格局」时才成立。
#: 实测 p30 结婚证：整页被 MinerU 输出成 3 行 × 2 列的表格（bbox 47-988 × 4-821），
#: 按行列均分得到 6 个 0.27 × 0.47 的格子 —— 单格就占页面 13%，而真实的
#: 「姓名/身份证件号」那一栏只占页面窄窄一条。框比目标大一个数量级，等于没框。
#: 正常表单（p22 押品表 17×4）单格约 1%，差两个数量级，阈值取 4% 分得开。
_SPLIT_MAX_CELL_AREA_RATIO = 0.04

#: 拆格后**每个有字的格子**的平均字数下限。
#:
#: 均分的前提是「表格有完整的行列结构」。整页扫描件被误判成 2-3 行表格时，
#: 一个格子就装下一整段正文（p30 首行 91 字、p154 首行 88 字、p111 单行 244 字、
#: p162 首行 74 字）——那是 OCR 把整块正文拍平后的换行，不是表格结构，按行切必然错位。
#: 真表单每格只装一个字段值（p22 押品表单格 2-6 字，p19 流水单格 4-20 字）。
#:
#: 分母用「有字的格子」而不是「全部格子」：表单本来就大量空着
#: （p22 的 68 格里只有 12 格有字），拿全部格子做分母会把真表单全卡掉。
_SPLIT_MAX_CHARS_PER_CELL = 45


def _table_cell_count(html: str) -> int:
    """表格的单元格总数（用于决定拆到格还是拆到行）。"""
    return sum(len(_CELL_RE.findall(row_html)) for row_html in _TR_RE.findall(html))


def _split_is_trustworthy(
    *,
    rect: dict[str, Any],
    html: str,
    grid: list[tuple[int, int, int, int, str]],
    row_count: int,
    col_count: int,
    by_row_only: bool,
) -> bool:
    """按行列均分这块表格，算出来的框能不能拿去给律师看。

    「表格块」不等于「等宽表格」：证件页/图纸页/拍平正文常被 MinerU 归成 table，
    这类块的 bbox 是**整页**而不是表格本身，行列数也只反映 OCR 的换行，均分必然错位。
    三条否决条件都来自 164 页真实卷宗的实测（见常量注释），命中任一条就退回整块：
    **宁可少画一堆框，也不要画一堆指错地方的框。**
    """
    if "<img" in html.lower():
        # 格子里装着照片/印章：这是整页版面，不是表格。实测 p24/25/27/28/29/33/81/158。
        return False
    if row_count < 2 and not by_row_only:
        # 单行拆格：nv 列均分一行文字，横坐标纯属编造（p147 宗地图 [WDZ7] 就 1 行 1 格）。
        return False
    cell_count = max(1, row_count * col_count)
    if float(rect["w"]) * float(rect["h"]) / cell_count > _SPLIT_MAX_CELL_AREA_RATIO:
        # 单格占比过大 → 整页被当成表格（p30 结婚证），不是能点中的粒度。
        return False
    filled = [len(text) for _r, _c, _rs, _cs, text in grid if text]
    if filled and sum(filled) / len(filled) > _SPLIT_MAX_CHARS_PER_CELL:
        # 每格塞进一整段正文 → 行列是 OCR 换行拼出来的（p30/p154/p162），不是表格结构。
        return False
    return True


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
    - 均分出来的框**不可信**（整页扫描件被当成表格、格子装的是图片、
      单行拆格、格子太大或太空）—— 判据见 ``_split_is_trustworthy``
    """
    rows = _TR_RE.findall(html)
    if not rows:
        return []

    grid = _parse_grid(html)
    if not grid:
        return []

    row_count = _grid_row_count(html)
    col_count = _grid_col_count(grid)
    if row_count <= 0 or col_count <= 0 or row_count > _TABLE_ROW_SPLIT_MAX:
        return []
    # 可信度判定放在**本函数内**而不是交给调用方：拆分入口只有一个，
    # 任何新增调用方都不应该有机会绕开它去画错位的格子。
    if not _split_is_trustworthy(
        rect=rect,
        html=html,
        grid=grid,
        row_count=row_count,
        col_count=col_count,
        by_row_only=by_row_only,
    ):
        return []

    x0, y0 = float(rect["x"]), float(rect["y"])
    total_w, total_h = float(rect["w"]), float(rect["h"])
    # 按**网格**均分，而不是按「每行 td 个数」均分。
    #
    # 两者的差别在合并单元格时才显现：p29 结婚证首行 2 个 td（其一 colspan=2），
    # 第二行 2 个 td —— 「每行 td 数」求出 2 列，实际是 3 列；而「结婚申请…」那一格
    # 横跨 2 列，按 1 列宽去画就短了一截。网格法用 colspan 累加出真实列位置。
    cell_w = total_w / col_count
    cell_h = total_h / row_count

    out: list[dict[str, Any]] = []

    if by_row_only:
        # 长表（流水）：一行一个块，文字是该行各格拼起来的。
        # 行矩形按 <tr> 数均分（rowspan 不改变行数，只是格子更高）。
        by_row: dict[int, list[str]] = {}
        for row_index, _col, _rs, _cs, text in grid:
            if text:
                by_row.setdefault(row_index, []).append(text)
        for row_index in sorted(by_row):
            out.append(
                {
                    "page": page_no,
                    "type": "table_row",
                    "text": " ".join(by_row[row_index]).strip(),
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

    for row_index, col_index, rowspan, colspan, text in grid:
        if not text:
            continue
        # 每格的宽高按 **span 累加**，不是固定单格尺寸：
        #   colspan=2 的「结婚申请…」应为 2 个 cell_w 宽，画 1 个就短一截。
        out.append(
            {
                "page": page_no,
                "type": "table_cell",
                "text": text,
                "rect": {
                    "x": round(x0 + cell_w * col_index, 4),
                    "y": round(y0 + cell_h * row_index, 4),
                    # 每格留 1px 级的缝：相邻格边框不重叠，律师看得出是两格
                    "w": round(cell_w * colspan * 0.97, 4),
                    "h": round(cell_h * rowspan * 0.94, 4),
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
            # 整块保留的**大表格**（不拆或拆不了）：这个矩形是「整块内容的外接框」，
            # 不是某一块文字的位置。bbox 缺失时更糟——``layout`` 里没有页面尺寸，
            # 此时整块框是 MinerU 千分比**假定 1000** 推出来的，仍然落在整页尺度上。
            # 两种情况都要标 approx，前端画虚线而不是谎报「这就是这块字的精确位置」。
            approx_whole_block = False
            if block_type == "table" and float(rect["h"]) >= _TABLE_SPLIT_MIN_HEIGHT_RATIO:
                table_html = str(block.get("table_body") or block.get("table_structure") or "")
                # 可否拆格由 ``_split_table_into_cells`` 自己判（含 <img> / 单行 /
                # 单格过大或太空 → 返回空列表），这里只负责「拆不了就整块保留」。
                # 判据集中在拆分入口，避免两处各有一份「什么时候不能拆」的规则漂移。
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
                approx_whole_block = True

            entry: dict[str, Any] = {
                "page": page.page_no,
                "type": block_type or "text",
                "text": text,
                "rect": {**rect, "approx": True} if approx_whole_block else rect,
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
