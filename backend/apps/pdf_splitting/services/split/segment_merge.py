r"""相邻分段的「续页合并」后处理。

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
3. **续页证据**——后段首页首行能解析出条款/编号序号，**且**前段末页能解析出
   **同一编号体系**的序号，且后段序号严格大于前段序号。

判据 3 的取向和 di-re 的 `_leading_label_trimmed_start` 一致：**只用版面/结构事实，
不猜语义**；而且方向是「宁可少合并，不可误合并」——误合并会把两份不同材料粘在
一起，比多切一段更难发现。

### 为什么序号必须「两侧都解析得出、且同体系」

旧判据是「两侧都能解析才校验，否则跳过校验直接合并」，两个方向都出过错：

- **误并**：`一、` / `1、` 开头能触发合并，但序号解析只认 `X.Y` / `第X条`，
  于是校验被跳过 → 两份同类型相邻材料（两份证据清单）被粘成一份。
- **漏并**：末页「最后一个 `\d+\.\d+`」把表格里的金额/面积/日期当条款号
  （164 页真实卷宗只读实测：`0.31`、`146.75`、`15000.41`、`125493.76`、
  `8.81m2`、`2020.04`、`1310000.00`、`1116075562.1116076` 全被当成过条款号），
  序号「不推进」→ 真续页并不回。

所以现在：**解析不出序号就不合并**；末页序号只认**行首**候选（实测全部误认
都发生在行中间的表格/地址里），并排除金额单位与超位整数；不同编号体系
（`X.Y` 条款 vs `一、` 列表）不可比，跨体系一律不合并。

### 编号体系之外的续页（本模块救不了，交给边界二审）

实测最典型的一份被切开的合同（p116-125 / p126-140），p125 末行是
「5.3 抵押担保的范围为…提前还款补偿」，p126 首行是「金、损害赔偿金和实现
债权及抵押权的费用。」——**半句话跨页**，首行根本没有序号。这种续页靠序号
判据永远并不回，由 `review_suspicious_boundaries` 拿两侧整页全文复核。

## 为什么不做「merged_pages 上限」之外的智能

有人会想「同类型连续 25 页肯定是同一份」——不对。实测里 p51-63 和 p64-69
都是 `bank_statement`，但那是**两个不同当事人**的流水（甲某 / 乙某），
必须分开。所以长度不能当证据。
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from itertools import pairwise
from typing import Any

from apps.pdf_splitting.models import PdfSplitReviewFlag

logger = logging.getLogger("apps.pdf_splitting")

#: 条款/编号开头的形态。命中说明这一页**可能**是上一页的续（还要过序号校验）。
_CLAUSE_START_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百]+条|第\d+条|\d+\.\d+(?:\.\d+)?|[一二三四五六七八九十]+、|\d+、)"
)

#: 这些行视为「材料开头」的标志（出现即不合并）。
_DOC_HEADING_HINTS = ("合同", "协议", "证明", "证书", "报告", "清单", "通知书", "申请书", "确认书", "回单", "凭证")

#: 单次合并后的最大页数上限。超过就不合了——防止把整本卷宗粘成一段。
#:
#: 80 页的依据：分段批大小 25 页（`segment_batch.DEFAULT_SEGMENT_BATCH_PAGES`），
#: 一份长合同被批界切开时最坏可跨 3 批 ≈ 75 页；旧的 40 页上限让「25+25 跨批
#: 长合同」永远合并不了。取 80（3 批 + 余量）既接得住跨批长合同，又远小于
#: 实测整本 164 页，不会把整本粘成一段。实测最长单份材料 31 页（估价报告）。
MAX_MERGED_PAGES = 80

#: 编号体系。跨体系比大小没有意义（条款 5.3 与列表「六、」不可比），
#: 只有同体系的序号推进才算续页证据。
KIND_DECIMAL = "decimal"
KIND_ARTICLE = "article"
KIND_LIST = "list"

#: 行首十进制条款号：整数部分最多 2 位、小数部分最多 2 位，后面不能再接数字。
#: 整数位上限直接排除实测误认的金额（1310000.00 / 125493.76 / 15000.41）、
#: 日期（2020.04）与证号拼接（1116075562.1116076）；「51,099.70」这类千分位
#: 金额也匹配不上（整数位后是逗号不是点）。
_DECIMAL_REF_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?!\d)")
#: 金额/面积/比例单位：行首「8.81m2」「1.00 元」即便整数位很小也不是条款号。
_UNIT_SUFFIX_RE = re.compile(r"^\s*(?:元|万元|平方米|㎡|m2|%|％)")
_ARTICLE_REF_RE = re.compile(r"^第([一二三四五六七八九十百]+|\d+)条")
_LIST_REF_RE = re.compile(r"^(?:[（(]([一二三四五六七八九十]+|\d+)[）)]|([一二三四五六七八九十]+|\d+)、)")

#: 复核标记的严重度：合并/疑点标定时取**更差**的那个，不让低置信证据被高置信掩盖。
_REVIEW_FLAG_SEVERITY = {
    str(PdfSplitReviewFlag.NORMAL): 0,
    str(PdfSplitReviewFlag.LOW_CONFIDENCE): 1,
    str(PdfSplitReviewFlag.OCR_FAILED): 2,
    str(PdfSplitReviewFlag.UNRECOGNIZED): 3,
}


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


def _line_clause_ref(line: str) -> tuple[str, float] | None:
    """解析一行开头的条款/编号序号，返回 (编号体系, 序号)。

    支持 `X.Y` 条款、`第X条`、`一、` / `1、` / `（一）` / `(1)` 列表编号。
    解析不出就返回 None——调用方据此**不合并**（旧逻辑跳过校验直接合并，
    是两份同类型相邻材料被误并的直接原因）。
    """
    stripped = line.strip()
    if not stripped:
        return None
    decimal = _DECIMAL_REF_RE.match(stripped)
    if decimal:
        if _UNIT_SUFFIX_RE.match(stripped[decimal.end() :]):
            return None
        return KIND_DECIMAL, float(f"{decimal.group(1)}.{decimal.group(2)}")
    article = _ARTICLE_REF_RE.match(stripped)
    if article:
        return _numbered_ref(KIND_ARTICLE, article.group(1))
    listed = _LIST_REF_RE.match(stripped)
    if listed:
        return _numbered_ref(KIND_LIST, listed.group(1) or listed.group(2))
    return None


def _numbered_ref(kind: str, token: str) -> tuple[str, float] | None:
    digits = int(token) if token.isdigit() else _cn_to_int(token)
    return (kind, float(digits)) if digits is not None else None


def _clause_ref(text: str) -> tuple[str, float] | None:
    """取首页首行的条款/编号序号。"""
    return _line_clause_ref(_first_line(text))


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


def _tail_clause_ref(text: str) -> tuple[str, float] | None:
    """取末页**最后一个行首**条款序号。

    只扫行首，不再取「全文最后一个 `\\d+\\.\\d+`」：164 页真实卷宗只读实测，
    末页最后一个十进制数几乎总是表格里的金额/面积/日期（`0.31`、`146.75`、
    `15000.41`、`8.81m2`、`2020.04`、`1310000.00`），把它们当条款号会让
    「序号不推进」成立，真续页反而并不回。行首 + 位数 + 单位三道判据
    把实测全部误认排除，同时保住真条款号（`5.3 抵押担保的范围为…`）。
    """
    found: tuple[str, float] | None = None
    for line in (text or "").splitlines():
        ref = _line_clause_ref(line)
        if ref is not None:
            found = ref
    return found


def should_merge(prev_text: str, next_text: str, *, prev_pages: int, next_pages: int) -> bool:
    """判断后一段是否只是前一段的续页。

    取向是「宁可少合并，不可误合并」：任何一侧解析不出序号、或两侧编号
    体系不同，都不合并。
    """
    if prev_pages + next_pages > MAX_MERGED_PAGES:
        return False
    # 后段首页像新材料开头 → 不合并
    if _looks_like_doc_heading(next_text):
        return False
    next_ref = _clause_ref(next_text)
    if next_ref is None:
        return False
    prev_ref = _tail_clause_ref(prev_text)
    if prev_ref is None:
        return False
    # 跨编号体系不可比：条款 5.3 与列表「六、」比大小会误并
    if prev_ref[0] != next_ref[0]:
        return False
    return next_ref[1] > prev_ref[1]


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
                merged[-1] = _merged_draft(prev, current)
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


def _merged_draft(prev: Any, current: Any) -> Any:
    """合并两段：页区间取并，置信度/复核标记取**更差**的一侧。

    旧逻辑只改 page_end，被并段的低置信度不带入合并段——一段「半份合同 +
    半份低置信续页」会以 NORMAL 呈现，律师按低置信筛复核时正好漏掉它。
    """
    return replace(
        prev,
        page_end=int(current.page_end),
        confidence=min(float(prev.confidence), float(current.confidence)),
        review_flag=_worse_review_flag(prev.review_flag, current.review_flag),
    )


def _worse_review_flag(left: Any, right: Any) -> str:
    a, b = str(left), str(right)
    return b if _REVIEW_FLAG_SEVERITY.get(b, 1) > _REVIEW_FLAG_SEVERITY.get(a, 1) else a


# ── 边界二审（P2-9a）────────────────────────────────────────────
#
# 为什么需要它：序号判据只能救「条款号连续推进」的合同。实测最典型的
# 一份被切开的合同（p116-125 / p126-140）是**半句话跨页**（p125 末行
# 「…提前还款补偿」→ p126 首行「金、损害赔偿金…」），首行没有序号，
# 序号判据永远并不回。而 p126 恰好是批界（164 页 / 25 页一批 → 批首
# 1, 26, 51, 76, 101, 126, 151），正是左上下文缺失最严重的地方。
#
# 保守边界：只看疑点、总次数封顶、失败保持原样。二审是锦上添花，
# 绝不能因为它挂掉就把本来正确的边界乱切。

#: 二审总次数上限。4 次的依据：164 页真实卷宗实测挑出 14 个疑点边界
#: （6 个批界里 5 个真的落在段界上 + 低置信边界），全审会让 LLM 调用数翻倍。
#: 取 4 覆盖最结构性薄弱的前几个（实测选中 26/51/101/126，其中 126 正是那份
#: 被半句话切开的合同），并行跑墙钟约等于一次二审（90s），落在阶段预算内。
#: 没审到的疑点不静默放过：由 `mark_unverified_boundaries` 标低置信供律师复核。
MAX_BOUNDARY_REVIEWS = 4


def collect_boundary_suspects(segments: list[Any], *, batch_start_pages: set[int]) -> list[int]:
    """挑出需要二审的边界（用**后段起始页**标识），批界优先、其次低置信。

    批界排前面：它是设计已知的薄弱点（左上下文缺失），而低置信只是模型
    自报的把握值，无校准、习惯给 0.9+（见 B6）。
    """
    scored: list[tuple[int, int]] = []
    for prev, current in pairwise(segments):
        boundary = int(current.page_start)
        if boundary != int(prev.page_end) + 1:
            continue
        if boundary in batch_start_pages:
            scored.append((0, boundary))
        elif _is_review_worthy(prev) or _is_review_worthy(current):
            scored.append((1, boundary))
    scored.sort()
    return [boundary for _priority, boundary in scored]


def _is_review_worthy(segment: Any) -> bool:
    return str(getattr(segment, "review_flag", "")) != str(PdfSplitReviewFlag.NORMAL)


def apply_boundary_verdict(segments: list[Any], *, boundary_page: int, action: str) -> list[Any]:
    """按二审结论改一条边界；动作未知或改动不可行时**原样返回**。

    - merge：后段整体并入前段（同一份材料被切开）
    - move_left：前段末页其实属于后段（边界左移一页）
    - move_right：后段首页其实属于前段（边界右移一页）

    三种改动都保持整覆盖、不产生重叠；移动时不允许把某一段移成空段。
    """
    index = _boundary_index(segments, boundary_page)
    if index is None or action == "keep":
        return list(segments)
    prev, current = segments[index], segments[index + 1]
    replacement = _boundary_replacement(prev, current, action=action, boundary_page=boundary_page)
    if replacement is None:
        return list(segments)
    changed = list(segments)
    changed[index : index + 2] = replacement
    logger.info(
        "pdf_split_boundary_review_applied",
        extra={"boundary_page": boundary_page, "action": action},
    )
    return [replace(item, order=i) for i, item in enumerate(changed)]


def _boundary_index(segments: list[Any], boundary_page: int) -> int | None:
    for index in range(len(segments) - 1):
        if int(segments[index].page_end) == boundary_page - 1 and int(segments[index + 1].page_start) == boundary_page:
            return index
    return None


def _boundary_replacement(prev: Any, current: Any, *, action: str, boundary_page: int) -> list[Any] | None:
    """算出替换这两段的新段列表；不可行返回 None（调用方保持原边界）。"""
    if action == "merge":
        if int(current.page_end) - int(prev.page_start) + 1 > MAX_MERGED_PAGES:
            return None
        return [_merged_draft(prev, current)]
    if action == "move_left":
        if int(prev.page_end) - int(prev.page_start) < 1:
            return None
        return [replace(prev, page_end=boundary_page - 2), replace(current, page_start=boundary_page - 1)]
    if action == "move_right":
        if int(current.page_end) - int(current.page_start) < 1:
            return None
        return [replace(prev, page_end=boundary_page), replace(current, page_start=boundary_page + 1)]
    return None


def mark_unverified_boundaries(segments: list[Any], *, boundary_pages: set[int]) -> list[Any]:
    """把「有疑点但没复核成」的边界后段标为低置信。

    这是 B6 的保守校准：不动 LLM 自报的 confidence 数值（无校准依据），
    只用**结构信号**补复核标记——批界是已知薄弱点，二审又没给出结论
    （超次数上限 / 调用失败 / 输出非法），那这一段就该让律师看一眼。
    """
    if not boundary_pages:
        return list(segments)
    marked: list[Any] = []
    for item in segments:
        if int(item.page_start) in boundary_pages:
            marked.append(
                replace(item, review_flag=_worse_review_flag(item.review_flag, PdfSplitReviewFlag.LOW_CONFIDENCE))
            )
            continue
        marked.append(item)
    return marked
