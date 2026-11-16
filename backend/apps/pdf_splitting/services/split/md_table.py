"""HTML 表格 → GFM 的纯函数层：网格对齐、表头判定、超宽降级、页脚行剔除。

从 ``markdown_builder`` 拆出来：那边还要管定位框（bbox 均分、精度分级），
表格渲染再长下去两件事会互相牵制。这里只做「HTML → 表格/文本」，不碰坐标。

网格解析（``parse_grid`` 及行列统计）也搬到这里，``markdown_builder`` 的定位框
逻辑反过来引用它——同一份 rowspan/colspan 占位算法只有一处实现，不会漂移。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from itertools import product

logger = logging.getLogger("apps.pdf_splitting")

_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

#: 单个单元格：捕获 rowspan / colspan 属性值（缺失即 1）
_CELL_WITH_SPAN_RE = re.compile(r"<t([dh])([^>]*)>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_ROWSPAN_RE = re.compile(r"rowspan\s*=\s*[\"']?(\d+)", re.IGNORECASE)
_COLSPAN_RE = re.compile(r"colspan\s*=\s*[\"']?(\d+)", re.IGNORECASE)

_WHITESPACE_RE = re.compile(r"\s+")
_DIGIT_RE = re.compile(r"\d")
_TH_RE = re.compile(r"<th\b", re.IGNORECASE)
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")

#: GFM 表格的列数上限，超过就降级为按行纯文本。
#:
#: 依据是 164 页真实卷宗 81 张表的**网格列数分布**（不是每行 td 数）：
#:   1×6 / 2×10 / 3×7 / 4×9 / 5×12 / 6×16 / 7×10 / 8×3 / 9×2 / 10×3 / 11×1 / 20×1 / **745×1**
#: 正常表最宽 20 列，唯一的异常表是 p151 不动产登记信息（745 列，引擎给了
#: ``colspan="101"`` + 数百个冗余空 ``<td>``）。30 落在 20 与 745 之间的空档里，
#: 既不会误伤任何一张真表，也拦得住怪兽行。
#:
#: 为什么降级而不是转置/分块：745 列里绝大多数是空格，转置后是 745 行噪声；
#: 按行拼接非空单元格能保住全部内容与行序，律师/下游 AI 至少读得到事实。
MAX_GFM_COLUMNS = 30

#: 表头词：首行任一短单元格命中就认定是表头。
#:
#: 用「包含」而不是「相等」：OCR 会吞字（实测 p51 表头被读成「易日期 对方账号」），
#: 「日期」「账号」仍能命中；一个格子里并了两列表头时也照样认得出来。
_HEADER_WORDS = (
    "序号",
    "日期",
    "姓名",
    "金额",
    "账号",
    "名称",
    "项目",
    "单位",
    "数量",
    "单价",
    "备注",
    "交易",
    "卡号",
    "余额",
    "对方",
    "摘要",
    "户名",
    "币种",
    "编号",
    "时间",
)
_HEADER_WORD_RE = re.compile("|".join(_HEADER_WORDS))

#: 表头词/短标签判定的长度上限：超过这个长度的单元格是正文，不是列名。
_HEADER_CELL_MAX_CHARS = 12

#: 数据行特征：长数字串（账号/证件号/单据号）或两位小数金额。
#: 真表头不会装账号，所以命中就**否决**表头判定——实测「*姓名 | 某某 | *证件号码 |
#: 4406…」这类表单行含表头词，但它是第一条记录，当表头会让下游把它当列名丢掉。
_DATA_NUMBER_RE = re.compile(r"\d{6,}|\d+\.\d{2}")
#: 「字段名:值」形态：冒号后面跟着值，说明这是表单里的一格数据而不是列名。
_FIELD_VALUE_RE = re.compile(r"[:：]")
#: 纯数字单元格（「1」「2017」）：带序号的记录行，不是列名行。
_PURE_NUMBER_RE = re.compile(r"^\d+$")
#: 长单元格占比达到这个值就判数据行：表头是「一行列名」，半数以上格子装着
#: 长文本（地址/正文/长值）时它是表单里的「标签+值」记录行。
#: 取 0.5 而不是「有一个长格就否决」：实测流水表 p52/p62/p63 的表头首格被 OCR
#: 粘上了表题（「通借记卡主活期账户交易明细表: 易日期 对方账号」），一格长、
#: 其余四格都是列名——那仍是表头，否决它会把诉请金额所在的流水表表头丢掉。
_HEADER_LONG_CELL_RATIO_MAX = 0.5

#: 页脚行的强标记：命中它才可能判为页脚（避免把「全是日期」的数据行误删）。
_FOOTER_STRONG_RE = re.compile(r"打印日期|打印时间|第\s*\d+\s*页|共\s*\d+\s*页")
#: 页脚里的打印日期单元格（「打印日期:20170720」「日期：20170822」）。
_FOOTER_DATE_RE = re.compile(r"^(?:打印日期|打印时间|日期|时间)?\s*[:：]?\s*\d{6,8}$")

#: 年份类数字：四位数字后紧跟「年」。不用裸四位数字——金额/账号/单号会混进来。
_YEAR_RE = re.compile(r"(?<!\d)(\d{4})\s*年")
#: 判「表格年份不可信」所需的最少年份样本数。
#:
#: 取 8：还款计划表有几十上百个年份，而普通合同只有 1~3 个日期（签订日/到期日），
#: 样本不足就不判——宁可漏掉一张坏表，也不要把正常合同降级成纯文本。
_MIN_YEAR_SAMPLES = 8
#: 表格里「不合理年份」的占比门槛（多数而非个别 OCR 错字）。
_BAD_YEAR_RATIO = 0.6
#: 同页纯文本允许的不合理年份占比上限：超过就说明纯文本与表格一样坏，
#: 拿不出独立证据，不降级。
_TEXT_BAD_YEAR_RATIO_MAX = 0.2
#: 合理年份下界：法律文书里早于 1900 的年份极少见。
_YEAR_MIN = 1900


def _span_value(pattern: re.Pattern[str], attrs: str) -> str:
    """从标签属性串里取 rowspan/colspan 值；缺失返回 ``"1"``。

    单独抽成函数是为了让 mypy 看清类型：``pattern.search(x) or [0, "1"]`` 把
    ``Match|None`` 和 ``list`` 混在一起，下标取值会报 Argument 1 has incompatible type。
    """
    found = pattern.search(attrs)
    return found.group(1) if found else "1"


def parse_grid(html: str) -> list[tuple[int, int, int, int, str]]:
    """把 HTML 表格解析成网格占位：``[(row, col, rowspan, colspan, text), ...]``。

    ## 为什么必须处理 rowspan / colspan

    实测 164 页备份卷宗里 **81 个带 table_body 的 table 块里有 66 个（约 81%）带合并单元格**
    （判据：``<td>`` 个数 < 网格格位数）。
    不带 span 处理就按「行列均分」切，框会整片错位。合并单元格的典型形态：

    ```html
    <tr><td rowspan="2">照片</td><td colspan="2">结婚申请,符合…</td></tr>
    <tr><td>登记机关</td><td>…</td></tr>
    ```

    首行只有 2 个 td，但第二行有 2 个 td，且首行的第二个 td 跨 2 列 ——
    若直接 `col_count = max(每行td数)`，会算出 2 列、把「结婚申请」那句
    按 1 列宽去画，实际它横跨 2 列。

    注意：上面这个 p29 结婚证页**整页都不拆**（首个命中判据是格子里有 ``<img>``），
    由 ``_split_is_trustworthy`` 拦下。span 算法仍然必须正确 —— 它对
    真表单（p22 押品表、p145 不动产权证）是决定框位置的唯一依据。
    （p22 虽然会进到拆格入口，但因 17 行 > ``_TABLE_SPLIT_MAX_ROWS`` 且不满足稀疏例外，
    最终也是整表保留；span 算法对真正被拆的 37 个表块仍然生效。）

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
            rowspan = max(1, int(_span_value(_ROWSPAN_RE, attrs)))
            colspan = max(1, int(_span_value(_COLSPAN_RE, attrs)))

            # 找到本行第一个未占用的列
            while occupied.get((row_index, col_cursor)):
                col_cursor += 1

            text = _TAG_RE.sub("", inner).strip()
            grid.append((row_index, col_cursor, rowspan, colspan, text))
            for dr, dc in product(range(rowspan), range(colspan)):
                occupied[(row_index + dr, col_cursor + dc)] = True
            col_cursor += colspan

    return grid


