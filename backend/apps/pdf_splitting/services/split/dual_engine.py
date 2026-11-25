"""双引擎交叉校验：找同一页被两个 OCR 引擎识别出的**分歧**，供人工裁决。

## 为什么「不投票」

最初的设想是「多引擎跑一遍，采信票数多的」。真实卷宗实测推翻了它：

- 第 31 页「张某某」：MinerU ✅ / PaddleOCR-VL ✅ —— 一致且都对
- 第 38 页「张某某」：MinerU ❌ / VL ❌ —— **两引擎一致地错**（真相是「张某某」）
- 第 38 页「张三丰」：MinerU ✅ / VL 认成「张四丰」 ❌ —— 分歧，暴露了真问题

（MinerU 侧的这半是可以复跑的：164 页备份卷宗缓存的 p31 文本内含该姓名、p38 内含错写
与「张三丰」。VL 侧那一半的原始响应不在仓库里，待核实（无存档，无法复跑）。）

也就是：

    一致 ≠ 正确（可能一起错）；分歧 = 确定的「这里有问题」信号

投票只能在「分歧」时起作用，而分歧恰恰是最不需要投票的场景（人一看就知道要核对）。
而在「一致」时投票什么也没做，却给人一种「多引擎都同意，肯定对」的错觉——这正是
第 38 页那种高置信度错答案的来源。

所以本模块**只做一件事**：把分歧找出来、分好级、带上上下文。不做自动采信，
不产出「最终文本」。裁决权留给人。

## 为什么不用 cross_page_consistency 的频次判据

那个模块判「同一份卷宗里同一段文字应该只有一种写法」，靠的是**频次悬殊**（低频写法
是高频写法的零头）。多引擎场景没有「出现多少次」这个概念——每页每个引擎只给一次结果，
两票对一票说明不了哪个对。硬套频次门槛只会把真分歧过滤掉。

## 对齐策略

两个引擎的**行切分方式不同**：VL 输出 Markdown（``#`` 标题、``|`` 表格行），
MinerU 输出版面段落。所以不能按行号硬对齐，要用 difflib 做序列对齐，
只把 ``equal`` 之外的区段当候选分歧。

## 为什么还要做定位归一化

分歧文本是对的，但律师拿到「张三丰 / 张四丰」还得自己在整页扫描件里找这两个字——
两个引擎**都带坐标**（MinerU ``ParsedBlock.bbox``、VL ``block_bbox``），不接进 UI
等于白扔。可两家的坐标系不同（MinerU 千分比、VL 绝对像素，页面尺寸来源也不同），
所以先把坐标统一成前端能直接画的 0–1 矩形（``EngineBlock.rect``），再按文本包含
关系把一条分歧挂回两引擎各自的块（``link_disagreement_to_blocks``）。

坐标宁可**不给**也不编：算不出可信比例时返回空 ``rect`` + ``approx=True``，
前端据此不画框。画错的框比没有框更坏——会让人指着 A 处说 B 处的内容。
"""

from __future__ import annotations

import difflib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from apps.document_parsing.protocols.document_parser_protocol import BLOCK_TYPE_UNKNOWN

from .page_rotation import derotate_rect, page_angle

#: 分歧上下文截断长度。律师看的是「这一行大概在说什么」，不是全文。
_CONTEXT_MAX_CHARS = 120

#: 视为「无意义差异」的字符：Markdown 标记与各类空白。
#: 两引擎一个输出 ``# 标题``、一个输出 ``标题``，这不是识别分歧，是排版差异。
_NOISE_CHARS_RE = re.compile(r"[#*`|>\-_~=\s\u3000]+")

#: 任意 HTML 标签（含自闭合）。用来判断「这一行去掉标签后还剩不剩字」。
#: 故意不限定标签名：VL 的写法会变（`<div><img/></div>` / `<img>` / `<br/>`），
#: 维护白名单迟早漏一个。
_TAG_ANY_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

#: LaTeX 的「包一层但保留文字」命令，如 ``\text{佛山市}`` / ``\underline{…}``。
#: 先把它换成里面的内容，剩下的命令（``\frac`` 之类）再整体丢掉。
_LATEX_TEXT_CMD_RE = re.compile(r"\\(?:text|textbf|textrm|underline|mbox|mathrm)\s*\{([^{}]*)\}")

#: 其余 LaTeX 命令（保留参数文本由 ``_LATEX_TEXT_CMD_RE`` 处理）。
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")

