"""答案正文里的法条 / 案号引用核验（纯函数 + 可注入查询接口）。

## 与 ``mcp_server/tools/legal_research/citation_check.py`` 的分工

那边是**给模型用的工具**：自己有网络、有凭证、有威科登录，产出三态
（``verified`` / ``not_verified`` / ``not_found``），还要把"没查"与"查了没有"
分开。本模块是**评审侧的最后一道核对**：把一栏回答里写到的引用抽出来，逐条问
注入的查询接口"这条在不在"，把核不到的写成一句给律师看的话，塞进
``Review.unverified``。两者共用同一组正则口径（同一批模型写出来的引用，写法
相同），但不能互相 import——那会把 ``mcp_server.client``（HTTP 客户端 + 远端
配置）拖进这个模块，纯函数单测就跑不起来了。

## 为什么不查库

本模块不 import Django、不拿 connection、不发请求：查询能力由
:class:`ReferenceLookup` 注入。同一段逻辑要在三个地方跑——请求线程、离线回归
脚本、单测——只有把数据源外置，才不用为每种场景造一套假 DB。

## 评审侧只剩两态

"核到了"与"核不到"。核不到的才进 ``unverified``；"核到了但法规已废止 / 条文
内容与所引命题不一致"属于数据源的事（威科链路有 ``validity`` / ``similarity``），
评审侧不重复判，也不假装判得了。

## 条款号在原文里的存在性：只在原文自己写了条号时才核对

真实数据源返回的 ``article_text`` 通常是**条文正文**（"夫妻一方要求离婚的，
可以由有关组织进行调解……"），里面根本没有「第一千零七十九条」。如果硬要求
条号必须出现在原文里，每一条真实引用都会被打成"未核验"，清单立刻变成噪音，
律师就会开始无视它。所以规则是：原文里**出现**条号 → 引用条号必须在其中
（这是防上游把 A 条原文贴成 B 条）；原文里**一个条号都没有** → 无从证伪，
按核到处理（宁缺勿错）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

#: 法条引用：《民法典》第一千零七十九条 / 《公司法》第32条。
#:
#: 与 ``mcp_server/tools/legal_research/citation_check.py`` 的 ``_STATUTE_RE``
#: 同源（少捕一个「第 N 款」分组：评审侧只核到条）。改任一处都要两处同批改——
#: 两边的输入是同一批模型写出来的句子，一边改另一边不改就会漏判。
STATUTE_RE = re.compile(
    # 条号两侧都允许空白：模型很常写「第 874 条」（实测 2026-11-22：综合稿里
    # 全是这种写法，旧正则一条都抽不到 → 核验返回 0 条 → 被当成"没有引用"的假绿）。
    r"《(?P<law>[^》]{2,40})》\s*第\s*(?P<article>[一二三四五六七八九十百千零〇\d]+)\s*条"
)

#: 案号：（20XX）某0105民初某某号 / （20XX）最高法民申某某号。与上面同源。
CASE_NO_RE = re.compile(
    r"[（(]\s*(?P<year>\d{4})\s*[）)]\s*(?P<court>[\u4e00-\u9fa5]{1,8}?\d{0,6}?)"
    r"(?P<type>[民刑行执商知破赔][\u4e00-\u9fa5]{0,4}?)(?P<num>\d{1,8})\s*号"
)

#: 原文里的条号（用于"条款号在原文存在性"核对）：第一千零七十九条 / 第32条。
_ARTICLE_MENTION_RE = re.compile(r"第(?P<num>[一二三四五六七八九十百千零〇\d]+)条")

#: 一份评审清单最多列多少条未核验：它要进 SSE 帧、也要进 metadata，长回答里
#: 几十条引用会把卡片撑爆。超出时补一条汇总（不静默丢）。
MAX_UNVERIFIED = 20

#: 中文数字表（与 ``mcp_server`` 侧同口径，见 :func:`_cn_to_int`）。
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


@dataclass(frozen=True)
class StatuteRef:
    """答案里的一处法条引用。

    ``raw`` 保留答案里的原样写法：未核验文案要照抄律师看得到的那句话，
    改写条号写法（"1079" ↔ "一千零七十九"）会让他在正文里搜不到。
    """

    raw: str
    law_name: str
    #: 条号折算成的整数；``None`` = 正则抓到了但折算不出来（极罕见）。
    article_no: int | None


@dataclass(frozen=True)
class CaseRef:
    """答案里的一处案号引用。"""

    raw: str
    #: 归一化案号（全角括号、空白已统一）——同一案号的两种写法只核一次。
    case_no: str


class ReferenceLookup(Protocol):
    """核验数据源。真实实现由调用方接到法条库 / 案件库，本模块不查库。"""

    def statute_text(self, law_name: str, article_no: int) -> str | None:
        """返回该法条该条的原文；库里没有这一条时返回 ``None``。"""

    def case_exists(self, case_no: str) -> bool:
        """案号在库里是否存在。"""


def _cn_to_int(text: str) -> int | None:
    """中文 / 阿拉伯条号折算成整数（支持「一千零七十九」「三十」「十五」「32」）。

    为什么要自己转而不是交给模型：转错一次（"一千零七十九" → 1009）就等于核错
    一条法条，而且错得看不出来。这里的换算与 ``mcp_server`` 侧逐字同源。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    total = 0
    section = 0
    digit = 0
    for char in raw:
        if char in _CN_DIGITS:
            digit = _CN_DIGITS[char]
            continue
        unit = _CN_UNITS.get(char)
        if unit is None:
            return None
        # 「十」单独出现时是 10（「十五」= 15），所以没有前置数字时按 1 计。
        section += (digit or 1) * unit
        digit = 0
    return total + section + digit


