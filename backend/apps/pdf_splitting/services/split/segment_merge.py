"""相邻分段的「续页合并」后处理。

## 要解决的问题

LLM 分段会**切错跨页的材料**。实测一份 164 页卷宗里：

```
36  p116-125  loan_contract  个人房产抵押贷款合同   ← 封面 + 特别告知 + 前几条
37  p126-140  loan_contract  个人房产抵押贷款合同   ← 第五条续 → 签署页
```

这不是两份合同，是**同一份被从中间切开**。证据：

- p125 结尾是 `3.9 还款账户被有权机关冻…`，p126 开头是 `5.4 借款人应…办理抵押登记`
  —— 条款序号连续推进，中间没有新标题；
- p140 是签署页（户籍所在地/通讯地址/联系电话），合同到这才结束；
- p141 才出现下一份材料的标题（`(适用于完善送达条款)`）。

不合并的后果：

1. 归案后出现两个同名材料，律师分不清哪份是完整的；
2. 后续「按材料生成起诉状」会拿半份合同去生成，条款缺失。

## 判据（三条同时成立才合并）

1. **同类型**：两段 `segment_type` 相同（不同材料的类型几乎必然不同）。
2. **页相邻**：前段 `page_end + 1 == 后段 page_start`（中间不能有别的材料隔着）。
3. **续页证据**——满足任一：
   - 后段首页**不是**一个「材料开头」（没有标题行、没有落款、没有 strong keyword 命中）；
   - 后段首页开头是条款/编号的延续（`第X条`、`X.Y`、`一、`…且序号大于前段末页的）。

判据 3 的取向和 di-re 的 `_leading_label_trimmed_start` 一致：**只用版面/结构事实，
不猜语义**；而且方向是「宁可少合并，不可误合并」——误合并会把两份不同材料粘在
一起，比多切一段更难发现。

## 为什么不做「merged_pages 上限」之外的智能

有人会想「同类型连续 25 页肯定是同一份」——不对。实测里 p51-63 和 p64-69
都是 `bank_statement`，但那是**两个不同当事人**的流水（甲某 / 乙某），
必须分开。所以长度不能当证据。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("apps.pdf_splitting")

#: 条款/编号开头的形态。命中说明这一页是上一页的续，不是新材料开头。
_CLAUSE_START_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百]+条|第\d+条|\d+\.\d+(?:\.\d+)?|[一二三四五六七八九十]+、|\d+、)"
)

#: 这些行视为「材料开头」的标志（出现即不合并）。
_DOC_HEADING_HINTS = ("合同", "协议", "证明", "证书", "报告", "清单", "通知书", "申请书", "确认书", "回单", "凭证")

#: 单次合并后的最大页数上限。超过就不合了——防止把整本卷宗粘成一段。
MAX_MERGED_PAGES = 40


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _looks_like_doc_heading(text: str) -> bool:
    """后段首页是否像一个「新材料开头」。

    ⚠️ 必须先排除条款行：合同正文里「本合同」二字满篇都是，
      「5.4 借款人应在本**合同**签订后…办理抵押登记」曾被误判成标题，
    导致真实的续页不合并（实测挂掉一条用例）。条款行是**正文**，
    它恰恰是「这一页在续上一页」的证据。
    """
    head = _first_line(text)
    if not head:
        return False
    if _CLAUSE_START_RE.match(head):
        return False
    # 标题里带这些词 + 篇幅短（标题一般不会很长）→ 视为新材料开头
    return len(head) <= 40 and any(hint in head for hint in _DOC_HEADING_HINTS)


def _looks_like_clause_continuation(text: str) -> bool:
    head = _first_line(text)
    return bool(_CLAUSE_START_RE.match(head))


def _clause_number(text: str) -> float | None:
    """取首条条款的序号，用于判断「序号在推进」。"""
    head = _first_line(text)
    m = re.match(r"^\s*(\d+)\.(\d+)", head)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}")
    m = re.match(r"^\s*第([一二三四五六七八九十百]+)条", head)
    if m:
        digits = _cn_to_int(m.group(1))
        return float(digits) if digits is not None else None
    return None


_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(text: str) -> int | None:
    """把「六」「十二」「二十一」这类中文数字转成 int（够用即可）。"""
    if not text:
        return None
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return _CN_DIGITS.get(text)


def _tail_clause_number(text: str) -> float | None:
    """取末页最后一个条款序号。"""
    matches = list(re.finditer(r"(\d+)\.(\d+)", text or ""))
    if not matches:
        return None
    last = matches[-1]
    try:
        return float(f"{last.group(1)}.{last.group(2)}")
    except ValueError:
        return None


def should_merge(prev_text: str, next_text: str, *, prev_pages: int, next_pages: int) -> bool:
    """判断后一段是否只是前一段的续页。"""
    if prev_pages + next_pages > MAX_MERGED_PAGES:
        return False
    # 后段首页像新材料开头 → 不合并
    if _looks_like_doc_heading(next_text):
        return False
    if not _looks_like_clause_continuation(next_text):
        return False
    # 条款序号必须推进（否则可能是并列的另一份）
    prev_num = _tail_clause_number(prev_text)
    next_num = _clause_number(next_text)
    if prev_num is not None and next_num is not None and next_num <= prev_num:
        return False
    return True


def merge_continuation_segments(
    segments: list[Any],
    pages_text: dict[int, str],
) -> list[Any]:
    """把误切的续页段合回前一段。

    Args:
        segments: 已按 page_start 排好序的分段（元素需有 page_start/page_end/segment_type）。
        pages_text: `{页码: 该页正文}`，用于判断续页证据。

    Returns:
        合并后的新列表（不改原对象）。
    """
    if len(segments) <= 1:
        return list(segments)

    from dataclasses import replace

    merged: list[Any] = [segments[0]]
    merges: list[tuple[int, int]] = []

    for current in segments[1:]:
        prev = merged[-1]
        prev_pages = int(prev.page_end) - int(prev.page_start) + 1
        next_pages = int(current.page_end) - int(current.page_start) + 1

        same_type = str(getattr(prev, "segment_type", "")) == str(getattr(current, "segment_type", ""))
        adjacent = int(current.page_start) == int(prev.page_end) + 1

        if same_type and adjacent:
            prev_text = pages_text.get(int(prev.page_end), "")
            next_text = pages_text.get(int(current.page_start), "")
            if should_merge(prev_text, next_text, prev_pages=prev_pages, next_pages=next_pages):
                merged[-1] = replace(prev, page_end=int(current.page_end))
                merges.append((int(prev.page_start), int(current.page_end)))
                continue

        merged.append(current)

    if merges:
        logger.info(
            "pdf_split_segments_merged",
            extra={"before": len(segments), "after": len(merged), "merges": merges[:10]},
        )

    # 重排 order（合并后序号会跳）
    return [replace(item, order=index) for index, item in enumerate(merged)]