#: 全半角标点归一表。``，`` vs ``,``、``：`` vs ``:`` 是后处理差异，不是认错字。
_PUNCT_MAP = str.maketrans(
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

#: 只承载排版、不承载法律事实的「呈现符」闭集（按归一化后**仍存活**的字符列）。
#:
#: 两串的差异全部落在这里时，两引擎认出的字与数字是一样的，只是标点/装饰符不同 → low。
#: 半角 ``- ~ = | > # * _`` 已被 ``_NOISE_CHARS_RE`` 当 Markdown 噪声清掉，所以这里
#: 只列它们的**全角对应形**（``－ ～ ＝ ｜ ＊ ＿``）——同一个字符不该因为宽度不同而
#: 一边被当噪声、一边被当 high 级实质分歧。
#:
#: **刻意不含** ``× ÷ ＋ + ☐ ☑ ☒ □ ✓ ✔ ✗ ％ % ￥ ＠ @ ＆ &``：勾选框的选中态
#: （``☒仲裁`` vs ``☑诉讼``）与公式运算符、百分号、货币符都是合同意思表示的一部分，
#: 把它们当排版差异降级会让真分歧静默消失——那比多报一条 high 坏得多。
_PRESENTATION_MARKS = frozenset(
    ".,:;!?()[]<>\"'"  # 句读与括引（全角形已被 _PUNCT_MAP 折成这些）
    "/／＼∕"  # 斜线：日期分隔，也是整块拼接时本模块自己加的分隔符
    "．·•‧"  # 句点与间隔号
    "–―－"  # 各类横线
    "▲△▼◆■●○"  # 装饰性项目符号（银行合同用它标条款，重复/漏一个不改语义）
    "｜＊～＿＝"  # 全角形，其半角对应字符已被当噪声清掉
    "‖│┃"  # 竖线分隔
)

#: 唯一标识锚点：18 位身份证 / 15 位旧身份证 / 12 位以上连续数字（账号、卡号）。
#:
#: 为什么这些位置错了最致命：姓名与身份证号同段出现时，姓名是**直接绑定**到唯一
#: 自然人的。这种位置的识别分歧必须给到 high，不能和普通正文一样淹在列表里。
_ANCHOR_RE = re.compile(r"\d{17}[\dXx]|\d{15}|\d{12,}")

#: 行级差异里，两串的相似度下限。
#:
#: 低于这个值就不当「同一行的两种写法」，而当「两个不同的行」（多为版面切分差异）。
#: 硬把它们凑成一对只会制造无用告警。
_LINE_SIMILARITY_FLOOR = 0.5

#: 把一块差异当成「只是切行不同」所需的最小行数比（短边/长边）。
#:
#: 光看相似度不够：一整块表单内容被一边当整段、另一边拆成很多行时，字符相似度
#: 依然可能过线，但行数差几倍就说明两边对这块版面的理解不同（一个当整段、
#: 一个当表格拆行），不是「同一段落换个换行位置」。取 0.5：行数差一倍以内才忽略。
#:
#: 待核实（缺乏可复跑的存档）：旧注释举的「实测 p44 左 2 行 vs 右 9 行（比 0.22）、整块相似度 0.558」
#: 无法复跑——它需要同一页的两引擎原文，而仓库里没有 PaddleOCR-VL 的响应存档。
_CHUNK_LINE_RATIO_FLOOR = 0.5

#: MinerU 千分比坐标的基准：它把页宽/页高各视作 1000。
#: 与 ``split/bbox.py`` 的 ``_MinerU_PERMILLE`` 是同一个约定（那个模块服务切分预处理，
#: 本模块服务双引擎对照，故各自持有一份而不互相 import）。
_MINERU_PERMILLE = 1000.0

#: 判定「这是绝对像素而不是千分比」的量级门槛。
#:
#: 取 2000 而不是 1000：千分比的理论上界就是 1000，但引擎会给越界值
#: （多边形外接矩形、跨页拼接图），若拿 1000 当门框，一个 ``[209, 89, 1066, 118]``
#: 这种轻微越界的千分比框就会被误判成像素、再被页宽除成一条细线。
#: 2000 给了 2 倍容差：常见页面（A4/Letter，612×792 / 595×842）上的真实像素框
#: 必然远超 2000，而千分比框即使翻倍也不会误触。
_MINERU_ABSOLUTE_PIXEL_FLOOR = 2000.0

ENGINE_MINERU = "mineru"
ENGINE_PADDLEOCR_VL = "paddleocr_vl"
ENGINE_TEXTIN = "textin"

#: 引擎展示名（前端要给人看，不能直接甩 snake_case）。
ENGINE_LABELS = {
    ENGINE_MINERU: "MinerU",
    ENGINE_PADDLEOCR_VL: "PaddleOCR-VL",
    ENGINE_TEXTIN: "TextIn",
}

KIND_CHAR = "char"
KIND_LINE = "line"
KIND_MISSING = "missing"

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

#: MinerU 的表格块类型（小写比较）。表格不参与逐字比对、也不产出对照框，
#: 理由见 ``_compare_pair`` 与 ``normalize_mineru_blocks``。
#:
#: **对外共享**：``dual_engine_runner`` 在构造逐页文本时用它剔表格块。两边必须
#: 用同一份词汇，否则一边剔了、另一边没剔，表格又会从另一个入口流进比对。
MINERU_TABLE_BLOCK_TYPES = frozenset({"table"})


@dataclass(frozen=True)
class EngineVariant:
    """某引擎对同一处的识别结果。

    ## 为什么既有 `text` 又有 `full_text`

    `text` 是**摘要**（截到 120 字），列表里扫一眼够用；但它带着省略号，
    前端拿它去正文块里做 `includes` 定位会**必然失败**（正文是完整文本），
    表现为「点了采用/修改没反应」。

    `full_text` 是这一行的完整原文。它让两件事成为可能：
    1. 前端按完整文本定位到对应的正文块；
    2. 律师在面板里能看到全文——不看清就没法判断哪一侧对。

    体积代价可接受：实测 332 条分歧 × 2 侧 × 平均约 300 字 ≈ 200KB。
    """

    engine: str
    text: str
    #: 完整原文（不截断）。缺省时退回 `text`，兼容旧产物。
    full_text: str = ""

    @property
    def body(self) -> str:
        """取完整原文；旧产物没有 `full_text` 时退回摘要。"""
        return self.full_text or self.text

    @property
    def label(self) -> str:
        return ENGINE_LABELS.get(self.engine, self.engine)


@dataclass(frozen=True)
class EngineDisagreement:
    """一处引擎分歧。

    只在**确实有分歧**时产生；两引擎一致的行不会出现在结果里——一致不是「没有问题」
    的证明（见模块 docstring），但也没法靠比对再榨出信息，列出来只会稀释真分歧。
    """

    page_no: int
    kind: str
    severity: str
    variants: list[EngineVariant]
    context: str
    #: 该处是否命中唯一标识锚点（身份证号/账号）。命中即说明这里是「绑定到具体人/账户」
    #: 的关键字段，前端应优先展示。
    anchor_hit: bool = False
    #: 两串的相似度（0-1），供前端排序用；missing 类为 0。
    similarity: float = field(default=0.0)


@dataclass(frozen=True)
class EngineBlock:
    """某引擎在某一页上的一个块（已把坐标归一成 0–1）。

    存在的理由：前端「双框对照」要画两个引擎各自的框，而两家的原始坐标互不兼容
    （MinerU 千分比 0–1000 / VL 绝对像素、页面尺寸来源也不同）。归一到同一个结构后，
    前端只认一种画法，不必知道数据是从哪个引擎来的。

    为什么 ``rect`` 单独用 dict 而不是四个 float：前端直接 ``x*100%`` 定位，
    缺尺寸时又要能“整个不画”——空 dict 是最省事的“无坐标”表达，
    不会像 ``x=0,y=0,w=1,h=1`` 那样被误当成真有个满页框。
    """

    engine: str
    page_no: int
    text: str
    #: 归一化 0–1 矩形 ``{"x", "y", "w", "h"}``；坐标不可信时为空 dict。
    rect: dict
    block_type: str
    #: 坐标是否为近似推出来的/干脆没有。缺页面尺寸时置 True，
    #: 前端据此不画框（宁可少画一个框，也不能画错一个框）。
    approx: bool = False


def disagreement_key(item: EngineDisagreement) -> tuple[int, str, str]:
    """一条分歧的稳定标识：``(页码, 类型, 上下文)``。

    只用于内部的“分歧 → 块矩形”配对，与前端 `draft/engine.ts` 的
    `disagreementKey` 不是同一个用途（那边面给“已核对”做勾选键）。
    """
    return (item.page_no, item.kind, item.context)


def _normalize(text: str) -> str:
    """把一行文本归一化到「只保留有语义的字符」，用于判断差异是否真实。

    去掉 Markdown 标记、各类空白，并把全角标点折成半角——这三类差异都是
    **排版/后处理**造成的，不是 OCR 认错字。不归一化会把它们全部报成分歧，
    真正的错字就被淹了。

    除 Markdown 外，还要剥掉下面两类——它们是实际跑出来的最大噪声源（整卷双引擎
    比对时 high 大量集中在「一个加了公式命令」「一个多了标签」这类排版差异上）：

    - **LaTeX 公式**：VL 会把重点内容包成 ``$ \\underline{\\text{…}} $``，
      MinerU 给纯文本。剥掉后两边一致，不会因为「一个加了下划线命令」就报 high。
    - **HTML 标签**：VL 把表格/印章输出成 ``<table>``/``<div><img></div>``，
      MinerU 给纯文本或整表块。标签本身不承载文字内容。（``<td>`` 里的文字要留下，
      所以只去标签、不去标签内的文本。）
    """
    raw = str(text or "")
    # LaTeX：先去 `\text{…}` 一类的包裹命令（保留括号里的内容），再丢掉其余反斜杠命令。
    # 顺序不能反：反了会先把 `\text` 当普通命令删掉、只剩 `{佛山市}` 再被当标点清掉。
    raw = _LATEX_TEXT_CMD_RE.sub(r"\1", raw)
    raw = _LATEX_CMD_RE.sub("", raw)
    # HTML 标签：只去标签本身，保留包在里面的文字
    raw = _TAG_ANY_RE.sub("", raw)
    # `$` 与 `\_`：公式定界符与 MinerU 的转义下划线（`\_\_\_` vs `_____`）
    raw = raw.replace("$", "").replace("\\_", "_")
    # LaTeX 的分组花括号：`\underline{\text{X}}` 剥掉 `\text` 后还剩 `{X}`，
    # 花括号不是文字内容，直接去掉（不影响正文里的全角「｛｝」，那两个已被折成半角但
    # 正文出现花括号的概率极低，且两边都会同样处理）。
    raw = raw.replace("{", "").replace("}", "")
    return _NOISE_CHARS_RE.sub("", raw.translate(_PUNCT_MAP))


def is_markdown_table_line(line: str) -> bool:
    """这一行是否是 Markdown/HTML 表格行（按形态判，不看语义）。

    认三种形态，都来自 PaddleOCR-VL 的实际输出：

    · 以 ``|`` 开头——GFM 表格行（``| 姓名 | 金额 |``）；
    · 纯分隔行（``| --- | --- |``）——同样以 ``|`` 开头，一并被上面那条盖住；
    · 去掉 HTML 标签后以 ``<table`` 开头——VL 有时直接把整表输出成 ``<table>``。

    **不**把「正文里偶尔出现一个竖线」的行当成表格：``|`` 在中文正文里是分隔符，
    按「含 | 即表格」会把正常句子整片丢弃，那才是真漏数据。

    **对外共享**：``dual_engine_runner`` 在没有块可用时用同一道过滤切 MinerU 文本。
    两个引擎必须用**同一个**表格形态判据，否则一侧剔了另一侧没剔，结果还是一堆假分歧。
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        return True
    return stripped.lower().startswith("<table")


def _split_meaningful_lines(text: str) -> list[str]:
    """把一页文本切成「有意义」的行。

    空行、纯 Markdown 分隔行（``| --- |``）、纯表格分隔符都丢掉——它们不承载内容，
    两引擎在这上面几乎必然不同（VL 输出 GFM 表格，MinerU 可能是段落），
    留着只会制造噪声。

    **表格行也丢掉**（见 :func:`is_markdown_table_line`），理由见 :func:`_compare_pair`：
    表格内容不参与逐字比对。
    """
    out: list[str] = []
    for raw in str(text or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        # 纯表格分隔行：|---|---| 或 --- 这类
        if re.fullmatch(r"[|\-:\s]+", stripped):
            continue
        # 表格行：两边输出形态根本不同，逐字比对没有意义（详见 _compare_pair）
        if is_markdown_table_line(stripped):
            continue
        # 没有可见文字的纯标签行（例如 ``<div style="..."><img ... /></div>``）。
        #
        # VL 会为每枚印章/照片输出这样一行，而 MinerU 把这类内容归到 image 块、
        # 正文里根本没有这一行。两边都不算「认错字」，但行数对不上就会在 difflib 里
        # 变成一串 insert/delete——一页就能刷出一批 low「缺行」，把真分歧淹掉。
        #
        # 判据不写具体标签名：去掉所有标签后是否还剩可见字符。这样 <img>、
        # <div><img/></div>、<br/> 等任意组合都能一笔盖住，将来 VL 改写法也不用维护白名单。
        # （图片本身已存在 PaddleOCRApiResult.images / EngineBlock 里，正文比对不必再算。）
        if _TAG_ANY_RE.search(stripped) and not _normalize(_TAG_ANY_RE.sub("", stripped)):
            continue
        # 归一化后什么都不剩的行（例如只有 Markdown 标记）也丢掉
        if not _normalize(stripped):
            continue
        out.append(stripped)
    return out


def _one_char_diff(left: str, right: str) -> bool:
    """两串是否只差一个字（同长度）。

    用 ``difflib`` 而不是逐位比较：两引擎可能在同一个语义行内部对空白/标点的
    处理不同，逐位比较会把「只差一个真实字符」误判成「多处不同」。
    """
    if len(left) != len(right):
        return False
    if left == right:
        return False
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    return (
        all(tag == "equal" for tag, *_ in matcher.get_opcodes() if tag != "replace")
        and sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag == "replace") == 1
    )


def _anchor_hit(text: str) -> bool:
    """该行是否含唯一标识锚点。"""
    return bool(_ANCHOR_RE.search(str(text or "")))


def _anchors_nearby(lines: list[str], index: int, *, window: int = 2) -> bool:
    """``lines[index]`` 附近（含自身）是否出现唯一标识锚点。

    为什么要看邻域而不是只看本行：卷宗表单里「姓名」与「身份证号码」经常是
    **相邻两行**（表格里甚至分成两格）。只看本行会把「张三丰/张四丰」这种
    绑定到具体自然人的姓氏分歧降级成 medium，而它和普通正文的分歧不是一个量级。

    window=2 是经验值：再远就不该算「同一字段区」了。
    """
    start = max(0, index - window)
    end = min(len(lines), index + window + 1)
    return any(_anchor_hit(lines[i]) for i in range(start, end))


def _truncate(text: str, limit: int = _CONTEXT_MAX_CHARS) -> str:
    """截到指定长度，供律师快速扫一眼「这一行大概在说什么」。

    **先剥 HTML 标签再截断**，顺序不能反：VL 会把整页内容包成一整个
    ``<table border=1 style=...><tr><td style=...>…``，直接截 120 字全是标签，
    律师看到的就是一屏 ``<td style='text-align: center;'>``——等于什么也没看到。
    剥完标签再截，才能把有限的字数用在真实内容上。
    待核实（缺乏可复跑的存档）：这条与 p44 样例同源，需 VL 原文才能复跑。

    同时把连续空白压成一个空格：HTML 表格展开后单元格之间会挤出一串空白，
    不压就白占预算。
    """
    raw = _TAG_ANY_RE.sub(" ", str(text or ""))
    # 字面量 ``\n``（反斜杠 + n）来自 PaddleOCR-VL：它把换行写成了转义序列，
    # 没有真换成 0x0A。不转掉的话律师看到的是 ``逾期本金:\n654.52元``，
    # 会以为那是识别出来的字符——实测 12 条 high 全部带着这个噪声。
    raw = raw.replace("\\n", " ").replace("\\t", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw if len(raw) <= limit else raw[: limit - 1] + "…"


def _flanked_by_digits(text: str, start: int, end: int) -> bool:
    """``text[start:end]`` 这段差异是否被两个数字夹在中间。"""
    return start > 0 and end < len(text) and text[start - 1].isdigit() and text[end].isdigit()


def _is_presentation_only_diff(left: str, right: str) -> bool:
    """两串（已归一化）的差异是否**全部**只是呈现符，不含任何字、数字或语义符号。

    为什么不能只看「差异字符是不是标点」：``146.75`` 与 ``14675`` 的差异也只是一个
    句点，但那是**小数点**——金额差一百倍。所以再加一道数字夹逼判据：差异段两侧都是
    数字时，这个标点可能是小数点/千分位/份额分隔（``1/2`` vs ``12``），一律不算排版。
    宁可把这类留在 high，也不能把诉讼金额的分歧降成 low。

    入参必须是 :func:`_normalize` 之后的串：全半角标点与空白已经在那里被折平，
    剩下的差异才轮到本判据分级。
    """
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    saw_diff = False
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        saw_diff = True
        marks = left[i1:i2] + right[j1:j2]
        if not all(ch in _PRESENTATION_MARKS for ch in marks):
            return False
        if _flanked_by_digits(left, i1, i2) or _flanked_by_digits(right, j1, j2):
            return False
    return saw_diff


def _classify_pair(left: str, right: str, *, anchor: bool) -> tuple[str, str, float] | None:
    """给一对「同一位置的两种写法」定 kind / severity / 相似度。

    返回 None 表示归一化后其实没差异（纯排版差异），不该报。
    """
    norm_left = _normalize(left)
    norm_right = _normalize(right)
    if norm_left == norm_right:
        return None

    matcher = difflib.SequenceMatcher(None, norm_left, norm_right, autojunk=False)
    similarity = matcher.ratio()
    # 差异只剩呈现符时降为 low：律师要的是「哪个字认错了」，不是「哪个逗号是全角」。
    # 锚点也不能把它抬回 high——账号/证件号本身没变，变的只是它前后的标点。
    presentation_only = _is_presentation_only_diff(norm_left, norm_right)

    if _one_char_diff(norm_left, norm_right):
        # 差一个字就是形近字/漏笔/多笔的典型形态。
        # 命中身份证号等锚点的位置升级为 high——姓名与号码绑定处的单字错最致命。
        if presentation_only:
            return KIND_CHAR, SEVERITY_LOW, similarity
        return KIND_CHAR, (SEVERITY_HIGH if anchor else SEVERITY_MEDIUM), similarity

    if similarity >= _LINE_SIMILARITY_FLOOR:
        # 同一行里差了两个以上字符：可能是漏字、串行，也可能是两引擎切行不同。
        # 一律 high——这一级已经超出「一眼能判断」的范围，必须人看。
        return KIND_LINE, (SEVERITY_LOW if presentation_only else SEVERITY_HIGH), similarity

    # 相似度太低：不再当「同一行的两个版本」，交给调用方按 missing/整行差异处理。
    return None


def compare_pages(
    engine_pages: dict[str, dict[int, str]],
    *,
    min_severity: str | None = None,
) -> list[EngineDisagreement]:
    """比对多个引擎的逐页文本，产出分歧列表。

    Args:
        engine_pages: ``{引擎名: {页码: 该页文本}}``。引擎名用本模块的 ``ENGINE_*``
            常量。**至少两个引擎**才有比对意义。
        min_severity: 只返回不低于该等级的分歧（``low`` < ``medium`` < ``high``）。
            None 表示全返回。

    Returns:
        按 (severity 降序, 页码升序, 相似度升序) 排序的分歧列表。
        相似度低的排前面——越不像越可疑。
    """
    engines = [name for name, pages in engine_pages.items() if pages]
    if len(engines) < 2:
        return []

    # 取所有引擎涉及过的页码，逐页比对。
    # 某引擎完全没识别这一页（例如降级失败）时，它在对比中缺席——
    # 这种情况由 _compare_single_page 里的 missing 分支处理。
    all_pages: set[int] = set()
    for pages in engine_pages.values():
        all_pages.update(pages.keys())

    results: list[EngineDisagreement] = []
    for page_no in sorted(all_pages):
        results.extend(_compare_single_page(page_no, engine_pages, engines))

    if min_severity:
        floor = _SEVERITY_RANK.get(min_severity, 0)
        results = [item for item in results if _SEVERITY_RANK.get(item.severity, 0) >= floor]

    return sorted(
        results,
        key=lambda item: (
            -_SEVERITY_RANK.get(item.severity, 0),
            item.page_no,
            item.similarity,
        ),
    )


_SEVERITY_RANK = {SEVERITY_LOW: 1, SEVERITY_MEDIUM: 2, SEVERITY_HIGH: 3}


def _compare_single_page(
    page_no: int,
    engine_pages: dict[str, dict[int, str]],
    engines: list[str],
) -> list[EngineDisagreement]:
    """比对单页。两两引擎分别对齐，避免「A 和 B 一致、C 不同」被合并丢失。"""
    # 收集本页有内容的引擎
    present = {name: engine_pages[name].get(page_no, "") for name in engines}
    present = {name: text for name, text in present.items() if str(text or "").strip()}

    if len(present) < 2:
        # 只剩一个引擎：不比对，但也不报 missing——
        # 单引擎是正常降级路径，报出来会让每一页都变成告警。
        return []

    names = sorted(present)
    out: list[EngineDisagreement] = []
    for i, left_name in enumerate(names):
        for right_name in names[i + 1 :]:
            out.extend(_compare_pair(page_no, left_name, present[left_name], right_name, present[right_name]))

    # 同一页同一位置可能被多对引擎重复报（3 引擎时 A-B、A-C、B-C 都命中）。
    # 去重键用 (kind, 归一化后的变体集合)，避免同一处刷出三条。
    deduped: dict[tuple[str, tuple[str, ...]], EngineDisagreement] = {}
    for item in out:
        key = (item.kind, tuple(sorted(_normalize(v.text) for v in item.variants)))
        existing = deduped.get(key)
        # 保留严重度更高的那条
        if existing is None or _SEVERITY_RANK.get(item.severity, 0) > _SEVERITY_RANK.get(existing.severity, 0):
            deduped[key] = item
    return list(deduped.values())


def _compare_pair(
    page_no: int,
    left_name: str,
    left_text: str,
    right_name: str,
    right_text: str,
) -> list[EngineDisagreement]:
    """两个引擎在同一页上的逐行比对。

    ## 表格内容**不参与**逐字比对

    两个引擎给出的表格形态根本不同：

    · MinerU：表格块是一整行（HTML 去标签 + 空白折叠，实用上 1000+ 字符的单行）；
    · PaddleOCR-VL：表格是多行 GFM markdown（每行带 ``|`` 分隔的单元格）。

    同一张表在两边的行切分、行列结构和空白处理上必然不同，喂给 difflib 只会整表
    判成一处 ``replace``、再因为相似度够高被报成 **high**。修复前表格块的 ``text``
    恒为空串，两边都在行切分阶段被跳过、**根本没参与比对**；``parsed.text`` 开始含
    表格内容之后若不同时堵住这里，每张表都会冒一条 high 级分歧，把「张三 /
    张叁」那种一字的真名错字淹掉——律师就再也看不到真问题。

    所以两侧都显式跳过表格：MinerU 侧由 ``_run_mineru`` 按块类型过滤（表格块不进去
    逐页文本），VL 侧由 ``_split_meaningful_lines`` 按行形态过滤。代价是「两边都识别
    到了表格」这类信息不再从逐字比对里体现——那是可以接受的：表格的正确性只能靠
    人看原图核对，逐字比对给不出可信结论，而一条假 high 会让真 suspect 失去意义。
    """
    left_lines = _split_meaningful_lines(left_text)
    right_lines = _split_meaningful_lines(right_text)
    if not left_lines or not right_lines:
        return []

    out: list[EngineDisagreement] = []
    matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        left_chunk = left_lines[i1:i2]
        right_chunk = right_lines[j1:j2]

        if tag == "replace" and left_chunk and right_chunk:
            # 逐行配对比较；多出来的行按 missing 处理
            emitted = 0
            for offset, (left_line, right_line) in enumerate(zip(left_chunk, right_chunk, strict=False)):
                # 锚点看**两侧邻域**：姓名与身份证号在表单里常是相邻两行，
                # 只看本行会把绑定到具体人的姓名分歧误降为 medium。
                anchor = (
                    _anchors_nearby(left_lines, i1 + offset)
                    or _anchors_nearby(right_lines, j1 + offset)
                    or _anchor_hit(left_line)
                    or _anchor_hit(right_line)
                )
                classified = _classify_pair(left_line, right_line, anchor=anchor)
                if classified is None:
                    continue
                kind, severity, similarity = classified
                emitted += 1
                out.append(
                    EngineDisagreement(
                        page_no=page_no,
                        kind=kind,
                        severity=severity,
                        variants=[
                            EngineVariant(engine=left_name, text=_truncate(left_line), full_text=left_line),
                            EngineVariant(engine=right_name, text=_truncate(right_line), full_text=right_line),
                        ],
                        context=_truncate(left_line if len(left_line) >= len(right_line) else right_line),
                        anchor_hit=anchor,
                        similarity=similarity,
                    )
                )

            if emitted == 0:
                # 逐行都配不上（相似度低于阀值）：两边是**完全不同的切行方式**，
                # 典型如 MinerU 把整页压成 1 行、VL 输出几十行。这不能静默丢弃——
                # 那一整块内容在两引擎里对不上，律师最需要看的就是这种。
                # 报成一条「整块覆盖不一致」，让人去核，而不是当作「无分歧」。
                left_joined = " ／ ".join(left_chunk)
                right_joined = " ／ ".join(right_chunk)
                # 先看整块归一化后是不是其实一样：
                # 典型如一边 `# 证明`、一边 `证明`——切行不同但内容相同。
                # 这种不该报成 high，否则每个带标题的段落都会刷一条假告警。
                whole_norm_left = _normalize(left_joined)
                whole_norm_right = _normalize(right_joined)
                if whole_norm_left == whole_norm_right:
                    continue
                whole_similarity = difflib.SequenceMatcher(
                    None, whole_norm_left, whole_norm_right, autojunk=False
                ).ratio()
                # 行数相近才当「只是切行不同」：两边都是 1~2 行的小段落时，
                # 相似度 0.5+ 往往真的只是换行位置不同。
                #
                # 但不能只看相似度：一整块表单内容被一边当整段、另一边拆成很多行时，
                # 字符相似度依然可能过线，但行数差几倍就不可能是「同一段落换个切法」。
                # 所以再加一道行数比限制，避免把真分歧滤掉。
                #
                # 待核实（不阻塞使用）：旧注释举的 p44「左 2 行 vs 右 9 行、相似度 0.558」
                # 需要两引擎原文才能复跑，而仓库里没有 VL 响应存档，所以这个阈值目前
                # 是经验值而非实测拟合值。若将来留了响应存档，应拿它重标一次。
                # 当前取值偏保守（宁可多报），错报代价远小于漏报。
                line_ratio = (
                    (min(len(left_chunk), len(right_chunk)) / max(len(left_chunk), len(right_chunk)))
                    if max(len(left_chunk), len(right_chunk))
                    else 0.0
                )
                if whole_similarity >= _LINE_SIMILARITY_FLOOR and line_ratio >= _CHUNK_LINE_RATIO_FLOOR:
                    # 内容大体相似且行数相当：只是行边界划得不同，不是真分歧。
                    continue
                out.append(
                    EngineDisagreement(
                        page_no=page_no,
                        kind=KIND_LINE,
                        # 整块对不上时同样要看差异的性质：两边行数不同会让本模块自己加的
                        # ``／`` 拼接分隔符数量对不上，那是排版不是认错字，降 low。
                        severity=(
                            SEVERITY_LOW
                            if _is_presentation_only_diff(whole_norm_left, whole_norm_right)
                            else SEVERITY_HIGH
                        ),
                        variants=[
                            EngineVariant(engine=left_name, text=_truncate(left_joined), full_text=left_joined),
                            EngineVariant(engine=right_name, text=_truncate(right_joined), full_text=right_joined),
                        ],
                        context=_truncate(left_joined),
                        anchor_hit=_anchors_nearby(left_lines, i1) or _anchors_nearby(right_lines, j1),
                        similarity=0.0,
                    )
                )
            continue

        if tag == "delete" and left_chunk:
            # 只有 A 有、B 没有。这**多数是版面切分差异**（B 把这几行并到上一段里了），
            # 不是「B 漏读了」。所以给 low，只为让人知道「这里两引擎覆盖不同」。
            for left_line in left_chunk:
                out.append(
                    EngineDisagreement(
                        page_no=page_no,
                        kind=KIND_MISSING,
                        severity=SEVERITY_LOW,
                        variants=[
                            EngineVariant(engine=left_name, text=_truncate(left_line), full_text=left_line),
                            EngineVariant(engine=right_name, text=""),
                        ],
                        context=_truncate(left_line),
                        anchor_hit=_anchor_hit(left_line),
                        similarity=0.0,
                    )
                )
            continue

        if tag == "insert" and right_chunk:
            for right_line in right_chunk:
                out.append(
                    EngineDisagreement(
                        page_no=page_no,
                        kind=KIND_MISSING,
                        severity=SEVERITY_LOW,
                        variants=[
                            EngineVariant(engine=left_name, text=""),
                            EngineVariant(engine=right_name, text=_truncate(right_line), full_text=right_line),
                        ],
                        context=_truncate(right_line),
                        anchor_hit=_anchor_hit(right_line),
                        similarity=0.0,
                    )
                )

    return out


# ---------------------------------------------------------------------------
# 引擎定位归一化
# ---------------------------------------------------------------------------
#
# 坐标统一成 0–1 的动机与 ``split/bbox.py`` 相同（那个模块做的是**切分预处理**用的
# 版面框，本段做的是**双引擎对照**用的块框，形状和输入来源都不同，故不互相调用）。


def _clamp01(value: float) -> float:
    """把归一化坐标夹回 0–1。

    引擎偶尔会给出越界值（多页拼接图的坐标、多边形外接矩形算错）。越界的框画出来
    会飘到页面外，前端还得自己兜；在归一化这一步夹回页内，前端拿到的 0–1 恒可信。
    """
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _to_rect_xyxy(raw: Any) -> list[float] | None:
    """把 ``[x0,y0,x1,y1]`` 或四点多边形转成外接矩形；转不了返回 None。

    VL 除了 ``block_bbox`` 还给了 ``block_polygon_points``（能处理倾斜版面）。
    这里不引入多边形渲染，统一取外接矩形：双框对照要的是“大致在哪一块”，
    而外接矩形对倾斜文字的覆盖只会变大——盖住真位置比偏出去安全。
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    # [[x,y], ...] 四点多边形 → 外接矩形
    if isinstance(raw[0], (list, tuple)):
        xs: list[float] = []
        ys: list[float] = []
        for point in raw:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            try:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
            except (TypeError, ValueError):
                return None
        if not xs or not ys:
            return None
        return [min(xs), min(ys), max(xs), max(ys)]
    if len(raw) < 4:
        return None
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])]
    except (TypeError, ValueError):
        return None


