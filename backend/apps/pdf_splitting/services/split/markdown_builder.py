"""分段 Markdown 重建：把每段的逐页取字结果重组成 AI 友好的 Markdown。

取字层两条路径的产出结构不同，这里统一收敛：
- 云端解析（MinerU / TextIn）：PageDescriptor.layout.blocks 带 block 类型、
  标题层级（MinerU text_level）与表格数据（MinerU table_body / TextIn
  table_structure，HTML）——按版面块重建标题 / 段落 / GFM 表格；
- 本地 OCR / PDF 文本层：只有页文本——按原文输出（保留换行），页间空行。

不存 DB（零迁移）：产物落 job 目录 analysis/segments_md.json，
经 job API 的 content_md 字段透出，供下游 AI 流程直接消费。

表格渲染与净化分别下沉到 ``md_table``（网格 → GFM）与 ``md_noise``（HTML/标题/
跨页重复行），本模块只负责「按页拼段 + 定位框 + 页偏移」。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .bbox import normalize_bbox, resolve_bbox_unit
from .md_noise import (
    drop_noise_lines,
    drop_stamp_boilerplate_lines,
    repeated_noise_lines,
    strip_html,
    title_already_present,
)
from .md_table import _TR_RE, GfmTable, drop_footer_table_lines
from .md_table import grid_col_count as _grid_col_count
from .md_table import grid_row_count as _grid_row_count
from .md_table import merge_continuation
from .md_table import parse_grid as _parse_grid
from .md_table import parse_table
from .md_table import table_cell_count as _table_cell_count
from .split_models import PageDescriptor, SegmentDraft

logger = logging.getLogger("apps.pdf_splitting")

_TITLE_TYPES = {"title", "text_level_title", "heading", "标题"}
_NOISE_TYPES = {"header", "footer", "page_number", "image", "equation", "watermark"}

#: 定位框的精度等级（随 rect 透出，前端据此决定视觉）。
#:
#: 为什么不能只有一个布尔 ``approx``：它同时被用来表示「整页近似框」与
#: 「表格均分的半格误差框」——这两种框的可信度差一个数量级。前端原来的注释
#: （``types.ts`` / ``PageCell.tsx``）全按「整页近似」写的，拿到的是半格框，
#: 于是律师看到一个占满半页的＂近似框＂，实际它只该盖住一格。拆成三档后，
#: 前端能分开画：
#: - ``exact``: 引擎真实返回的 bbox（MinerU/VL 原生，可信）
#: - ``cell`` : 表格拆分的推算框（半格误差，仅小表）
#: - ``page`` : 整页近似（整表未拆 / 坐标基本无意义）
#:
#: ``approx`` 字段**保留**：前端旧代码还在读它，删掉会让未跟进的前端白屏。
_PRECISION_EXACT = "exact"
_PRECISION_CELL = "cell"
_PRECISION_PAGE = "page"


def build_segments_markdown(
    drafts: list[SegmentDraft],
    pages: list[PageDescriptor],
    *,
    bbox_backend: str | None = None,
) -> list[dict[str, Any]]:
    """为每个分段生成 Markdown 描述（order / 页区间 / 正文 / 页偏移 / 定坐标块）。

    ``positioned`` 是「识别定位」的数据：每个正文块 + 它在原页上的归一化矩形。
    前端拿它做"点右栏字段 → 原文绿框"的双向对照。没有坐标的后端（本地 OCR）
    给空列表，而不是给一堆没框的块让前端白渲染。

    ``page_spans`` 是「按页搬运正文」的数据：``[{"page", "start", "end"}]``，
    左闭右开的**字符偏移**，指向 ``markdown`` 里该页产出的正文。只含实际产出
    非空内容的页；注入的段标题不计入。前端切/并段时按它精确切分，不用靠
    ``indexOf`` 猜（猜不中就会两视图漂移）。
    """
    page_by_no = {page.page_no: page for page in pages}
    results: list[dict[str, Any]] = []
    for draft in drafts:
        seg_pages = [page_by_no[no] for no in range(draft.page_start, draft.page_end + 1) if no in page_by_no]
        title = re.sub(r"\.pdf$", "", draft.filename or "", flags=re.IGNORECASE).strip() or "未命名材料"
        markdown, page_spans = _assemble_segment(title, seg_pages)
        results.append(
            {
                "order": draft.order,
                "page_start": draft.page_start,
                "page_end": draft.page_end,
                "markdown": markdown,
                "page_spans": page_spans,
                "positioned": build_positioned_blocks(seg_pages, bbox_backend=bbox_backend),
            }
        )
    return results


#: 拆格门槛：整表高度超过页面这个比例才拆。
#:
#: 为什么不是「有 table 就拆」：一两行的小表格拆开没有意义（每个框都很小，
#: 反而让绿框密度过高、读不清）。真正的痛点是「一个大框罩住十几行」、律师点不中
#: 具体某一格——那种表才值得拆。
#:
#: 实测（164 页备份卷宗 81 个带 table_body 的 table 块）：高度 >18% 的有 66 个，
#: 取 0.18 正好把最容易长成「整页大框」的那批筛出来。
#: 待核实（缺乏可复跑的存档）：旧注释写「152 个 table 块里 114 个高度 >25%」，本机 136 页
#: 缓存里只有 81 个 table 块，152/114 这两个数在现有数据上复现不出来。
_TABLE_SPLIT_MIN_HEIGHT_RATIO = 0.18

#: 拆成**单元格**的上限：超过就退回「按行拆」。
#:
#: 实测（164 页备份卷宗，81 个带 table_body 的 table 块）单元格数存在**明显断层**：
#:   流水类长表  247 / 256 / 256 / 274 / 295 / 306 / 307×4 / 974 / 1627 / 2046
#:   表单类中等表  65 / 68 / 69 / 80 / 88 / 92
#: 断层就落在 92 与 247 之间。取 120 做分界，两类都能干净分开。
#:
#: 为什么长表只拆到行：无差别逐格拆会让块数爆掉——同一份卷宗上模拟「三道上限全拆掉」，
#: 可定位块从 1482 涨到 8311（5.6 倍），前端渲染几千个绝对定位框会明显卡顿；
#: 而且流水的单格本身无点击价值——律师要看的是「哪一行」。
#: （旧注释记的「1147 → 6062（5.3 倍）」是更早一版的数字，在当前代码上已不可复现。）
_TABLE_CELL_SPLIT_MAX = 120

#: 拆成**行**的硬上限：再超过就整体保留。
#:
#: 当前它**仍会独立拦下东西**，不只是冗余保险：实测 p52（165 行）与 p63（285 行）
#: 这两个超长表在把 ``_TABLE_SPLIT_MAX_ROWS`` 抬成无穷后依然返回空列表，正是被这一道挡住。
#: （多数 52 行左右的流水表在 ``_TABLE_SPLIT_MAX_ROWS`` 那一关就被拦了，所以平时看不到
#: 这一层的效果。）
_TABLE_ROW_SPLIT_MAX = 80

#: 表格行数超过这个值就不再逐行/逐格拆分，整表保留一个块。
#:
#: 为什么不用「行高」做判据：p62 的 52 行流水表行高 0.0125 页（已用真实缓存核算：
#: bbox 高 0.65 页 ÷ 52 行），单看行高像是能点中的；但均分的前提是「所有行等高」，
#: 而卷宗表格几乎都有标题行 / 表头行 / 合并单元格。一旦行高不等，误差会累积。
#: 行高只能回答「框够不够大」，回答不了「偏没偏」。
#:
#: ## 误差是实测出来的，不是估的
#:
#: 把均分框叠到 p62 原图上量（可视化见 ``scripts/eval_table_split.py`` 的同行工具）：
#:
#: ======  ==========  ==========
#: 行号    偏移(px)    偏移(行)
#: ======  ==========  ==========
#: 1       -89         -3.9
#: 5       -76         -3.3
#: 20      -37         -1.6
#: 40      +17         +0.7
#: 52      +52         +2.3
#: ======  ==========  ==========
#:
#: 每行间距 22.7px。最大偏差 89px ≈ 4 个文字行高——律师点「第 1 行」会高亮到第 4.9 行。
#: 偏移曲线两端大、中间小且**符号会翻转**：表格顶部的标题/表头行比数据行高，均分把它们
#: 压扁后后续行整体前移；到末尾又因为强制对齐表格下边界而反向偏。这正说明「两端对齐、
#: 中间错位」，不可能靠一个统一系数修正。
#:
#: ## 为什么取 12（尝试过 20，已回退）
#:
#: 阈值只决定「拆不拆定位框」，与取字质量**完全正交**——8 个阈值 （0/3/6/12/20/30/80/999）
#: 对 7 页 golden 跑出的 CER 与 cell F1 全部一模一样（见 ``scripts/eval_table_split.py``）。
#: 所以这个数不是质量参数，只是「给律师画几个框」的取舍。
#:
#: ### 为什么 20 被回退
#:
#: 曾调到 20，目的是放行 p22 押品表（17 行×4 列）。实测发现**拆出来的框是错的**：
#: 均分假设「每列等宽」，而真实表格四列宽度差得很远——「模块」列只装「押品信息」4 个字，
#: 「参数项名称」列装「*该产证所属房产是否全部抵押」13 个字。等宽切开后，窄列的框盖到了右邻列、
#: 宽列的框只盖住左半截，律师点「参数项名称」那一格只能看到半句话。
#:
#: 叠加两个事实：
#:
#: 1. 行方向的均分同样有误差（p62 实测最大偏 89px ≈ 4 行）；
#: 2. 押品表这类「字段默认值表」对起诉材料几乎没有价值（不承载借贷事实、不含诉请依据）。
#:
#: 所以不再为它开特例：**宁可整表一个框，也不给一个盖不准的格**。
#: 12 行的依据：行数少时即使结构不均，行方向的累积误差仍在 1 行内；
#: 而列方向的问题对「<12 行」的小表影响也小（小表多为 2~3 列的字段表，列宽差异不悬殊）。
#:
#: 全卷 164 页的实测分布：62 张表整表保留，其中 9 张是「单格过大/整段正文」、
#: 7 张是「格子里有图片」——这两类即使把阈值抬高也拆不了，是结构性不可拆。
_TABLE_SPLIT_MAX_ROWS = 12

#: 行数超标时允许拆分的「稀疏表」例外：有字格占比低于这个值时仍然拆。
#:
#: 用意：稀疏表里大量空格不承载内容、律师不会去点，行数超标也值得拆。
#:
#: ⚠️ 这条分支在 164 页备份卷宗上**一次都没触发过**：27 个行数 >12 的表块里，
#: 有字率全部 ≥ 0.30（最低的是 p16 的 30×11 表，0.691）。所以它现在只是条备用规则，
#: 没有真实样本验证过「稀疏表拆出来准不准」。
#: （旧注释把 p22 押品表说成「17 行 × 4 列只填了 12 格，有字率 18%」的鼓励样本，
#: 实测 p22 是 17×4、68 个格位全部有字、有字率 1.000——正是它在 ``_TABLE_SPLIT_MAX_ROWS``
#: 那一关被拦下的原因。待核实（缺乏可复跑的存档）：需要一份真有稀疏长表的卷宗来验证这条分支。）
_FILLED_CELL_RATIO_BYPASS = 0.30


#: 拆格后**单格**面积的容忍上限（占页面面积比例）。
#:
#: 为什么不是「表格大就拆」：均分只有在「表格本身就是页面格局」时才成立。
#: 实测 p30 结婚证：整页被 MinerU 输出成 3 行 × 2 列的表格（bbox [47,4,988,821]），
#: 归一化后 0.941 × 0.817，按行列均分得到 6 个格子 —— 单格就占页面 12.8%，而真实的
#: 「姓名/身份证件号」那一栏只占页面窄窄一条。框比目标大一个数量级，等于没框。
#: 正常表单（p22 押品表 17×4，bbox [192,154,790,554]）单格只占 0.35%，差两个数量级，
#: 阈值取 4% 分得开。
_SPLIT_MAX_CELL_AREA_RATIO = 0.04

#: 拆格后**每个有字的格子**的平均字数上限（均值，不是单格最大值）。
#:
#: 均分的前提是「表格有完整的行列结构」。整页扫描件被误判成 2-3 行表格时，
#: 一个格子就装下一整段正文——那是 OCR 把整块正文拍平后的换行，不是表格结构，
#: 按行切必然错位。实测 p111 那个 1×6 的「表格」平均每格 121.5 字（单格最长 223 字），
#: 是全卷唯一被这条判据拦下的块。
#: 真表单每格只装一个字段值：p22 押品表平均 4.2 字，p19 流水表平均 20.9 字。
#:
#: 分母用「有字的格子」而不是「全部格子」：表单本来就大量空着，拿全部格子做分母
#: 会把真表单全卡掉。
#: 待核实（缺乏可复跑的存档）：旧注释举的「p30 首行 91 字 / p154 首行 88 字 / p111 单行 244 字 /
#: p162 首行 74 字」在现有缓存上对不上（实测 p30 首行 53 字、p154 首行 25 字、
#: p111 单行 223 字、p162 首行 13 字），且这条判据量的是**均值**而不是「首行」。
_SPLIT_MAX_CHARS_PER_CELL = 45


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
    四条否决条件都来自 164 页真实卷宗的实测（见常量注释），命中任一条就退回整块：
    **宁可少画一堆框，也不要画一堆指错地方的框。**

    四条判据在当前数据上**各自都仍在生效**（164 页备份卷宗 81 个 table 块的实际拦截分布：
    ``<img>`` 8 个 / 单行拆格 3 个 / 单格占比过大 5 个 / 每格字数超限 1 个；
    有意留的 37 个块通过了全部四条，另 25 个在更前面的 ``_TABLE_SPLIT_MAX_ROWS`` 已拦下）。
    """
    if "<img" in html.lower():
        # 格子里装着照片/印章：这是整页版面，不是表格。实测 p24/25/27/28/29/33/81/158。
        return False
    if row_count < 2 and not by_row_only:
        # 单行拆格：nv 列均分一行文字，横坐标纯属编造（p147 宗地图 [WDZ7] 就 1 行 1 格）。
        return False
    cell_count = max(1, row_count * col_count)
    if float(rect["w"]) * float(rect["h"]) / cell_count > _SPLIT_MAX_CELL_AREA_RATIO:
        # 单格占比过大 → 整页被当成表格（p30 结婚证 0.128、p154 0.056、p35 0.187），
        # 不是能点中的粒度。
        return False
    filled = [len(text) for _r, _c, _rs, _cs, text in grid if text]
    if filled and sum(filled) / len(filled) > _SPLIT_MAX_CHARS_PER_CELL:
        # 每格平均塞进一整段正文 → 行列是 OCR 换行拼出来的，不是表格结构。
        # 实测只有 p111 那个 1×6 块命中（均值 121.5 字）；p30/p154 是被上一条「单格占比」拦的。
        return False
    return True