def grid_col_count(grid: list[tuple[int, int, int, int, str]]) -> int:
    """网格的真实列数（由最右侧被占用的列 +1 得出，不受 colspan 干扰）。"""
    return max((col + colspan for _r, col, _rs, colspan, _t in grid), default=0)


def grid_row_count(html: str) -> int:
    """网格的真实行数（HTML 的 <tr> 数；rowspan 不改变行数，只是格子更高）。"""
    return len(_TR_RE.findall(html))


def table_cell_count(html: str) -> int:
    """表格的单元格总数（用于决定拆到格还是拆到行）。"""
    return sum(len(_CELL_RE.findall(row_html)) for row_html in _TR_RE.findall(html))


def _cell_text(raw: str) -> str:
    """单元格文字：反转义 + 空白折叠。竖线留到渲染时再转义（判定要用原文）。"""
    return _WHITESPACE_RE.sub(" ", unescape(raw)).strip()


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|")


def looks_like_header(cells: list[str]) -> bool:
    """首行是不是表头。

    先否决（命中任一即判数据行）：
    - 行内有长数字串/金额（账号、证件号、发生额）——真表头不装这些；
    - 首个非空格是纯数字（带序号的记录行）；
    - 半数以上格子是长文本（表单的「标签+值」行，如「物业名称 | 某某详细地址」）。

    再认定（命中任一即是）：
    1. 任一短单元格是**纯标签**且含表头词（序号/日期/金额/账号…，「客户姓名:某某」
       这种带值的不算）；
    2. 全部非空格都是「短且不含数字」的标签（如「模块 | 参数项名称 | 输入项」）。

    为什么不能无条件把首行当表头：实测 45 段里 43 张表的首行是**数据**
    （「客户姓名:测试甲 | 客户编号:1000000000000001」「*姓名 | 测试甲 | *证件号码 | 1101…」），
    当表头会让下游按列抽取时把第一条记录当成列名丢掉。
    """
    filled = [cell for cell in cells if cell]
    if not filled:
        return False
    if any(_DATA_NUMBER_RE.search(cell) for cell in filled):
        return False
    if _PURE_NUMBER_RE.match(filled[0]):
        return False
    long_cells = sum(1 for cell in filled if len(cell) > _HEADER_CELL_MAX_CHARS)
    if long_cells / len(filled) >= _HEADER_LONG_CELL_RATIO_MAX:
        return False
    if any(
        len(cell) <= _HEADER_CELL_MAX_CHARS and _HEADER_WORD_RE.search(cell) and not _FIELD_VALUE_RE.search(cell)
        for cell in filled
    ):
        return True
    return all(len(cell) <= _HEADER_CELL_MAX_CHARS and not _DIGIT_RE.search(cell) for cell in filled)


