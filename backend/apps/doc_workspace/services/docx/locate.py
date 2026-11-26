"""按原文在 docx 里定位落笔区间——不做「最像哪一段」的猜测。

## 三条纪律

1. **锚点是内容，不是坐标。** 段落序号会因前文任何一次增删而漂移；LLM 数出来的
   段号更是和程序数的对不上（表格、编号、页眉全错位）。所以只认原文。
2. **重复就报错，不取第一条。** 合同里「甲方应于本协议签订之日起」这种句子
   完全可能出现在两处。取第一条的结果是「改错地方」——比失败严重得多。
   失败时把候选数回给调用方，让模型自己把选区拉长到唯一。
3. **只降两层，不降到「近似」。** 精确子串 → 归一化（折叠全半角 + 去空白）。
   再往下就是猜，宁可 `None`。

**为什么不复用 `apps/contract_review` 里那套**：目标是让画布链路不再依赖那个
app（它即将整体移除）。这里是一份独立实现，口径与 `text.visible_text` 对齐。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from docx.document import Document as DocumentType
from docx.text.paragraph import Paragraph

from .text import iter_paragraphs, visible_text


@dataclass(frozen=True)
class LocateHit:
    """一次成功的定位。"""

    paragraph: Paragraph
    """命中的段落（可能是表格单元格内的段落）。"""

    how: str
    """命中方式：`exact` 逐字 / `normalized` 归一化后匹配。"""

    span: tuple[int, int]
    """在 `visible_text(paragraph)` 中的半开区间 `[start, end)`。"""

    @property
    def matched_text(self) -> str:
        return visible_text(self.paragraph)[self.span[0] : self.span[1]]


@dataclass(frozen=True)
class LocateFailure:
    """定位失败——带足够信息让调用方（人或模型）自纠。"""

    reason: str
    candidates: int = 0
    """命中的候选段落数。>1 表示原文不唯一，需要把选区拉长。"""


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """归一化并保留「归一化后第 i 个字符 ← 原文第几个字符」的映射。

    NFKC 会把一个字符展开成多个（`ﬁ` → `fi`），所以映射是 list 而不是一对一。
    映射是必须的：落笔要删的是**文档里的真实区间**，只有归一化后的位置没用。
    """
    out: list[str] = []
    idx_map: list[int] = []
    for i, ch in enumerate(text):
        folded = unicodedata.normalize("NFKC", ch)
        if folded.strip() == "" and folded != "\u00a0":
            # 空白不参与比对（与 text.normalize 同口径）
            continue
        for c in folded:
            out.append(c)
            idx_map.append(i)
    return "".join(out), idx_map


def span_in_paragraph(paragraph: Paragraph, selection: str) -> tuple[str, tuple[int, int]] | None:
    """在这一段里找选区，返回 (命中方式, 原坐标区间)；找不到返回 None。

    公开成函数而不是留在 `locate()` 内部：`revision` 拿到已经定位好的段落之后
    还要在同一段上重算一次区间（段落对象无法从 `LocateHit` 之外反推坐标）。
    """
    body = visible_text(paragraph)
    if not body:
        return None

    start = body.find(selection)
    if start >= 0:
        return "exact", (start, start + len(selection))

    # 归一化层：处理「空格多/少、全角半角、零宽字符」造成的逐字不匹配
    norm_body, idx_map = _normalize_with_map(body)
    norm_sel, _ = _normalize_with_map(selection)
    if not norm_sel:
        return None
    n_start = norm_body.find(norm_sel)
    if n_start < 0:
        return None
    n_end = n_start + len(norm_sel)
    return "normalized", (idx_map[n_start], idx_map[n_end - 1] + 1)


def locate(
    doc: DocumentType,
    selection: str,
    *,
    require_unique: bool = True,
) -> LocateHit | LocateFailure:
    """在整篇文档里定位选区（含表格内段落）。

    `require_unique=True`（默认）下，命中段落数 > 1 直接失败——改错位置比改不动
    严重得多。调用方据 `candidates` 把选区加长后重试。
    """
    probe = (selection or "").strip()
    if not probe:
        return LocateFailure(reason="选区为空：原文片段是定位锚点，必须给出")

    hits: list[LocateHit] = []
    for paragraph in iter_paragraphs(doc):
        found = span_in_paragraph(paragraph, probe)
        if found is None:
            continue
        how, span = found
        hits.append(LocateHit(paragraph=paragraph, how=how, span=span))
        if len(hits) > 1 and require_unique:
            # 早退：已经不唯一了，继续扫只是浪费
            return LocateFailure(
                reason=(
                    f"原文在文档中出现多次（已找到 {len(hits)} 处），无法确定改哪一处；"
                    "请把原文片段加长到唯一（连同前后条款文字一起给出）"
                ),
                candidates=len(hits),
            )

    if not hits:
        return LocateFailure(reason="未在文档中找到该原文片段（可能已被改写或跨段落）")
    return hits[0]