def _filled_cell_ratio(
    *,
    grid: list[tuple[int, int, int, int, str]],
    row_count: int,
    col_count: int,
) -> float:
    """有字格**覆盖的格位**占全部格位的比例（用于「稀疏表例外」）。

    分子分母都用「格位」而不是「``<td>`` 个数」：合并单元格会让 ``len(grid)``
    远小于实际格位（实测 p44 面谈表只有 57 个 td、却占 29×7=203 个格位），
    拿 td 个数做分母会把它算成 28% 的「稀疏表」而误放行拆分。
    按 rowspan/colspan 累加才算得出真实的占位比例（p44 按格位算是 0.956）。
    """
    total = max(1, row_count * col_count)
    return sum(rowspan * colspan for _r, _c, rowspan, colspan, text in grid if text) / total


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

    实测 p22：17 行 × 4 列全部对齐，bbox=[192,154,790,554]，均分后每格 0.15 × 0.02 页
    （按 4:3 页面估约 149 × 24 px）。注：p22 自身因 17 行 > ``_TABLE_SPLIT_MAX_ROWS``
    且不满足稀疏例外，最终是整表保留，不拆；这里引它只是为了说明**均分本身对得上**。

    ## 为什么拆格而不是拆行

    律师的痛点是「我要点在『*房产证编号』这一格上，不要框住整张表」。
    只拆到行仍然要在一行四格里挑，还是点不准。拆到单元格才是真正可点击的粒度。

    ## by_row_only：中等表格只拆到行

    超过 ``_TABLE_CELL_SPLIT_MAX`` 格的中等表（几十行的表单/流水）逐格拆会把
    块数撑爆（同卷宗上模拟「三道上限全拆掉」：1482 → 8311，5.6 倍），且单格本身
    无点击价值。这类表按行合并成一个块，每行保留该行全部单元格的文字拼接——
    律师点中「哪一行」就够用了。

    ## 长表格不再拆（本次改造的核心）

    均分的坐标是**编造的**：律师点中第 37 行、实际高亮第 35 行，越往后偏得越多。
    行数超过 ``_TABLE_SPLIT_MAX_ROWS`` 时，这种误差已经不是「半格」而是「好几行」，
    框不仅没用还会误导——所以直接返回空列表，让调用方保留整表真 bbox
    （那个框是引擎真实返回的），并透出 ``table_rows``/``table_cols`` 告诉前端
    「这是多大的一张表」。

    例外：**稀疏表**（有字格占比 < ``_FILLED_CELL_RATIO_BYPASS``）行数超标仍然拆——
    理由是稀疏表大量空格不承载内容、律师不会去点，列宽均等时均分误差不叠加。
    ⚠️ 这条例外在 164 页备份卷宗上**从未触发**（27 个行数 >12 的表块有字率全 ≥0.30），
    所以它目前没有经过真样本验证。p22 押品表**不是**稀疏表（68 个格位全部有字，有字率 1.000），
    它就是被这条门槛挡在拆分之外的那一批。

    ## 返回空列表的条件（调用方保留原整块）

    - 行/列数算不出来
    - 行数超过 ``_TABLE_ROW_SPLIT_MAX``
    - **行数超过 ``_TABLE_SPLIT_MAX_ROWS`` 且不是稀疏表**（均分误差累积到好几行）
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
    # 行数超标就整表保留：均分的前提是「每行等高」，而卷宗表格几乎都有标题/表头/
    # 合并单元格，行高一旦不等误差就累积。
    # 行数少时累计误差本身也就 1~2 行，可以接受，所以判据落在行数而非行高上。
    # （这条在 164 页备份卷宗上拦下 25 个表块，是全卷拦截量最大的一道；
    #   p22 押品表、p62 流水表都是在这里被挡住的。）
    if (
        row_count > _TABLE_SPLIT_MAX_ROWS
        and _filled_cell_ratio(grid=grid, row_count=row_count, col_count=col_count) >= _FILLED_CELL_RATIO_BYPASS
    ):
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
                        # 按行均分推算，不是量出来的：半格误差，仅限小表
                        "precision": _PRECISION_CELL,
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
                    "precision": _PRECISION_CELL,
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

    每个块：``{page, type, text, rect:{x,y,w,h,approx,precision}}``。
    ``rect`` 统一为 0–1 归一化，前端直接 ``left: x*100%`` 就能画。
    坐标换算不出来（无页面尺寸 / 后端不给坐标）的块**整条丢弃**：
    没框的块在前端只能当普通文本展示，那还不如留在 markdown 里。

    整表未拆的 table 块额外带 ``table_rows`` / ``table_cols``（来自 HTML 的
    ``<tr>`` / 网格列统计）：既告诉前端「这是一张 52 行的表」，也解释它为什么
    只有一个整表框（行数超过 ``_TABLE_SPLIT_MAX_ROWS``，均分误差会累积到好几行）。
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
            # 整块保留的**大表格**（不拆或拆不了）：这个矩形是「整块内容的外接框」，
            # 不是某一块文字的位置。bbox 缺失时更糟——``layout`` 里没有页面尺寸，
            # 此时整块框是 MinerU 千分比**假定 1000** 推出来的，仍然落在整页尺度上。
            # 两种情况都要标 approx，前端画虚线而不是谎报「这就是这块字的精确位置」。
            table_html = ""
            if block_type == "table":
                table_html = str(block.get("table_body") or block.get("table_structure") or "")

            # 整表未拆（含矮到不值得拆 / 拆不了两种）：一个 table 块只有一个整表框，
            # 它不是「某块字的位置」而是「整张表的外接框」——精度就是 page 级。
            whole_table_kept = False
            if table_html:
                if float(rect["h"]) >= _TABLE_SPLIT_MIN_HEIGHT_RATIO:
                    # 可否拆格由 ``_split_table_into_cells`` 自己判（含 <img> / 单行 /
                    # 行数超标 / 单格过大或太空 → 返回空列表），这里只负责「拆不了就整块保留」。
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
                whole_table_kept = True

            entry: dict[str, Any] = {
                "page": page.page_no,
                "type": block_type or "text",
                "text": text,
                "rect": {
                    **rect,
                    # ``approx`` 保留原语义，且必须与 precision 一致：老前端读 approx、
                    # 新前端读 precision，两套视觉规则若给出不同答案会打架。
                    # 整表未拆 → 整页近似；有真实 bbox 的普通块 → 沿用 normalize_bbox 的判定。
                    "approx": True if whole_table_kept else bool(rect["approx"]),
                    "precision": _PRECISION_PAGE if whole_table_kept else _PRECISION_EXACT,
                },
            }
            # 整表未拆时透出结构信息：markdown 侧仍按行显示（HTML 拆行），
            # 但定位只能高亮整表框——前端要能告诉律师「这是 52 行的表」。
            # （164 页备份卷宗实测：1482 个可定位块中 57 个是这种整表框。）
            if whole_table_kept:
                entry["table_rows"] = _grid_row_count(table_html)
                entry["table_cols"] = _grid_col_count(_parse_grid(table_html))
            # Office 的结构定位（段落序 / 行列）一并透出：它对"定位"是确定的，
            # 而矩形只是整页近似。两者不冲突，前端按需用。
            locator = block.get("locator")
            if isinstance(locator, dict):
                entry["locator"] = locator
            out.append(entry)
    return out


