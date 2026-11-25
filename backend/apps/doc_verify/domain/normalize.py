"""正文归一化：把「排版差异」和「实质改动」分开。

## 口径与双引擎比对同构

`apps/pdf_splitting/services/split/dual_engine.py` 的 `_normalize` 已经在替我们回答
「什么差异不算差异」：全角标点折成半角、Markdown/LaTeX/HTML 标记剥掉。本模块照它
那张标点表与那套噪声字符处理来做（`PUNCT_MAP` 与它的 `_PUNCT_MAP` 逐项一致，单测钉住）。

为什么不直接 import 它：那个模块服务「同一页两个 OCR 引擎的分歧」，拉进来会把
pdf_splitting 的依赖链（版面换算、页旋转、引擎适配）拖进 domain 纯函数层。
`dual_engine._MINERU_PERMILLE` 也是同一个理由各持一份而不互相 import。

## 两处刻意的不同

1. **保留换行**：`_normalize` 面对的是「一行」，可以把所有空白一抹到底；本模块要切
   段落（`split_paragraphs`），换行就是段落边界，抹掉就再也切不回来。所以这里只
   **压缩**水平空白（连续空格/制表符折成一个），换行原样保留。
2. **先切页再去页眉页脚**：页眉页脚唯一的可靠判据是「跨页重复同一行」，所以必须
   先按 `PAGE_SEPARATOR` 切页。没有分页符时只去页码行——硬猜页眉会把正文里重复
   出现的行（表格行、当事人姓名）一起删掉，那是拿内容换整洁。

## 分页符是三方共用的约定

`baseline.text` / `inbound.text` 逐页用 `\\f` 拼接（pdfminer 的惯例：每页文本后跟一个
换页符）。切页只此一份实现——`split_pages`，基线捕获与核对编排都必须调它，
各写一份就会在「末页多一个 `\\f`」这种地方错位一整页。
"""

from __future__ import annotations

import difflib
import re
from collections import Counter

# ── 分页 ────────────────────────────────────────────────────────────────────

#: 文本层的分页符。pdfminer 的 `extract_text` 每页文本后跟一个换页符，拼接后即此符。
PAGE_SEPARATOR = "\f"

# ── 标点宽度 ────────────────────────────────────────────────────────────────

#: 全半角标点归一表。与 `dual_engine._PUNCT_MAP` 逐项一致（单测对比，防口径漂移）。
#:
#: `，` vs `,`、`：` vs `:` 是后处理差异，不是改字；`　`（表意空格）折成普通空格，
#: 它同样只是排版。
PUNCT_MAP = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "、": ",",
        "；": ";",
        "：": ":",
        "？": "?",
        "！": "!",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "《": "<",
        "》": ">",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "—": "-",
        "…": ".",
        "％": "%",
        "＃": "#",
        "＠": "@",
        "＆": "&",
        "　": " ",
    }
)

# ── 剥标记 ──────────────────────────────────────────────────────────────────

#: Markdown 呈现符（**不含** `-`）：`#` 标题、`*` 强调、`|` 表格、`>` 引用、反引号、`_` 下划线。
#:
#: `-` 刻意留下：金额、日期、负数里它是内容的一部分；它作为列表符号时只出现在行首，
#: 由 `_LIST_BULLET_RE` 单独处理。
_MARKDOWN_MARKS_RE = re.compile(r"[#*`|>_~=]")

#: 行首列表符号（`- 第一条` / `• 事项`）。`1.` 这类编号不是列表符号，是内容（诉请项数靠它数）。
_LIST_BULLET_RE = re.compile(r"^\s*[-–—•·▪◦]\s+")

#: LaTeX 的「包一层但保留文字」命令（`\text{佛山市}` / `\underline{…}`）。
_LATEX_TEXT_CMD_RE = re.compile(r"\\(?:text|textbf|textrm|underline|mbox|mathrm)\s*\{([^{}]*)\}")

#: 其余 LaTeX 命令（保留参数文本由 `_LATEX_TEXT_CMD_RE` 处理）。
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")

#: 任意 HTML 标签（含自闭合）。只去标签本身，标签里的文字留着。
_TAG_ANY_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

# ── 空白与空行 ──────────────────────────────────────────────────────────────

#: 水平空白（空格、制表符、全角空格、不换行空格）压缩成一个半角空格。换行不在内。
_HORIZONTAL_SPACE_RE = re.compile(r"[ \t\u3000\u00a0]+")

#: 「有正文」的判据：至少一个汉字、字母或数字。整行只剩装饰符（`---`、`___`）的行丢掉。
_TEXT_CHAR_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff\u3007]")

# ── 页码行 ──────────────────────────────────────────────────────────────────