def is_footer_row(cells: list[str]) -> bool:
    """这一行是不是混进表格的页脚（「打印日期:20170720 第2页」）。

    判据刻意要求「**每个**非空格都像页脚」且至少有一个强标记：
    流水数据行也可能全是日期，但只要有一个金额/账号格就不满足，不会被误删。
    """
    filled = [cell for cell in cells if cell]
    if not filled:
        return False
    if not any(_FOOTER_STRONG_RE.search(cell) for cell in filled):
        return False
    return all(_FOOTER_STRONG_RE.search(cell) or _FOOTER_DATE_RE.match(cell) for cell in filled)


def split_gfm_row(line: str) -> list[str]:
    """GFM 行 → 单元格文字（按未转义的竖线切，去掉首尾空串）。"""
    parts = _UNESCAPED_PIPE_RE.split(line.strip())
    return [part.strip() for part in parts[1:-1]]


def drop_footer_table_lines(text: str) -> str:
    """纯文本里夹带的表格行也剔页脚。

    为什么纯文本路径也要管：VL OCR 兜底（``source_method=ocr``、无 layout）直接
    返回 GFM 格式的表格文本，实测 p55/p69 的「| 日期：20170822 | | 第6页 |」
    就是这样混进正文的——只清 HTML 表格会漏掉这一半。
    """
    if "|" not in text:
        return text
    kept = [
        line for line in text.splitlines() if not (line.strip().startswith("|") and is_footer_row(split_gfm_row(line)))
    ]
    return "\n".join(kept)


def _bad_year_ratio(text: str, *, year_max: int) -> tuple[int, float]:
    years = [int(year) for year in _YEAR_RE.findall(text)]
    if not years:
        return 0, 0.0
    bad = sum(1 for year in years if year > year_max or year < _YEAR_MIN)
    return len(years), bad / len(years)