def build_segment_markdown(title: str, pages: list[PageDescriptor]) -> str:
    """单段 Markdown（不需要页偏移时用这个）。"""
    markdown, _page_spans = _assemble_segment(title, pages)
    return markdown


@dataclass
class _Piece:
    """段内某页的一块正文，以及它与前一块之间的分隔符。"""

    page_no: int
    text: str
    join: str


def _assemble_segment(title: str, pages: list[PageDescriptor]) -> tuple[str, list[dict[str, Any]]]:
    """重建单段 Markdown，并给出每页正文在**最终字符串**里的字符区间。

    偏移必须按最终字符串算：注入的段标题、页间分隔符、跨页续表合并都会移动位置，
    「先 join 再 strip」会让偏移整体漂移。这里每块先 strip、分隔符显式记账，
    于是 ``markdown[span["start"]:span["end"]]`` 恰好等于该页产出的正文
    （含页内块间空行；跨页续表被合并时，本页贡献的就是接在上一表后面的那几行）。
    """
    page_pieces: list[tuple[int, list[Any]]] = []
    for page in pages:
        pieces = _page_pieces(page)
        if pieces:
            page_pieces.append((page.page_no, pieces))
    merged_pages = _merge_continuation_tables(page_pieces)
    noise = repeated_noise_lines([_piece_lines(pieces) for _page_no, pieces in page_pieces])

    flat: list[_Piece] = []
    for page_index, (page_no, pieces) in enumerate(page_pieces):
        for position, piece in enumerate(pieces):
            rendered = piece.render() if isinstance(piece, GfmTable) else drop_noise_lines(piece, noise)
            text = rendered.strip()
            if not text:
                continue
            if not flat:
                join = ""
            elif position == 0:
                join = "\n" if page_index in merged_pages else "\n\n"
            else:
                join = "\n\n"
            flat.append(_Piece(page_no=page_no, text=text, join=join))

    body_parts: list[str] = []
    spans: dict[int, dict[str, Any]] = {}
    cursor = 0
    for piece in flat:
        start = cursor + len(piece.join)
        body_parts.append(piece.join + piece.text)
        cursor = start + len(piece.text)
        if piece.page_no in spans:
            spans[piece.page_no]["end"] = cursor
        else:
            spans[piece.page_no] = {"page": piece.page_no, "start": start, "end": cursor}
    body = "".join(body_parts)

    prefix = f"# {title}"
    if body:
        prefix = "" if title_already_present(title, body.split("\n", 1)[0]) else f"# {title}\n\n"
    offset = len(prefix)
    page_spans = [
        {"page": span["page"], "start": span["start"] + offset, "end": span["end"] + offset} for span in spans.values()
    ]
    return prefix + body + "\n", page_spans


