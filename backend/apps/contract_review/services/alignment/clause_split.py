"""中文合同条款切分（标题 → 条款编号 → 空行段落 → 句号，四级降级）。

## 为什么必须"降级"而不是"尽量切"

三份 patch 要靠 ``clause_key`` 对齐才能说"第 7.2 条有三种改法"。但合同文本的
形态并不统一：有的只有"第一章/第二章"，有的只有"第一条/第二条"，有的是空行
分段，还有的整篇没有换行。切不出来时**唯一诚实的做法是承认切不出来**：

- 四级里任何一级真的切出了 ≥2 段，才返回 ``aligned=True``；
- 四级全不命中 → ``granularity="line"``、``aligned=False``，key 是行号 ``L1``/``L2``；
- **行级 key 不是条款坐标**：``classify`` 在 ``aligned=False`` 时一律把
  ``clause_key`` 写成 ``None``，不许把"第 3 行"伪装成"第 3 条"。把行级当条款级
  会让律师看到一条根本不存在的"条款冲突"，比不切更糟。

## 四级顺序是硬的

1. **标题行**：``第一章`` / ``第二节`` / ``第三篇`` / ``第四部分`` / ``附件一`` /
   ``附录二``。只认行首的结构化标题，不猜"付款方式"这种裸标题——猜错会把
   正文里的短句当成章节。
2. **条款编号**：``第X条`` / ``一、`` / ``（一）`` / ``1.1`` / ``1.``（行首）。
3. **空行段落**：连续非空行成段（``\\n\\s*\\n`` 分隔）。
4. **句号**：``。！？!?`` 断句。

前两级各要求**至少两个标记**才算命中：只有一个"第一章"的文档切出来是一整块，
那不叫条款对齐，应该继续降级。段落/句子级同理要求 ≥2 段。

## key 的唯一性

同一份合同里"第三条"可能出现两次（正文 + 附件）。key 重复会让两份无关的
patch 被对齐到同一组，所以第二次出现起加后缀 ``#2``/``#3``。后缀只解决
**同一次切分内**的歧义；跨文档比较请用 ``(subpath, key)``。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

#: 切分粒度。``line`` 是"切不出来"的兜底，**不是**条款级。
Granularity = Literal["heading", "clause_number", "paragraph", "sentence", "line"]

#: 四级降级 + 兜底（顺序即优先级）。
GRANULARITIES: tuple[Granularity, ...] = ("heading", "clause_number", "paragraph", "sentence", "line")

#: 标题行：章/节/篇/部分/附件/附录。只匹配行首，避免正文中的"见第一章"。
_HEADING_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百千零〇0-9]+(?:章|节|篇|部分)|附件[一二三四五六七八九十0-9]+|附录[一二三四五六七八九十0-9]*)"
)

#: 条款编号：第X条 / 一、 / （一） / 1.1 / 1.。数字首段限 1-2 位，避开 2026.11.20 这类日期。
_CLAUSE_NUMBER_RE = re.compile(
    r"^(?:"
    r"第[一二三四五六七八九十百千零〇0-9]+条"
    r"|[一二三四五六七八九十百]+、"
    r"|[（(][一二三四五六七八九十百0-9]+[）)]"
    r"|\d{1,2}(?:\.\d{1,2})+(?=[\s、.．:：]|$)"
    r"|\d{1,2}[、.．](?=\s|$|[^\d])"
    r")"
)

_SENTENCE_RE = re.compile(r"[^。！？!?]*[。！？!?]|[^。！？!?]+$")

#: 行首空白（含全角空格）；定位时要从行首偏移里扣掉。
_INDENT = " \t\u3000"


@dataclass(frozen=True)
class ClauseSpan:
    """一段被切出来的文本。

    ``text`` 与 ``source[start:end]`` **逐字相等**（含原文空白），这样 patch 的
    ``original`` 可以直接在原文坐标上比对，不需要再做归一化。
    """

    key: str
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class ClauseSplit:
    """一次切分的结果。调用方必须先看 ``aligned``/``granularity`` 再决定怎么用 key。"""

    spans: tuple[ClauseSpan, ...]
    aligned: bool
    granularity: Granularity

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(span.key for span in self.spans)


def split_clauses(text: str) -> ClauseSplit:
    """按四级降级切分 ``text``；四级全不命中时返回行级且 ``aligned=False``。"""

    for granularity, splitter in _SPLITTERS:
        spans = splitter(text)
        if len(spans) >= 2:
            return ClauseSplit(spans=tuple(spans), aligned=True, granularity=granularity)
    return ClauseSplit(spans=tuple(_split_by_lines(text)), aligned=False, granularity="line")


def _split_by_headings(text: str) -> list[ClauseSpan]:
    return _split_by_markers(text, _HEADING_RE)


def _split_by_clause_numbers(text: str) -> list[ClauseSpan]:
    return _split_by_markers(text, _CLAUSE_NUMBER_RE)


def _split_by_markers(text: str, pattern: re.Pattern[str]) -> list[ClauseSpan]:
    """按行首标记切段；标记少于两个时返回空列表（继续降级）。"""

    markers = _marker_starts(text, pattern)
    if len(markers) < 2:
        return []

    segments: list[tuple[str, int, int]] = []
    first_start = markers[0][0]
    if first_start > 0 and text[:first_start].strip():
        segments.append(("前言", 0, first_start))
    for index, (start, marker) in enumerate(markers):
        end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        segments.append((_normalize_key(marker), start, end))
    return _build_spans(text, segments)


def _marker_starts(text: str, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """``[(行首非空白处偏移, 标记文本)]``。"""

    starts: list[tuple[int, str]] = []
    for line_start, line_end in _line_spans(text):
        line = text[line_start:line_end]
        stripped = line.lstrip(_INDENT)
        if not stripped:
            continue
        match = pattern.match(stripped)
        if match:
            starts.append((line_start + len(line) - len(stripped), match.group(0)))
    return starts


def _normalize_key(marker: str) -> str:
    """去掉标记尾部的分隔符：``一、`` → ``一``，``1.`` → ``1``。"""

    return marker.rstrip(" \t\r\n、.．:：")


def _split_by_paragraphs(text: str) -> list[ClauseSpan]:
    segments: list[tuple[str, int, int]] = []
    start: int | None = None
    end = 0
    for line_start, line_end in _line_spans(text):
        if text[line_start:line_end].strip():
            if start is None:
                start = line_start
            end = line_end
        elif start is not None:
            segments.append((f"P{len(segments) + 1}", start, end))
            start = None
    if start is not None:
        segments.append((f"P{len(segments) + 1}", start, end))
    return _build_spans(text, segments)


def _split_by_sentences(text: str) -> list[ClauseSpan]:
    segments: list[tuple[str, int, int]] = []
    for match in _SENTENCE_RE.finditer(text):
        chunk = match.group(0)
        stripped = chunk.strip()
        if not stripped:
            continue
        chunk_start = match.start()
        start = chunk_start + len(chunk) - len(chunk.lstrip())
        end = chunk_start + len(chunk.rstrip())
        segments.append((f"S{len(segments) + 1}", start, end))
    return _build_spans(text, segments)


def _split_by_lines(text: str) -> list[ClauseSpan]:
    """最后兜底：非空行各成一段。key 是行号，**不是条款坐标**。"""

    segments: list[tuple[str, int, int]] = []
    for line_start, line_end in _line_spans(text):
        if not text[line_start:line_end].strip():
            continue
        start = line_start + len(text[line_start:line_end]) - len(text[line_start:line_end].lstrip(_INDENT))
        segments.append((f"L{len(segments) + 1}", start, line_end))
    return _build_spans(text, segments)


def _line_spans(text: str) -> list[tuple[int, int]]:
    """每行的 ``[start, end)``；保留行尾换行，保证覆盖全文。"""

    spans: list[tuple[int, int]] = []
    position = 0
    for line in text.splitlines(keepends=True):
        spans.append((position, position + len(line)))
        position += len(line)
    return spans


def _build_spans(text: str, segments: Sequence[tuple[str, int, int]]) -> list[ClauseSpan]:
    """``(raw_key, start, end)`` → `ClauseSpan`，重复 key 加 ``#n`` 后缀。"""

    seen: dict[str, int] = {}
    spans: list[ClauseSpan] = []
    for raw_key, start, end in segments:
        count = seen.get(raw_key, 0) + 1
        seen[raw_key] = count
        key = raw_key if count == 1 else f"{raw_key}#{count}"
        spans.append(ClauseSpan(key=key, text=text[start:end], start=start, end=end))
    return spans


_SPLITTERS: tuple[tuple[Granularity, Callable[[str], list[ClauseSpan]]], ...] = (
    ("heading", _split_by_headings),
    ("clause_number", _split_by_clause_numbers),
    ("paragraph", _split_by_paragraphs),
    ("sentence", _split_by_sentences),
)


__all__ = ["ClauseSpan", "ClauseSplit", "GRANULARITIES", "Granularity", "split_clauses"]