def _ratio_rect(
    x0: float, y0: float, x1: float, y1: float, divisor_x: float, divisor_y: float
) -> dict[str, float] | None:
    """把已排好序的原始框除以给定的两个基准，产出 0–1 矩形。

    两种坐标单位（千分比 / 绝对像素）的差别只有「除以什么」，其余（夹回页内、
    退化框判定、保留 4 位小数）完全一致，所以步骤共用一份，单位只在调用处选择。
    """
    nx0 = _clamp01(x0 / divisor_x)
    ny0 = _clamp01(y0 / divisor_y)
    nx1 = _clamp01(x1 / divisor_x)
    ny1 = _clamp01(y1 / divisor_y)

    width_ratio = nx1 - nx0
    height_ratio = ny1 - ny0
    # 退化框（宽或高为 0）画出来看不见，等同“没有坐标”
    if width_ratio <= 0 or height_ratio <= 0:
        return None
    # 保留 4 位小数：除法会算出 0.03999999999999998 这类丑数，前端快照也难写
    return {"x": round(nx0, 4), "y": round(ny0, 4), "w": round(width_ratio, 4), "h": round(height_ratio, 4)}


def _normalize_permille_rect(bbox: Any) -> dict[str, float] | None:
    """千分比框（0–1000）→ 0–1；坐标不可解析或退化时返回 None。

    **不需要页面尺寸**：千分比是引擎自带的「页宽高 = 1000」约定，与真实页宽无关。
    这也是 MinerU 唯一可靠的坐标口径——它给的 ``page_size`` 是点（612×1008 之类），
    bbox 却是千分比，两个数不能相除。
    """
    coords = _to_rect_xyxy(bbox)
    if coords is None:
        return None
    x0, y0, x1, y1 = coords
    # 引擎偶尔给反序坐标（右下在前），先排序再算宽高
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return _ratio_rect(x0, y0, x1, y1, _MINERU_PERMILLE, _MINERU_PERMILLE)


