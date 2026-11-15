"""取字/表格质量的**可复跑度量**：CER、归一化、表格单元格 F1。

## 为什么要有这个文件

在它出现之前，本模块所有质量取舍（``_TABLE_SPLIT_MAX_ROWS = 12``、表格拆格门槛、
分段相似度 0.5）都是**凭目测**定的：注释里写「实测 p62 第 1 行偏差 72px」，
但那个数是人盯着屏幕量出来的，改完代码没有任何东西能复跑一遍说「变好了还是变坏了」。
没有度量的调参等于没有版本控制的重构——每次改动都不可证伪。

所以这里只放三个纯函数，全部只用 stdlib：

- :func:`char_error_rate` —— 逐页文本的 CER（编辑距离 / 参考长度）
- :func:`normalize_for_cer` —— CER 前的归一化（去空白、去 Markdown 标记、全半角统一）
- :func:`table_cell_f1` —— 表格的单元格级 F1（不要求行列对齐）

## 归一化必须同时报两个数

归一化（去空白 / 去 Markdown 标记）几乎必然把 CER 拉低，因为差异被"洗掉"了。
只看归一化后的数字，任何改动都会显得在变好——这是自欺。所以度量契约是：
**同时报「归一化前」与「归一化后」两个 CER**，两者都进基线报告，
用归一化后的看「内容对不对」，用归一化前的看「排版/格式有没有退化」。

## 为什么 CER 用编辑距离而不是「不同字符数」

OCR 的典型错误是插入/删除（多认一个字、漏认一个字），不是等长替换。
「不同字符数」对插入删除无穷大（长度都不等），编辑距离才能给出 0–1 的连续刻度。
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .split_models import _levenshtein_distance

#: Markdown 结构标记：标题井号、列表符号、强调符、代码围栏、表格分隔行。
#: 只去**结构**，不去内容——把 `#` 去掉是为了让「MinerU 给标题加了 `##`、
#: 本地 OCR 没加」这种纯格式差异不算错字，但标题里的文字一个字都不许动。
#: 必须带 ``re.MULTILINE``：这些标记都锚在**行首**，不带 M 时 ``^`` 只匹配
#: 整串开头，多行文本的第 2 行起列表符号会漏掉（实测用例直接抓到这个）。
_MD_STRUCTURE_RE = re.compile(
    r"^\s{0,3}#{1,6}\s+"  # ATX 标题的井号前缀
    r"|^\s*[-*+]\s+"  # 无序列表符号
    r"|^\s*\d+[.)]\s+"  # 有序列表符号
    r"|^\s*```(?:\w+)?\s*$",  # 代码围栏整行（带语言标注的也吃掉）
    re.MULTILINE,
)
_MD_INLINE_RE = re.compile(r"\*{1,3}|`{1,2}|~~")
#: GFM 表格分隔行：`| --- | :---: |`。它在 Markdown 里是纯排版，参考文本不会有。
_MD_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"\s+")


def char_error_rate(pred: str, gold: str) -> float:
    """CER = (S+D+I) / N，N 是参考文本 ``gold`` 的字符数。

    编辑距离用 Levenshtein（插入/删除/替换均计 1），返回值语义：

    - ``0.0`` —— 与参考完全一致
    - ``1.0`` —— 一字不差地全错，或长度相等但全部替换
    - ``> 1.0`` —— 预测比参考长得多（大量插入）。**不截断到 1.0**：
      截断会把「多认了一倍的字」和「全错」压成同一个数，看不出退化。

    参考为空（``gold == ""``）时按行业惯例返回 ``0.0``（若预测也为空）或 ``1.0``
    （预测有字却无参考，无从判断，按全错记），避免除零。
    调用前请先用 :func:`normalize_for_cer` 处理两侧，否则空白/格式差异会污染分数。

    Args:
        pred: 预测文本（待评测的取字结果）。
        gold: 参考文本（golden）。

    Returns:
        CER 值，``0.0`` 起，无上界（插入过多时 >1）。
    """
    if not gold:
        return 0.0 if not pred else 1.0
    # 用编辑距离而不是「逐位比对」：OCR 的典型错误是插入/删除（多认、漏认一个字），
    # 长度一变，逐位比对会把后面所有字都记成错，分数虚高到 1.0。
    return _levenshtein_distance(pred, gold) / len(gold)


def normalize_for_cer(text: str) -> str:
    """CER 前的归一化：全半角统一 → 去 Markdown 结构标记 → 去全部空白。

    三步的**顺序有讲究**：

    1. **全半角先做**（NFKC）：``（``/``(``、``１``/``1`` 是同一个字的不同写法，
       不先统一，去空白之后再洗就分不清哪些空格是半角转来的。
    2. **再去 Markdown 标记**：只去结构（``##``、``- ``、``**``、表格分隔行），
       标题/正文里的汉字一个都不动——格式差异不该算错字，内容差异必须留着。
    3. **最后去空白**：OCR 引擎之间换行位置、缩进、全角空格差异极大
       （同一页 MinerU 与本地 OCR 的换行几乎从不一致），保留空白等于在度量换行策略。

    ⚠️ **报告时必须同时给归一化前与归一化后的 CER**。归一化几乎必然降低 CER，
    只看后者会让任何改动都显得在变好——那是假提升。归一化后看内容对不对，
    归一化前看排版有没有退化。

    Args:
        text: 原始文本（可能带 Markdown 标记、全角标点、多行缩进）。

    Returns:
        归一化后的文本，不含任何空白字符。
    """
    if not text:
        return ""
    unified = unicodedata.normalize("NFKC", text)
    unified = _MD_TABLE_SEPARATOR_RE.sub("\n", unified)
    unified = _MD_STRUCTURE_RE.sub("", unified)
    unified = _MD_INLINE_RE.sub("", unified)
    return _WHITESPACE_RE.sub("", unified)


def table_cell_f1(pred_html: str, gold_html: str) -> float:
    """表格单元格级 F1：按**格内容的多重集合**匹配，不要求行列对齐。

    ## 为什么不做行列对齐

    本仓库的表格坐标是**均分推算**的（MinerU 只给整表 bbox，逐格坐标是编出来的），
    行列切分本身就可能错位——拿行列对齐去评分，测的是「均分算得准不准」，
    不是「表里的字认得对不对」。律师要的是「这格里的『*房产证编号』认对了没有」，
    所以度量只认格内容。

    ## 为什么两侧都接受 HTML 和 GFM 两种形态

    pipeline 的输出是 **GFM 表格**（``_html_table_to_markdown`` 的产物），
    而 golden 参考存的是 **HTML**（MinerU ``table_body`` 原样）。只认 HTML 的话，
    拿真实产物去打分恒为 0——那是度量写错了，不是 pipeline 坏了。
    所以单看输入里有没有 ``<td``/``<th`` 决定按哪种形态切格。

    ## 为什么用多重集合而不是集合

    流水表里「财付通支付」会出现几十次，用 set 会把 40 次正确识别压成 1 次，
    掩盖漏行。``Counter`` 的交集基数 = 每种格内容两侧较小计数之和。

    单元格文本先过 :func:`normalize_for_cer`：``<td>押品信息</td>`` 与
    ``<td> 押品信息 </td>`` 是同一格，不该算错。``<img>`` 之类的纯图形格
    剥完标签后是空串，直接丢弃——它不承载可比对的文字。

    Args:
        pred_html: 预测侧表格，HTML（``<table>...</table>``）或 GFM 管道表，可为空串。
        gold_html: 参考侧表格，同上两种形态任意一种。

    Returns:
        单元格 F1，``0.0``–``1.0``。两侧都无有字格时返回 ``1.0``（没有可错的）。
    """
    pred_cells = Counter(_table_cell_texts(pred_html))
    gold_cells = Counter(_table_cell_texts(gold_html))
    if not pred_cells and not gold_cells:
        return 1.0
    if not pred_cells or not gold_cells:
        return 0.0
    # 匹配数 = 每个格内容在两侧的较小计数之和（多重集合交集的基数）
    matched = sum((pred_cells & gold_cells).values())
    if matched == 0:
        return 0.0
    precision = matched / sum(pred_cells.values())
    recall = matched / sum(gold_cells.values())
    # 两侧对称，F1 分母不可能为 0（matched>0 时 precision/recall 均 >0）
    return 2 * precision * recall / (precision + recall)


#: 单元格切分：容忍属性（colspan/rowspan/style）与自闭合 img。
_CELL_BLOCK_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
#: GFM 分隔行：整行只由 ``|``、``-``、``:`` 与空白组成。
_GFM_SEPARATOR_LINE_RE = re.compile(r"^\|?[\s:|-]*-[\s:|-]*\|?$")


def _table_cell_texts(table: str) -> list[str]:
    """把表格拆成「归一化后的有字格」列表（不含空串）。

    行/列结构在这里被刻意丢弃：度量只看格内容，见 :func:`table_cell_f1`。
    有 ``<td``/``<th`` 就走 HTML 分支，否则按 GFM 管道表切。
    """
    if not table:
        return []
    texts = _html_cell_texts(table) if _CELL_BLOCK_RE.search(table) else _gfm_cell_texts(table)
    out: list[str] = []
    for raw in texts:
        text = normalize_for_cer(raw)
        if text:
            out.append(text)
    return out


def _html_cell_texts(html: str) -> list[str]:
    """HTML 表格 → 原始格文本（未归一化，``<img>`` 等标签已剥掉）。"""
    return [_TAG_STRIP_RE.sub("", raw) for raw in _CELL_BLOCK_RE.findall(html)]


def _gfm_cell_texts(markdown: str) -> list[str]:
    """GFM 管道表 → 原始格文本。

    跳过 ``| --- | :---: |`` 分隔行——它在 Markdown 里是纯排版，参考侧没有对应格，
    留着会让每张表白扣 ``列数`` 个格。
    """
    out: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # 分隔行整行只由 - 和 : 组成，不含任何文字
        if _GFM_SEPARATOR_LINE_RE.match(stripped):
            continue
        for cell in stripped.strip("|").split("|"):
            out.append(cell)
    return out