def _normalize_case_no(raw: str) -> str:
    """案号归一化：全角→半角统一到全角、去掉所有空白（案号里不会有空格）。"""
    return re.sub(r"\s+", "", (raw or "").replace("(", "（").replace(")", "）"))


def extract_statute_refs(text: str) -> list[StatuteRef]:
    """抽出法条引用（按 ``(法律名, 条号)`` 去重，保留首次出现的原文）。"""
    seen: set[tuple[str, int | str]] = set()
    refs: list[StatuteRef] = []
    for match in STATUTE_RE.finditer(text or ""):
        law_name = match.group("law").strip()
        article_no = _cn_to_int(match.group("article"))
        # 条号折不出来时退回原文写法做身份，免得两条不同的怪写法被并成一条。
        identity = (law_name, article_no if article_no is not None else match.group("article"))
        if identity in seen:
            continue
        seen.add(identity)
        refs.append(StatuteRef(raw=match.group(0).strip(), law_name=law_name, article_no=article_no))
    return refs


def extract_case_refs(text: str) -> list[CaseRef]:
    """抽出案号引用（按归一化案号去重，保留首次出现的原文）。"""
    seen: set[str] = set()
    refs: list[CaseRef] = []
    for match in CASE_NO_RE.finditer(text or ""):
        case_no = _normalize_case_no(match.group(0))
        if case_no in seen:
            continue
        seen.add(case_no)
        refs.append(CaseRef(raw=match.group(0).strip(), case_no=case_no))
    return refs


def _article_numbers(article_text: str) -> set[int]:
    """原文里写到的所有条号（一个都没有时返回空集，见模块 docstring）。"""
    numbers: set[int] = set()
    for match in _ARTICLE_MENTION_RE.finditer(article_text or ""):
        number = _cn_to_int(match.group("num"))
        if number is not None:
            numbers.add(number)
    return numbers


def _check_statute(ref: StatuteRef, lookup: ReferenceLookup) -> str:
    """核一条法条；核不到时返回给律师看的一句话，核到返回空串。"""
    if ref.article_no is None:
        return f"引{ref.raw}，条号无法解析（不能自动核对）"
    article_text = (lookup.statute_text(ref.law_name, ref.article_no) or "").strip()
    if not article_text:
        return f"引{ref.raw}，本轮无核验命中"
    mentioned = _article_numbers(article_text)
    if mentioned and ref.article_no not in mentioned:
        return f"引{ref.raw}，核验返回的原文里查无此条号"
    return ""


def _with_limit(messages: Sequence[str], limit: int) -> list[str]:
    """截断到 ``limit`` 条，并把被截掉的条数写成最后一行（不静默丢）。"""
    if len(messages) <= limit:
        return list(messages)
    return [*messages[:limit], f"另有 {len(messages) - limit} 处引用未核验（本清单最多列 {limit} 条）"]


def verify_references(text: str, *, lookup: ReferenceLookup, limit: int = MAX_UNVERIFIED) -> list[str]:
    """把一栏回答里**核不到**的引用写成文案列表（``Review.unverified`` 的数据源）。

    Args:
        text: 一栏回答的正文；只解析 ``《X》第N条`` 与案号，其它内容不看。
        lookup: 核验数据源（法条原文 / 案号存在性），由调用方注入。
        limit: 最多列多少条（默认 :data:`MAX_UNVERIFIED`）；超出部分折成一行汇总。

    Returns:
        未核验文案：法条在前、案号在后，各自按出现顺序去重；核到的不出现。
        没有未核验引用时返回空列表（不是 ``None``——调用方直接塞进 ``Review``）。

    Raises:
        ValueError: ``limit < 0``（负数会把清单切成"除最后一条全留下"，不是截断）。
    """
    if limit < 0:
        raise ValueError(f"limit 必须 ≥ 0，收到 {limit}")

    messages: list[str] = []
    for statute in extract_statute_refs(text):
        message = _check_statute(statute, lookup)
        if message:
            messages.append(message)
    for case in extract_case_refs(text):
        if not lookup.case_exists(case.case_no):
            messages.append(f"引案号{case.raw}，本轮无核验命中")
    return _with_limit(messages, limit)


__all__ = [
    "CASE_NO_RE",
    "MAX_UNVERIFIED",
    "STATUTE_RE",
    "CaseRef",
    "ReferenceLookup",
    "StatuteRef",
    "extract_case_refs",
    "extract_statute_refs",
    "verify_references",
]