def _normalize_absolute_rect(bbox: Any, page_width: Any, page_height: Any) -> dict[str, float] | None:
    """绝对像素框 → 0–1 的 ``{"x","y","w","h"}``；页面尺寸缺失/无效时返回 None。

    **返回 None 而不是猜一个尺寸**：没有页宽高就无法把像素换算成比例，
    拿“假定 1200×1976”去凑会得到一个看着像真的、实际错位的框。
    """
    coords = _to_rect_xyxy(bbox)
    if coords is None:
        return None
    try:
        width = float(page_width)
        height = float(page_height)
    except (TypeError, ValueError):
        return None
    # 零/负尺寸除下去就是 inf/nan，会把整层 SVG 搞坏
    if width <= 0 or height <= 0:
        return None

    x0, y0, x1, y1 = coords
    # 引擎偶尔给反序坐标（右下在前），先排序再算宽高
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return _ratio_rect(x0, y0, x1, y1, width, height)


def _mineru_rect(bbox: Any, page_width: Any, page_height: Any) -> dict[str, float] | None:
    """MinerU 框 → 0–1；按本块的坐标量级判定单位后换算。

    为什么要判定而不是写死一个单位：MinerU 的 bbox 有两种来源，量级差 3 个数量级，
    用错单位不是「差一点」而是把框平台挤扁到左上一小块（真实事故：整层框全空/全错位）。

    · ``content_list.json``（**主路径**）：**千分比** 0–1000；
    · 某些本地 pipeline：**绝对像素**，随 200/300 DPI 可达数千。

    判定依据是同一块版面在三个文件里的原始值互相换算后全部吻合：

    ```
    content_list [209, 89, 666, 118] / 1000 × 612 = [127.9, 54.5, 407.6, 72.2]
    layout.json  [128, 90, 408, 119]   （page_size 612×1008，绝对像素）  ✓
    model.json   [0.21, 0.09, 0.668, 0.119] × 612 = [128.5, 55.1, 408.8, 72.8] ✓
    ```

    所以 ``content_list`` 的千分比除以 1000 得到的比例，与 ``layout.json`` 的像素
    除以 ``page_size`` 得到的比例**是同一个数**——两套换算殊途同归，量级判据只要
    不把两边弄反，结果一致。

    判定规则：坐标最大值 > 2000 → 只能是绝对像素；否则按千分比。
    **不确定时选千分比**：content_list 是主路径，且像素框恰好全落在 2000 以内
    意味着整个块挤在页面左上角，本就不该被信任。

    **``page_size`` 是像素，不是千分比基准。** 它只在本块被判为绝对像素时充当除数；
    千分比换算用它就会得到错位框。判为绝对像素却没有有效页宽高时返回 None
    （宁可不画框，也不按错单位画）。
    """
    coords = _to_rect_xyxy(bbox)
    if coords is None:
        return None
    # 量级判据用绝对值：越界负坐标（多边形外接矩形算错）同样是「远超上界」的证据
    if max(abs(value) for value in coords) <= _MINERU_ABSOLUTE_PIXEL_FLOOR:
        return _normalize_permille_rect(bbox)
    return _normalize_absolute_rect(bbox, page_width, page_height)