def table_years_unreliable(table_text: str, page_text: str, *, current_year: int | None = None) -> bool:
    """表格里的年份大比例不合理、而同页纯文本年份合理 → 这张表的数字不可信。

    实测 p151：表格 HTML 里 745 个年份有 732 个落在 2700–2759（还款计划日期被读错）。
    但**降级必须有独立证据**：MinerU 的 ``page.text`` 本身就是 ``table_body`` 去标签
    来的（实测 p151 两者逐字相同），同源数据一样坏时不能拿它当「纯文本是对的」的依据。

    另一个必须保守的理由：30 年按揭的还款计划**合法地**延伸到 2047 年，按
    「> 今年+1」算异常会把它们全判坏。所以本判据只在「同页纯文本独立且合理」时才成立，
    单看表格自身年份一律不降级。
    """
    year_max = (current_year if current_year is not None else date.today().year) + 1
    table_count, table_ratio = _bad_year_ratio(table_text, year_max=year_max)
    if table_count < _MIN_YEAR_SAMPLES or table_ratio < _BAD_YEAR_RATIO:
        return False
    text_count, text_ratio = _bad_year_ratio(page_text, year_max=year_max)
    if text_count < _MIN_YEAR_SAMPLES or text_ratio > _TEXT_BAD_YEAR_RATIO_MAX:
        return False
    return True


@dataclass
class GfmTable:
    """一张待渲染的表。``plain_lines`` 非 None 表示已降级为按行纯文本。

    ``has_header`` 记录首行是否**真**表头：跨页续表判定要用它区分
    「上一页的表还在继续」与「这是一张新表」。
    """

    width: int
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    has_header: bool = False
    plain_lines: list[str] | None = None

    def render(self) -> str:
        if self.plain_lines is not None:
            return "\n".join(self.plain_lines)
        if self.width <= 0:
            return ""
        lines = [
            "| " + " | ".join(_escape_cell(cell) for cell in self.header) + " |",
            "|" + " --- |" * self.width,
        ]
        lines.extend("| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in self.rows)
        return "\n".join(lines)

    def render_rows_only(self) -> str:
        """只渲染数据行（跨页续表合并后，本页贡献的就是这几行）。"""
        return "\n".join("| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in self.rows)


def _rows_as_plain_lines(rows: list[list[str]]) -> list[str]:
    return [" ".join(cell for cell in row if cell) for row in rows]


def parse_table(html: str, *, page_text: str = "") -> GfmTable | None:
    """HTML 表格 → GfmTable；解析不出任何有内容的行时返回 None（调用方走纯文本兜底）。

    列位置按**真实网格**放：colspan 的文字落在锚点列、其余被覆盖的列留空，
    rowspan 同理只在首行出现。GFM 没有 colspan，目标是**列不错位**——
    按「每行 td 个数」补空列会让合并单元格后面的金额整体左移一列（诉请金额的生命线）。
    """
    if not html:
        return None
    grid = parse_grid(html)
    if not grid:
        return None
    width = grid_col_count(grid)
    row_count = grid_row_count(html)
    matrix = [[""] * width for _ in range(row_count)]
    for row_index, col_index, _rowspan, _colspan, text in grid:
        matrix[row_index][col_index] = _cell_text(text)

    rows = [(index, row) for index, row in enumerate(matrix) if any(row) and not is_footer_row(row)]
    if not rows:
        return None
    kept = [row for _index, row in rows]

    if width > MAX_GFM_COLUMNS:
        logger.warning("表格网格 %d 列超过 GFM 上限 %d，降级为按行纯文本", width, MAX_GFM_COLUMNS)
        return GfmTable(width=width, plain_lines=_rows_as_plain_lines(kept))
    if table_years_unreliable(" ".join(" ".join(row) for row in kept), page_text):
        logger.warning("表格年份大比例异常而同页纯文本年份正常，降级为按行纯文本（%d 列）", width)
        return GfmTable(width=width, plain_lines=_rows_as_plain_lines(kept))

    first_index, first_row = rows[0]
    has_header = bool(_TH_RE.search(_TR_RE.findall(html)[first_index])) or looks_like_header(first_row)
    if has_header:
        return GfmTable(width=width, header=first_row, rows=kept[1:], has_header=True)
    # GFM 必须有表头行：首行是数据时插一行空表头，数据一行不丢。
    return GfmTable(width=width, header=[""] * width, rows=kept, has_header=False)


def merge_continuation(previous: GfmTable, following: GfmTable) -> bool:
    """把下一页首表并入上一表（保守判据），成功返回 True 并原地扩充 previous.rows。

    只认「列数相同 + 首行不是表头」：列数不同说明是另一张表（实测 579 包 8 处
    跨页相邻表格**全部**列数不同，包括结婚证、客户回单、测绘成果表——按宽松判据
    合并会把两份不相干的材料拼成一张表）。首行是表头则视为新表，不并。

    合并后表头沿用上一表的（GFM 只能有一行表头），续表的数据行接在其后。
    """
    if previous.plain_lines is not None or following.plain_lines is not None:
        return False
    if previous.width != following.width or following.has_header or not following.rows:
        return False
    previous.rows.extend(following.rows)
    return True