def _merge_continuation_tables(page_pieces: list[tuple[int, list[Any]]]) -> set[int]:
    """跨页续表合并（保守版）：返回「首块已并入上一页表格」的页下标集合。

    只在上一页**最后一块**就是那张表时才并：否则续表行会接到上一页的正文段落后面。
    合并后本页首块换成「只有数据行」的字符串，与上一页之间用单个换行衔接——
    用空行会把一张 GFM 表切成两张。

    上一页那张表必须在合并**前**定格成字符串：``merge_continuation`` 是原地扩充
    ``rows``，若留着对象等拼装时再渲染，上一页会把本页的续行一起渲染出来（正文重复）。
    连续三页以上的续表只定格一次，之后锚点仍是同一张表对象。
    """
    merged: set[int] = set()
    anchor: GfmTable | None = None
    anchor_at: tuple[int, int] | None = None
    for page_index, (_page_no, pieces) in enumerate(page_pieces):
        merged_here = False
        if anchor is not None and anchor_at is not None and pieces and isinstance(pieces[0], GfmTable):
            previous_pieces = page_pieces[anchor_at[0]][1]
            previous_index = anchor_at[1]
            snapshot = anchor.render() if isinstance(previous_pieces[previous_index], GfmTable) else None
            following = pieces[0]
            if merge_continuation(anchor, following):
                if snapshot is not None:
                    previous_pieces[previous_index] = snapshot
                pieces[0] = following.render_rows_only()
                merged.add(page_index)
                merged_here = True
        if pieces and isinstance(pieces[-1], GfmTable):
            anchor, anchor_at = pieces[-1], (page_index, len(pieces) - 1)
        elif not (merged_here and len(pieces) == 1):
            # 本页末尾不是表（也不是刚并进来的续行）→ 下一页不能再接着并
            anchor, anchor_at = None, None
    return merged