def _coerce_page_no(raw: Any) -> int | None:
    """把页码转成正整数；转不了或 <=0 返回 None。

    页码为 None 的块无法归到任何一页，双框对照也就无从画起——直接跳过。
    """
    try:
        page_no = int(str(raw))
    except (TypeError, ValueError):
        return None
    return page_no if page_no >= 1 else None


def normalize_mineru_blocks(
    blocks: Any,
    page_sizes: Mapping[int, Any] | None = None,
) -> list[EngineBlock]:
    """把 MinerU 的 ``ParsedBlock`` 列表统一成 ``EngineBlock``。

    Args:
        blocks: ``ParsedBlock`` 列表（或任何带 ``type`` / ``text`` / ``bbox`` / ``page_no``
            这四个属性的对象——刻意不 import 具体类型，免得本模块被钉死在某个后端）。
        page_sizes: ``{页码: 页面尺寸}``。尺寸可以是 ``{"width": w, "height": h}``，
            也可以是 ``(w, h)`` 二元组。MinerU 的页宽高在
            ``doc.layout["pages"][].width/height`` 里，由调用方整理成这个形状。

    Returns:
        与输入同序的块列表；**表格块**、空文本、无 bbox、无页码的块被跳过
        （画不出来、没内容，或不该参与比对）。
        ``page_sizes`` 里查不到某页时，只要坐标量级是千分比（SaaS 主线）仍能画出框；
        只有量级像是绝对像素时才因为没页宽高而 ``rect={}`` 且 ``approx=True``。

    ## 为什么表格块要**显式**跳过

    这里刻意不靠 ``text == ""`` 顺手把表格块滤掉：``parsed.text`` / 块文本现在会带上
    表格正文（HTML 去标签），表格块不再是空文本，靠空串过滤的旧假设已经失效。而表格块
    一旦流进 ``link_disagreement_to_blocks``，一张 1000+ 字符的整表块几乎必含任何短变体
    的文字，会把分歧“定位”到整张表上——画出一个盖住半页的假框。
    表格本身不参与逐字比对，也就不需要它的对照框（理由见 :func:`_compare_pair`）。
    """
    sizes = page_sizes or {}
    out: list[EngineBlock] = []
    for block in blocks or []:
        # 表格块显式跳过（不能靠 text 为空隐式跳过，表格文本现在非空）
        if str(getattr(block, "type", "") or "").strip().lower() in MINERU_TABLE_BLOCK_TYPES:
            continue
        text = str(getattr(block, "text", "") or "").strip()
        if not text:
            continue
        page_no = _coerce_page_no(getattr(block, "page_no", None))
        if page_no is None:
            continue
        bbox = getattr(block, "bbox", None)
        if bbox is None:
            # 无 bbox 的块（本地后端按行兜底的产物）连位置都没有，跳过
            continue

        width, height = _split_page_size(sizes.get(page_no))
        # MinerU 的 bbox 是千分比（不是绝对像素）；缺页面尺寸不影响千分比换算，
        # 尺寸只在坐标量级像是绝对像素时才需要，由 ``_mineru_rect`` 自己判
        rect = _mineru_rect(bbox, width, height)
        out.append(
            EngineBlock(
                engine=ENGINE_MINERU,
                page_no=page_no,
                text=text,
                # 算不出可信坐标（绝对像素缺页宽高 / 退化框）→ 不给坐标，也不假装精确
                rect=rect or {},
                block_type=str(getattr(block, "type", "") or BLOCK_TYPE_UNKNOWN),
                approx=rect is None,
            )
        )
    return out


