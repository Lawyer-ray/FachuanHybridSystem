"""Markdown 净化纯函数：原始 HTML 剥离、段标题去重、跨页重复短行噪声。

这三件事都只依赖字符串，不碰坐标也不碰 DB，单独成模块便于逐条单测。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from html import unescape

from .page_quality import is_name_token, strip_stamp_boilerplate_lines

#: 只剥**已知 HTML 标签名**，不用 `<[^>]+>` 通吃。
#:
#: 法律正文里出现「金额<100万」「利率>4%」这类比较号是常态，通吃正则会把
#: 「<100万…>」整段当标签吃掉。引擎（MinerU/TextIn）写进纯文本的标签是
#: 可枚举的，按名单剥既干净又不会误伤正文。
_HTML_TAG_RE = re.compile(
    r"</?(?:img|div|span|p|br|td|th|tr|table|tbody|thead|font|b|i|u|sup|sub|a|ul|ol|li|h[1-6]|strong|em|hr)\b[^>]*>",
    re.IGNORECASE,
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
#: 标题归一化：去掉标点、空白、下划线，只留字母数字汉字（全角/半角差异一并抹平）。
_TITLE_NORMALIZE_RE = re.compile(r"[\W_]+", re.UNICODE)

#: 噪声行长度上限：超过它的行承载正文，不参与重复统计。
MAX_NOISE_LINE_CHARS = 30
#: 至少重复出现在这么多页上。
MIN_NOISE_PAGES = 3
#: 且占本段页数的这个比例以上。
MIN_NOISE_PAGE_RATIO = 0.5

#: 条款编号：命中就**不滤**，哪怕它每页都重复。
#:
#: 为什么必须保护：法院文书/合同的「第X条」「X.Y」「一、」本身就是跨页重复的
#: 结构性行，滤掉等于把条款骨架删了。这条判据是防「优化银行档案、劣化法院文书」
#: 的关键——银行档案的噪声（印章核验语）不带条款号，两类材料因此分得开。
_CLAUSE_RE = re.compile(
    r"第[一二三四五六七八九十百零〇\d]+[条章节款项]|^\d+\.\d+|^[一二三四五六七八九十]+、|^\d+[、.)．]"
)
#: 承载金额/日期/账号的数字：长数字串、小数、或带年月日的数字。
#: 单个数字（如「第2页」的 2）不算——那正是页码噪声。
_NUMERIC_PAYLOAD_RE = re.compile(r"\d{4,}|\d+\.\d+|\d+\s*[年月日]")


def strip_html(text: str) -> str:
    """剥掉引擎写进纯文本里的原始 HTML 标签。

    ``<img src=...>`` 直接去除，**不编造占位文字**：图片里的手写/表格内容本来
    就没被 OCR 出来，写个「[图片]」只会让下游 AI 以为那里有内容可引用。
    ``<br>`` 换成换行（它本来就是换行语义），其余标签只去壳留内文。
    """
    if "<" not in text and "&" not in text:
        return text.strip()
    cleaned = _BR_RE.sub("\n", text)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    return unescape(cleaned).strip()


def normalize_title(text: str) -> str:
    return _TITLE_NORMALIZE_RE.sub("", text).lower()


def title_already_present(title: str, body_first_line: str) -> bool:
    """正文首行就是与段名同名的标题时，不再重复注入 ``# 段名``。

    只看**首行**：段名与文档自身首标题叠加时两者必然相邻（实测 9/45 段都是
    「# 个人房产抵押贷款合同」紧跟「## 个人房产抵押贷款合同」）。若同名标题
    出现在正文深处，保留注入的段名——那是段级锚点，删了会让前端/下游找不到段头。
    """
    heading = _HEADING_RE.match(body_first_line)
    if heading is None:
        return False
    normalized = normalize_title(title)
    return bool(normalized) and normalize_title(heading.group(1)) == normalized


def repeated_noise_lines(pages_lines: Sequence[Iterable[str]]) -> set[str]:
    """段内跨页统计：哪些短行是重复噪声（返回行文本集合）。

    ``pages_lines`` 是本段**有正文产出**的页各自的行序列。判据：
    短行（≤30 字）在 ≥3 页且 ≥50% 页上重复出现。

    为什么两个条件都要：只看「≥3 页」会把长合同里偶尔重复的正文短句滤掉；
    只看「≥50%」会把两三页材料里的正文首行当噪声。印章核验语（「已核对与原件
    相符」）每页都盖一次，两个条件同时满足；而正文条款/金额日期行另有保护判据。

    表格行（``|`` 开头）与标题行（``#`` 开头）一律不参与：跨页流水表每页都重复
    同一行表头，滤掉它等于把表拆了。
    """
    total = len(pages_lines)
    if total < MIN_NOISE_PAGES:
        return set()
    pages_by_line: dict[str, set[int]] = {}
    for page_index, lines in enumerate(pages_lines):
        for line in lines:
            text = line.strip()
            if not text or len(text) > MAX_NOISE_LINE_CHARS:
                continue
            if text.startswith(("|", "#")):
                continue
            if _CLAUSE_RE.search(text) or _NUMERIC_PAYLOAD_RE.search(text):
                continue
            pages_by_line.setdefault(text, set()).add(page_index)
    return {
        text
        for text, page_indexes in pages_by_line.items()
        if len(page_indexes) >= MIN_NOISE_PAGES and len(page_indexes) / total >= MIN_NOISE_PAGE_RATIO
    }


def drop_noise_lines(text: str, noise: set[str]) -> str:
    """按行剔除噪声（保持其余行的原文与行序）。"""
    if not noise:
        return text
    return "\n".join(line for line in text.splitlines() if line.strip() not in noise).strip()


def is_stamp_boilerplate_line(line: str) -> bool:
    """整行都是印章/核对套话（含「经办人：某某 某某」）时才判 True。

    短语与归一化口径**完全复用** ``page_quality.strip_stamp_boilerplate_lines``，
    这里不另造词表（两份词表迟早漂移）。它与跨页频次路互补而非替代：
    579 实测 32 个含噪段里 12 段只有 1 页、6 段只有 2 页，频次路的「≥3 页」
    永远够不到；而噪声大头在 mineru_ocr 的版面块路径上，取字层的清洗接不到那里。

    ## 为什么必须逐 token 复核

    那份判据里「经办人[:：][^\\n]*」是**贪婪到行尾**的，直接拿「清洗后为空」
    当纯套话会吞掉真实正文。579 实测会被吞掉的行包括：
    「经办人：某某 某某根据《中华人民共和国物权法》…准予登记，颁发此证。」（整段权证正文）、
    「经办人：某某 某某实施 FATCA 法案尽职调查」、「经办人：某某 某某中华人民共和国国土资源部监制」。
    所以要求每个空白分隔的 token 要么被同一套判据整块吃掉，要么只是人名形态的短词。

    混合行（套话 + 实质内容）一律 False：**不剔也不改**，正文原样保留。
    条款号/金额日期账号/表格行/标题行的保护与频次路同一套。
    """
    text = line.strip()
    if not text or text.startswith(("|", "#")):
        return False
    if _CLAUSE_RE.search(text) or _NUMERIC_PAYLOAD_RE.search(text):
        return False
    if strip_stamp_boilerplate_lines(text).strip():
        return False
    for token in text.split():
        residue = strip_stamp_boilerplate_lines(token).strip()
        # 校验的是**剥掉套话后的残留**：OCR 会把人名与套话粘成一个 token
        # （「测试甲已核对与原件相符」），拿原 token 判形态会漏掉这类纯噪声行。
        if residue and not is_name_token(residue):
            return False
    return True


def drop_stamp_boilerplate_lines(text: str) -> str:
    """剔掉整行印章套话（不依赖页频，单页段也生效）；没命中时原样返回。"""
    lines = text.splitlines()
    kept = [line for line in lines if not is_stamp_boilerplate_line(line)]
    if len(kept) == len(lines):
        return text
    return "\n".join(kept).strip()