def _piece_lines(pieces: list[Any]) -> list[str]:
    """噪声统计只看文本块：表格行（``|`` 开头）本来就受保护，不必参与统计。"""
    return [line for piece in pieces if isinstance(piece, str) for line in piece.splitlines()]


def _page_pieces(page: PageDescriptor) -> list[Any]:
    """一页的正文块（``str`` = 文本/标题，``GfmTable`` = 表格）；版面块全空时退回页文本。"""
    blocks = (page.layout or {}).get("blocks") if isinstance(page.layout, dict) else None
    if isinstance(blocks, list) and blocks:
        pieces = [piece for piece in (_block_piece(block, page_text=page.text or "") for block in blocks) if piece]
        if pieces:
            return pieces
    text = _text_piece(page.text or "")
    return [text] if text else []


def _text_piece(raw: str) -> str:
    """文本块净化：剥原始 HTML 标签 + 剔夹带表格行里的页脚 + 剔整行印章套话。

    印章套话走**短语锚定**（不依赖页频），所以单页段、以及取字层清洗接不到的
    版面块路径都能清掉；跨页频次路在 ``_assemble_segment`` 里另行叠加。
    """
    return drop_stamp_boilerplate_lines(drop_footer_table_lines(strip_html(raw)))


def _block_piece(block: Any, *, page_text: str) -> Any:
    if not isinstance(block, dict):
        return ""
    block_type = str(block.get("type") or "").strip().lower()
    text = _text_piece(str(block.get("text") or ""))
    if block_type in _NOISE_TYPES or not text:
        return ""

    if block_type == "table":
        table = parse_table(str(block.get("table_body") or block.get("table_structure") or ""), page_text=page_text)
        return table if table is not None else text

    text_level: Any = block.get("text_level")
    if block_type in _TITLE_TYPES or text_level not in (None, "", 0, "0"):
        try:
            level = max(2, min(int(text_level) + 1, 6)) if str(text_level).lstrip("-").isdigit() else 2
        except (TypeError, ValueError):
            level = 2
        return f"{'#' * level} {text}"
    return text