def _split_page_size(raw: Any) -> tuple[Any, Any]:
    """拆出 ``(width, height)``；认得的形状有 dict 与二元组，其它一律 (None, None)。"""
    if isinstance(raw, Mapping):
        return raw.get("width"), raw.get("height")
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return raw[0], raw[1]
    return None, None


def _frame_size(width: Any, height: Any) -> tuple[float, float] | None:
    """``prunedResult`` 的 ``width``/``height`` → 正浮点二元组；不可用返回 ``None``。

    方向反变换要在像素与归一化之间来回换算，没有可信的正尺寸就不做（宁可给θ=0 的
    未变换坐标，也不拿 0 当分母算出一个飘到页外的框）。
    """
    try:
        width_px, height_px = float(width), float(height)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(width_px) and math.isfinite(height_px)) or width_px <= 0 or height_px <= 0:
        return None
    return width_px, height_px


def normalize_paddleocr_vl_blocks(pruned_results: Any) -> list[EngineBlock]:
    """把 PaddleOCR-VL 的 ``prunedResult`` 列表统一成 ``EngineBlock``。

    Args:
        pruned_results: ``jsonUrl`` 结果里的 ``layoutParsingResults[i].prunedResult``，
            即 ``{"width": ..., "height": ..., "parsing_res_list": [...]}``。
            也接受直接传入单页的 ``parsing_res_list``（没有页面尺寸时按缺尺寸处理）。

    Returns:
        按输入顺序拼接的块列表（跨页按 ``pruned_results`` 顺序）。**页号按列表下标 +1**：
        VL 的块本身不带页码，只能靠 ``layoutParsingResults`` 的顺序定位，
        这与 MinerU 1 起页号对齐。缺 ``width``/``height`` 时 ``rect={}`` 且 ``approx=True``。

    ## 方向：``rect`` 出来时已经在**原页帧**

    开启整页方向分类后 ``prunedResult`` 的坐标全在转正帧（见 ``page_rotation``）。反变换就在这里
    做——而且**只在这里**做一次：本函数是两个消费方（``ocr_handler.vl_page_layout`` 与
    ``dual_engine_runner``）共用的唯一入口，谁也不必再转一次。
    """
    out: list[EngineBlock] = []
    for index, pruned in enumerate(pruned_results or []):
        if not isinstance(pruned, Mapping):
            continue
        page_no = index + 1
        width = pruned.get("width")
        height = pruned.get("height")
        theta = page_angle(dict(pruned))
        frame = _frame_size(width, height)
        raw_blocks = pruned.get("parsing_res_list")
        if not isinstance(raw_blocks, list):
            continue
        for raw_block in raw_blocks:
            if not isinstance(raw_block, Mapping):
                continue
            text = str(raw_block.get("block_content") or "").strip()
            if not text:
                continue
            # block_bbox 缺失时退回多边形外接矩形（VL 两个字段通常都有，但不保证）
            bbox = raw_block.get("block_bbox") or raw_block.get("block_polygon_points")
            if not bbox:
                continue
            rect = _normalize_absolute_rect(bbox, width, height)
            if rect is not None and theta:
                # 转正了却拿不到可信帧尺寸 = 换不回原页帧：宁可不出框（approx=True），
                # 也不把转正帧的坐标当作原页帧画出去。
                rect = derotate_rect(rect, theta, rot_w=frame[0], rot_h=frame[1]) if frame else None
            # 原始 label（doc_title/text/table…）原样保留：前端要按它区分标题/表格，
            # 归一到统一词汇会丢掉对照时需要的粒度。
            out.append(
                EngineBlock(
                    engine=ENGINE_PADDLEOCR_VL,
                    page_no=page_no,
                    text=text,
                    rect=rect or {},
                    block_type=str(raw_block.get("block_label") or BLOCK_TYPE_UNKNOWN),
                    approx=rect is None,
                )
            )
    return out