#: 纯页码行的形态闭集。它们不承载任何法律事实，两侧还经常一个有一个没有。
_PAGE_NUMBER_RES = (
    re.compile(r"^[-–—·•]?\s*\d{1,4}\s*[-–—·•]?$"),
    re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$"),
    re.compile(r"^第\s*\d{1,4}\s*页(\s*[,，/]?\s*共\s*\d{1,4}\s*页)?$"),
    re.compile(r"^共\s*\d{1,4}\s*页\s*第\s*\d{1,4}\s*页$"),
    re.compile(r"^(?:page|p\.)\s*\d{1,4}(\s*(?:of|/)\s*\d{1,4})?$", re.IGNORECASE),
)

#: 页眉页脚只看每页的头尾各几行。取 2：公文页眉多是「文号 + 密级」两行、页脚是
#: 「页码 + 落款」两行，再多就会啃到正文首段。
_HEADER_FOOTER_EDGE = 2


def split_pages(text: str) -> list[str]:
    """按 `PAGE_SEPARATOR` 切页，返回**原始**页文本（未归一化）。

    - 没有分页符：整段算一页（单页文书与「忘了按页拼」的文本都走这条）；
    - 空文本：0 页（不是「一页空白」，否则页数统计会凭空多一页）；
    - 末尾的 `\\f` 不算一页（拼接方按页尾加符，末页后面必然多一个）；
    - 中间的空页**保留**：位置就是页码，删掉会让后面每一页的页码整体前移。
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    pages = raw.split(PAGE_SEPARATOR)
    while pages and not pages[-1].strip():
        pages.pop()
    return pages


def normalize_text(text: str) -> str:
    """把正文归一化成「只保留承载法律事实的字符」，逐行拼接（空行不留）。

    做四件事：全角标点折半角、剥 Markdown/LaTeX/HTML 标记、水平空白压缩、去页码行与
    （有分页符时）跨页重复的页眉页脚。
    """
    lines: list[str] = []
    for page_lines in _normalized_pages(str(text or "")):
        lines.extend(page_lines)
    return "\n".join(lines)


def split_paragraphs(text: str) -> list[str]:
    """归一化后按空行/换行切段，丢弃空段。一段 = 一行非空文本。"""
    return [line for line in normalize_text(text).split("\n") if line]


def similarity(a: str, b: str) -> float:
    """两段文本的相似度（`difflib.SequenceMatcher.ratio()`，0–1）。

    `autojunk=False`：默认的「高频元素」启发式会把中文正文里反复出现的字（「的」「人」）
    当噪声剔除，长段落之间的相似度因此被系统性低估，0.92 的同段判据就会失效。
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _normalized_pages(text: str) -> list[list[str]]:
    """逐页归一化，返回每页的非空行（页眉页脚已去）。"""
    pages = [
        [line for line in (_normalize_line(raw) for raw in chunk.splitlines()) if line] for chunk in split_pages(text)
    ]
    return _drop_page_headers_and_footers(pages)


def _normalize_line(raw: str) -> str:
    """单行归一化。返回空串表示这行不承载内容（空行/页码行/纯装饰行）。"""
    line = _LIST_BULLET_RE.sub("", str(raw))
    # LaTeX：先去 `\text{…}` 一类包裹命令（保留括号里的内容），再丢掉其余反斜杠命令。
    # 顺序不能反：反了会先把 `\text` 当普通命令删掉，只剩 `{佛山市}` 再被当标点清掉。
    line = _LATEX_TEXT_CMD_RE.sub(r"\1", line)
    line = _LATEX_CMD_RE.sub("", line)
    line = _TAG_ANY_RE.sub("", line)
    # `$` 是公式定界符，`\_` 是 MinerU 的转义下划线，花括号是 LaTeX 分组符——都不是正文。
    line = line.replace("$", "").replace("\\_", "_").replace("{", "").replace("}", "")
    line = _MARKDOWN_MARKS_RE.sub("", line)
    line = _HORIZONTAL_SPACE_RE.sub(" ", line.translate(PUNCT_MAP)).strip()
    if not line or _is_page_number_line(line):
        return ""
    if not _TEXT_CHAR_RE.search(line):
        return ""
    return line


def _is_page_number_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in _PAGE_NUMBER_RES)


def _drop_page_headers_and_footers(pages: list[list[str]]) -> list[list[str]]:
    """去掉「每页头尾都重复」的行（页眉页脚）。

    只在有 2 页以上、且该页够长（头尾各 2 行不重叠）时才动手：页数少或页太短时
    「重复」没有统计意义，删错就是丢正文。
    """
    if len(pages) < 2:
        return pages
    edge = _HEADER_FOOTER_EDGE
    seen: Counter[str] = Counter()
    for page in pages:
        if len(page) < 2 * edge:
            continue
        seen.update(page[:edge] + page[-edge:])
    repeated = {line for line, count in seen.items() if count >= 2}
    if not repeated:
        return pages
    return [page if len(page) < 2 * edge else _drop_repeated_edges(page, repeated) for page in pages]


def _drop_repeated_edges(page: list[str], repeated: set[str]) -> list[str]:
    edge = _HEADER_FOOTER_EDGE
    keep: list[str] = []
    for index, line in enumerate(page):
        is_edge = index < edge or index >= len(page) - edge
        if is_edge and line in repeated:
            continue
        keep.append(line)
    return keep
