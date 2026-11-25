"""把一段改写写成 Word 原生修订痕迹（`w:ins` / `w:del`）。

## 为什么必须是修订痕迹，而不是直接改正文

接受修订后的正文只有一种结果，但**过程**是律师的责任证据：客户或对方质疑
「谁把这句删了」时，Word 的「审阅」面板是唯一被普遍接受的凭证。直接改写正文
等于把一次法律意见变成一次不可审计的覆盖。

## 三个真机踩过的坑（都已在这里处理）

1. **`w:id` 撞号 → Word 判定文档损坏。** 所以取号一律扫**整篇文档**已有的
   `w:ins`/`w:del` 求最大号 +1，绝不用进程内自增。
2. **`w:date` 必须是真 UTC。** 曾把本地时间（UTC+8）冒充 UTC，Word 里修订时间
   显示成 8 小时后。
3. **`w:trackChanges` 不写，Word 会把 ins/del 当「已接受的文本」显示。** 落修订
   之后必须同时在 `settings.xml` 里打开跟踪修订（见 `enable_track_changes`）。

## 语义细节

- 删掉**别人刚插入**的内容（`w:ins` 内的 run）时，按 Word 行为做「撤回」：
  直接把那段 run 拿掉，**不留删除痕迹**（留了等于把自己撤下的东西再删一次，
  审阅面板会出现一层看不懂的痕迹）。
- 覆盖到「含制表符/图片/脚注锚点」的 run 时，如果只删它的一部分，**拒绝落笔**：
  按字符切会把这些非文本内容切丢。宁可失败并让调用方把选区对齐到整段。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .locate import span_in_paragraph
from .text import run_has_complex_child, run_text, visible_text

#: AI 落笔的修订署名。
#:
#: **只允许这一个常量**：同一份文档里出现两个 AI 作者名（历史上曾有
#: `法穿AI` 与 `法穿SI` 并存）会让律师在「审阅」面板里看到两个"人"，
#: 也让按作者过滤的统计全部失真。
AI_AUTHOR = "法穿AI"

_W_R = qn("w:r")
_W_INS = qn("w:ins")
_W_DEL = qn("w:del")
_W_ID = qn("w:id")
_W_AUTHOR = qn("w:author")
_W_DATE = qn("w:date")
_W_T = qn("w:t")
_W_RPR = qn("w:rPr")
_W_DELTEXT = qn("w:delText")
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


@dataclass(frozen=True)
class RevisionResult:
    """一次落笔的结果。"""

    ok: bool
    reason: str = ""
    how: str = ""
    """命中方式（exact / normalized），便于排查「为什么这次走了归一化」。"""

    rev_ids: tuple[int, ...] = ()
    """本次写入的 `w:id`（del, ins）。后续「按 finding 撤回单条修订」要用。"""


def _document_root(paragraph: Paragraph) -> Any:
    """整篇文档的 XML 根（`w:id` 取号必须看全篇，不能只看这一段）。"""
    return paragraph.part.element


def _next_rev_id(root: Any) -> int:
    """全篇最大修订号 +1（无修订时 1）。"""
    biggest = 0
    for tag in (_W_INS, _W_DEL):
        for elem in root.iter(tag):
            raw = elem.get(_W_ID)
            if raw is None:
                continue
            try:
                biggest = max(biggest, int(raw))
            except ValueError:
                continue
    return biggest + 1


def _utc_now() -> str:
    """Word 要求的 `YYYY-MM-DDTHH:MM:SSZ`（真 UTC，不是本地时间）。"""
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run(text: str, source_run: Any, *, tag: str = "w:t") -> Any:
    """按源 run 的格式造一个只含一段文字的 run（保留字体/字号/加粗）。"""
    run = OxmlElement("w:r")
    src_rpr = source_run.find(_W_RPR) if source_run is not None else None
    if src_rpr is not None:
        import copy

        run.append(copy.deepcopy(src_rpr))
    t = OxmlElement(tag)
    t.text = text
    t.set(_XML_SPACE, "preserve")
    run.append(t)
    return run


def _make_del(text: str, *, author: str, date: str, rev_id: int, source_run: Any) -> Any:
    elem = OxmlElement("w:del")
    elem.set(_W_ID, str(rev_id))
    elem.set(_W_AUTHOR, author)
    elem.set(_W_DATE, date)
    elem.append(_make_run(text, source_run, tag="w:delText"))
    return elem


def _make_ins(text: str, *, author: str, date: str, rev_id: int, source_run: Any) -> Any:
    elem = OxmlElement("w:ins")
    elem.set(_W_ID, str(rev_id))
    elem.set(_W_AUTHOR, author)
    elem.set(_W_DATE, date)
    elem.append(_make_run(text, source_run))
    return elem


@dataclass
class _Token:
    """段落里的一段文字（一个 `w:r`，可能在 `w:ins` 里）。"""

    run: Any
    parent: Any
    text: str
    start: int
    end: int
    in_ins: bool
    complex: bool


def _tokens(paragraph: Paragraph) -> list[_Token]:
    tokens: list[_Token] = []
    cursor = 0
    for child in paragraph._element:
        if child.tag == _W_R:
            text = run_text(child)
            tokens.append(
                _Token(child, paragraph._element, text, cursor, cursor + len(text), False, run_has_complex_child(child))
            )
            cursor += len(text)
        elif child.tag == _W_INS:
            for run in child.findall(_W_R):
                text = run_text(run)
                tokens.append(_Token(run, child, text, cursor, cursor + len(text), True, run_has_complex_child(run)))
                cursor += len(text)
    return tokens


def _top_level_of(token: _Token, paragraph: Paragraph) -> Any:
    """token 在段落下的直接子元素（`w:r` 自己，或包着它的 `w:ins`）。"""
    return token.parent if token.in_ins else token.run


def apply_revision(
    paragraph: Paragraph,
    original: str,
    replacement: str,
    *,
    author: str = AI_AUTHOR,
    date: str | None = None,
) -> RevisionResult:
    """在**这一段**里把 `original` 换成 `replacement`，以修订痕迹留痕。

    定位口径与 `locate.locate` 一致（精确 → 归一化）。跨段的原文会失败：
    跨段替换等于重排结构，不是「改一句话」。
    """
    if not (original or "").strip():
        return RevisionResult(ok=False, reason="原文为空：它是定位锚点")
    if not (replacement or "").strip():
        return RevisionResult(ok=False, reason="改写为空：如需删除请保留一个占位表述")

    body = visible_text(paragraph)
    span = _span_of(paragraph, original)
    if span is None:
        return RevisionResult(ok=False, reason="本段内未找到原文片段（可能已被改写或跨段落）")
    how, (start, end) = span

    tokens = _tokens(paragraph)
    covered = [t for t in tokens if t.end > start and t.start < end]
    if not covered:
        return RevisionResult(ok=False, reason="原文落在一个不可切分的元素上（制表符/图片等），请把选区对齐到整段")

    # 部分覆盖「复杂 run」→ 拒绝：按字符切会丢制表符/图片/脚注锚点
    for tok in covered:
        partial = tok.start < start or tok.end > end
        if tok.complex and partial:
            return RevisionResult(
                ok=False,
                reason="原文跨越了含制表符/图片的片段，按字符替换会丢失非文本内容；请把选区对齐到整段",
            )

    deleted_chars: list[str] = []
    ins_touched = False
    anchor: Any | None = None
    stripped_runs: list[tuple[Any, Any]] = []

    for tok in covered:
        local_start = max(start, tok.start) - tok.start
        local_end = min(end, tok.end) - tok.start
        whole = local_start == 0 and local_end == len(tok.text)
        if tok.in_ins:
            ins_touched = True
            # 撤回别人刚插入的内容：不写删除痕迹（Word 行为）
            if not whole:
                deleted_chars.append(tok.text[local_start:local_end])
            stripped_runs.append((tok.run, tok.parent))
        else:
            deleted_chars.append(tok.text[local_start:local_end])

        if anchor is None:
            anchor = _top_level_of(tok, paragraph)

        if whole:
            tok.parent.remove(tok.run)
        else:
            _split_keep_outside(tok, local_start, local_end)

    # 空的 w:ins 不能留：Word 会当成一个零宽修订点，审阅面板里点不掉
    for parent in {id(p): p for _r, p in stripped_runs}.values():
        if parent.tag == _W_INS and not parent.findall(_W_R):
            paragraph._element.remove(parent)

    rev_id = _next_rev_id(_document_root(paragraph))
    stamp = date or _utc_now()
    source_run = covered[0].run

    new_del = None
    deleted = "".join(deleted_chars)
    if deleted:
        new_del = _make_del(deleted, author=author, date=stamp, rev_id=rev_id, source_run=source_run)
    new_ins = _make_ins(
        replacement, author=author, date=stamp, rev_id=rev_id + (1 if deleted else 0), source_run=source_run
    )

    position = _index_of(paragraph, anchor)
    for elem in (new_del, new_ins):
        if elem is None:
            continue
        if position is None:
            paragraph._element.append(elem)
        else:
            paragraph._element.insert(position, elem)
            position += 1

    written = tuple(e for e in (rev_id if deleted else None, rev_id + (1 if deleted else 0)) if e is not None)
    return RevisionResult(ok=True, how=how, rev_ids=written)


def _index_of(paragraph: Paragraph, elem: Any | None) -> int | None:
    if elem is None:
        return None
    for i, child in enumerate(paragraph._element):
        if child is elem:
            return i
    return None


def _span_of(paragraph: Paragraph, original: str) -> tuple[str, tuple[int, int]] | None:
    """段落内定位（与 `locate.locate` 同一套两层口径，只看这一段）。"""
    return span_in_paragraph(paragraph, original.strip())


def _split_keep_outside(token: _Token, local_start: int, local_end: int) -> None:
    """把被部分覆盖的 run 拆成 before / after 两块（中间那段交给 del/撤回）。

    before/after 克隆原 run 的 `rPr`，格式不变。
    """
    parent = token.parent
    before_text = token.text[:local_start]
    after_text = token.text[local_end:]

    pieces: list[object] = []
    if before_text:
        pieces.append(_make_run(before_text, token.run))
    if after_text:
        pieces.append(_make_run(after_text, token.run))

    idx = list(parent).index(token.run)
    parent.remove(token.run)
    for offset, piece in enumerate(pieces):
        parent.insert(idx + offset, piece)


def enable_track_changes(doc: Any) -> None:
    """在 `settings.xml` 里打开跟踪修订。

    不写这一项，Word 打开时会把 `w:ins`/`w:del` 当作「已接受的文本」直接显示成
    定稿——律师看不到任何痕迹，等于没留痕。
    """
    settings = doc.settings.element
    if settings.find(qn("w:trackChanges")) is not None:
        return
    settings.append(OxmlElement("w:trackChanges"))