#: 文本包含关系匹配的最短长度。
#:
#: 单字/双字变体（如“李四”里的“四”）在整页块里几乎必然被某个长块包含，
#: 会把分歧硬挂到一个不相干的段上——那种“猜”出来的框比没有框更误导。
_TEXT_LINK_MIN_CHARS = 3


def _squash(text: str) -> str:
    """去掉所有空白与 Markdown 噪声，只留有语义字符，用于包含关系比较。

    两个引擎对同一块文本的空白/换行处理不同（VL 的表格是 GFM 一行带 ``|``），
    不压平的话“包含”关系会因为中间夹了个空格就断。
    """
    return _normalize(text)


def _find_block(variant_text: str, blocks: list[EngineBlock]) -> EngineBlock | None:
    """在同引擎的块里找承载 ``variant_text`` 的那一个；找不到返回 None。

    匹配策略：**文本包含关系**（块文本包含变体，或变体包含块文本）。
    不用坐标/序号硬对应，因为两引擎的行切分方式不同（见模块 docstring），
    序号对不上号；而文本包含关系是“这段字确实出在这块里”，是能验证的事实。

    多个候选时（同一段短字被多个长块包含）取**归一化文本最短**的那个：
    块越短，包含关系越可能是精确对应，而不是恰好也包含这几个字。
    """
    needle = _squash(variant_text)
    if len(needle) < _TEXT_LINK_MIN_CHARS:
        return None

    best: EngineBlock | None = None
    best_len = 0
    for block in blocks:
        haystack = _squash(block.text)
        if not haystack:
            continue
        if needle not in haystack and haystack not in needle:
            continue
        if best is None or len(haystack) < best_len:
            best, best_len = block, len(haystack)
    return best


def link_disagreement_to_blocks(
    disagreement: EngineDisagreement,
    blocks_by_engine: Mapping[str, list[EngineBlock]],
) -> dict[str, EngineBlock | None]:
    """把一条分歧挂回两引擎各自的块，供前端画双框。

    Args:
        disagreement: ``compare_pages`` 产出的一条分歧。
        blocks_by_engine: ``{引擎名: 该引擎的全部 EngineBlock}``（跨页可以都放进来，
            本函数会先按分歧的页码过滤）。

    Returns:
        ``{引擎名: 该引擎对应的块或 None}``，键与 ``blocks_by_engine`` 一致。
        匹配不上就是 ``None``——**不猜**：宁可前端只画一个框，
        也不要把框画到一个不相干的段落上让人误以为“这处就在那里”。
    """
    page_no = disagreement.page_no
    result: dict[str, EngineBlock | None] = {}

    for engine in blocks_by_engine:
        page_blocks = [block for block in blocks_by_engine[engine] if block.page_no == page_no]
        found: EngineBlock | None = None
        for variant in disagreement.variants:
            if variant.engine != engine:
                continue
            # missing 类的某个引擎变体文本为空 —— 它本来就没识别出这段,
            # 没有任何东西可指，保持 None（前端只画另一侧的实框）。
            found = _find_block(variant.text, page_blocks)
            if found is not None:
                break
        result[engine] = found

    return result
