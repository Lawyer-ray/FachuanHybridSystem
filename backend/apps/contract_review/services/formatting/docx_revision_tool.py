from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone

_CST = timezone(timedelta(hours=8))

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

logger = logging.getLogger(__name__)

AUTHOR = "法穿SI"

_rev_id_counter = 1


def _next_rev_id() -> str:
    global _rev_id_counter
    _rev_id_counter += 1
    return str(_rev_id_counter)


class DocxRevisionTool:
    """通过 lxml 操作 OOXML 实现 Track Changes（修订模式）"""

    def apply_revision(
        self,
        paragraph: Paragraph,
        original: str,
        replacement: str,
        author: str | None = None,
    ) -> bool:
        """在段落中定位原文，插入 <w:del> 和 <w:ins> 修订标记。
        先尝试单 run 匹配，失败则跨 run 匹配（空白容忍，见 _find_span）。
        """
        author = author or AUTHOR
        date = datetime.now(tz=_CST).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 尝试单 run 精确匹配
        for run in paragraph.runs:
            if original in run.text:
                self._apply_single_run(paragraph, run, original, replacement, author, date)
                return True

        # 跨 run 匹配：拼接段落「现行文本」查找。模板空位（下划线空格）
        # 与编辑器复制会把连续空格折叠或展开，精确比对必然误判「找不到」；
        # 已带修订痕迹的段落里，现行文本在 w:ins 内（python-docx 的
        # paragraph.text 看不见）——统一走空白容忍的 _find_span + 现行文本
        # 序列（_content_runs），真实内容不同才算找不到
        if _find_span(visible_text(paragraph), original) is None:
            logger.warning("未在段落中找到原文: %s", original[:60])
            return False

        return self._apply_cross_run(paragraph, original, replacement, author, date)

    def _apply_single_run(
        self,
        paragraph: Paragraph,
        run: Run,
        original: str,
        replacement: str,
        author: str,
        date: str,
    ) -> None:
        """原文在单个 run 内的情况"""
        run_elem = run._element
        text = run.text
        start = text.index(original)
        prefix = text[:start]
        suffix = text[start + len(original) :]

        parent = run_elem.getparent()
        idx = list(parent).index(run_elem)
        parent.remove(run_elem)

        insert_pos = idx

        if prefix:
            parent.insert(insert_pos, _make_run(prefix, run_elem))
            insert_pos += 1

        parent.insert(insert_pos, _create_del(original, author, date, run_elem))
        insert_pos += 1

        parent.insert(insert_pos, _create_ins(replacement, author, date, run_elem))
        insert_pos += 1

        if suffix:
            parent.insert(insert_pos, _make_run(suffix, run_elem))

    def _apply_cross_run(
        self,
        paragraph: Paragraph,
        original: str,
        replacement: str,
        author: str,
        date: str,
    ) -> bool:
        """原文跨多个 run 的情况：在「现行文本」序列上找区间并落修订。

        现行文本 = 直接 run + w:ins（修订插入也是正文，python-docx 的
        paragraph.text 看不见它）；w:del 里的 delText 不算（已删内容）。
        落笔规则与 Word 修订语义一致：
        - 覆盖到的**直接 run** 文本 → 包进一个 w:del（删除线痕迹）；
        - 覆盖到的 **w:ins 文本** → 直接撤回（未接受的插入被替换时不留
          删除痕迹——Word 里删自己未接受的插入正是这个行为）；
        - 区间边界只吃掉覆盖部分：残余留在**同类容器**里（ins 里的残余
          另起一个 ins，不降级成普通文本）。
        """
        items = _content_units(paragraph)
        if not items:
            return False

        offsets: list[tuple[int, int]] = []
        pos = 0
        for text, _, _ in items:
            offsets.append((pos, pos + len(text)))
            pos += len(text)

        full_text = "".join(text for text, _, _ in items)
        span = _find_span(full_text, original)
        if span is None:
            return False

        idx, end_idx = span

        first_item = last_item = -1
        for i, (s, e) in enumerate(offsets):
            if s < end_idx and e > idx:
                if first_item < 0:
                    first_item = i
                last_item = i
        if first_item < 0:
            return False

        p_elem = paragraph._element
        # 新 ins 的格式参考：区间起点所在单元的首个 run
        ref_elem = _unit_format_source(items[first_item][1], items[first_item][2])

        # 原位下标必须在手术前记录：首个覆盖单元可能被整只移除，且它的
        # p 层后继也可能同批被删（跨多 run 全覆盖）——按兄弟元素定位会退化
        # 成段尾插入，修订块落到段落末尾、残余 run 语序被打乱。前置元素不会
        # 被手术触碰，下标在术后依然有效。
        first_elem = items[first_item][1]
        insert_pos = list(p_elem).index(first_elem)
        after_anchor: etree._Element | None = None

        # 逐单元手术：撤回覆盖文本，残余留在同类容器
        del_pieces: list[str] = []  # 直接 run 的被覆盖文本 → 共享 w:del
        for i in range(first_item, last_item + 1):
            text, elem, is_ins = items[i]
            s, e = offsets[i]
            local_start = max(0, idx - s)
            local_end = min(len(text), end_idx - s)
            keep_before = text[:local_start]
            keep_after = text[local_end:]
            if not is_ins:
                del_pieces.append(text[local_start:local_end])
            kept, _tail = _withdraw_unit_text(elem, is_ins, keep_before, keep_after)
            if i == first_item and kept is not None:
                # 首单元带前缀保留：del/ins 落它后面（addnext 比下标稳，
                # 不受后续新增残余元素的影响）
                after_anchor = kept  # 直接 run 或 ins，都在 p 层

        elements: list[etree._Element] = []
        # 删除痕迹写文档**实际**区间文本：空白容忍匹配下选区与原文的空白
        # 可能不一致，照抄 original 会让 del 内容与被删 run 对不上账
        if del_pieces:
            elements.append(_create_del("".join(del_pieces), author, date, ref_elem))
        elements.append(_create_ins(replacement, author, date, ref_elem))

        if after_anchor is not None and after_anchor.getparent() is p_elem:
            for elem in reversed(elements):
                after_anchor.addnext(elem)
        else:
            pos = min(insert_pos, len(p_elem))
            for i, elem in enumerate(elements):
                p_elem.insert(pos + i, elem)
        return True


def _create_del(text: str, author: str, date: str, source_run: etree._Element) -> etree._Element:  # pragma: no cover
    """创建 <w:del> 删除标记"""
    del_elem = OxmlElement("w:del")
    del_elem.set(qn("w:id"), _next_rev_id())
    del_elem.set(qn("w:author"), author)
    del_elem.set(qn("w:date"), date)
    del_elem.append(_make_run(text, source_run, tag="w:delText"))
    return del_elem


def _create_ins(text: str, author: str, date: str, source_run: etree._Element) -> etree._Element:  # pragma: no cover
    """创建 <w:ins> 插入标记"""
    ins_elem = OxmlElement("w:ins")
    ins_elem.set(qn("w:id"), _next_rev_id())
    ins_elem.set(qn("w:author"), author)
    ins_elem.set(qn("w:date"), date)
    ins_elem.append(_make_run(text, source_run))
    return ins_elem


def _make_run(text: str, source_run: etree._Element, tag: str = "w:t") -> etree._Element:  # pragma: no cover
    """创建 <w:r>，复制源 run 的格式"""
    r = OxmlElement("w:r")
    source_elem = getattr(source_run, "_element", source_run)
    rpr = source_elem.find(qn("w:rPr"))
    if rpr is not None:
        r.append(deepcopy(rpr))
    t = OxmlElement(tag)
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _run_text(run_elem: etree._Element) -> str:
    """run 的可见文本（拼接其全部 w:t；delText 不在此列）。"""
    return "".join(t.text or "" for t in run_elem.findall(qn("w:t")))


def _set_run_text(run_elem: etree._Element, text: str) -> None:
    """重设 run 文本：收敛为单个 w:t（保留 rPr 等其它子元素）。"""
    for t in run_elem.findall(qn("w:t")):
        run_elem.remove(t)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run_elem.append(t)


def _content_units(paragraph: Paragraph) -> list[tuple[str, etree._Element, bool]]:
    """段落的「现行文本」单元序列：(文本, 元素, 是否 ins)，文档序。

    - 直接子 run 是一个单元；
    - **整个 w:ins 是一个原子单元**（修订插入是正文的一部分——这是与
      python-docx `paragraph.runs` 的关键差异：后者看不见 ins 里的 run，
      已改过一次的段落从此再也无法定位）；
    - w:del（已删内容）与无文本单元不进序列。
    """
    p_elem = paragraph._element
    units: list[tuple[str, etree._Element, bool]] = []
    for child in p_elem:
        if child.tag == qn("w:r"):
            text = _run_text(child)
            if text:
                units.append((text, child, False))
        elif child.tag == qn("w:ins"):
            text = "".join(_run_text(r) for r in child.findall(qn("w:r")))
            if text:
                units.append((text, child, True))
    return units


def visible_text(paragraph: Paragraph) -> str:
    """段落的现行文本（直接 run + 修订插入；已删除内容不算）。

    定位选区、给模型读上下文都用这个口径——与编辑器/解析端看到的
    「接受所有修订后」文本一致。
    """
    return "".join(text for text, _, _ in _content_units(paragraph))


def _unit_format_source(elem: etree._Element, is_ins: bool) -> etree._Element:
    """取单元里第一个 run 作为格式参考（ins 单元取其内首个 run）。"""
    if is_ins:
        for r in elem.findall(qn("w:r")):
            return r
    return elem


def _withdraw_unit_text(
    elem: etree._Element,
    is_ins: bool,
    keep_before: str,
    keep_after: str,
) -> tuple[etree._Element | None, etree._Element | None]:
    """撤回单元的覆盖文本，返回 (保留前缀的元素, 残余后缀的新元素)。

    - 直接 run：前缀改写原 run 文本；后缀另起一个同格式 run 插原位之后；
      全覆盖时移除原 run。
    - ins 单元：前缀留在原 ins；后缀**另起一个新 ins**（未接受的插入不能
      降级成普通文本）；全覆盖时整只移除。
    """
    parent = elem.getparent()
    # 原位后继必须在移除前捕获：detach 之后 getnext() 恒为 None
    next_sibling = elem.getnext()
    if not is_ins:
        if keep_before:
            _set_run_text(elem, keep_before)
            kept: etree._Element | None = elem
        else:
            kept = None
            if parent is not None:
                parent.remove(elem)
        tail: etree._Element | None = None
        if keep_after:
            tail = _make_run(keep_after, elem)
            if kept is not None:
                kept.addnext(tail)
            else:
                _insert_at_original_position(next_sibling, tail, parent)
        return kept, tail

    # ins 单元：首个 run 承载前缀，其余 run 收敛掉
    runs = elem.findall(qn("w:r"))
    first = runs[0] if runs else None
    if keep_before and first is not None:
        _set_run_text(first, keep_before)
        for r in runs[1:]:
            elem.remove(r)
        kept = elem
    else:
        kept = None
        if parent is not None:
            parent.remove(elem)
    if keep_after:
        # 新 ins 复制原修订属性（同作者同轮次的延续插入）
        new_ins = OxmlElement("w:ins")
        for attr in (qn("w:author"), qn("w:date")):
            val = elem.get(attr)
            if val:
                new_ins.set(attr, val)
        new_ins.set(qn("w:id"), _next_rev_id())
        new_ins.append(_make_run(keep_after, first if first is not None else elem))
        tail = new_ins
        if kept is not None:
            kept.addnext(tail)
        else:
            _insert_at_original_position(next_sibling, tail, parent)
    else:
        tail = None
    return kept, tail


def _insert_at_original_position(
    next_sibling: etree._Element | None, new_elem: etree._Element, parent: etree._Element | None
) -> None:
    """把 new_elem 放回单元被移除前的原位（有后继插它前面，无后继则追加）。"""
    if next_sibling is not None and next_sibling.getparent() is parent:
        next_sibling.addprevious(new_elem)
    elif parent is not None:
        parent.append(new_elem)


def _find_span(text: str, needle: str) -> tuple[int, int] | None:
    """在 text 里为 needle 找落笔区间 [start, end)，空白完全容忍。

    模板空位（下划线空格）与编辑器复制的选区在空白上天然不一致：下划线
    空位是两个空格、选区只剩一个甚至没有；反过来选区带空格、原文没有也
    有。精确 find 只是快路径，失败后按「去空白等价」匹配，并把区间映射回
    原文本坐标——返回的 [start, end) 始终切在真实字符上，删除痕迹用文档
    实际文本，不吃亏不越界。找不到（真实内容不同）返回 None。
    """
    i = text.find(needle)
    if i >= 0:
        return i, i + len(needle)
    stripped_needle = "".join(needle.split())
    if not stripped_needle:
        return None
    stripped_chars: list[str] = []
    orig_idx: list[int] = []
    for pos, ch in enumerate(text):
        if not ch.isspace():
            stripped_chars.append(ch)
            orig_idx.append(pos)
    j = "".join(stripped_chars).find(stripped_needle)
    if j < 0:
        return None
    start = orig_idx[j]
    end = orig_idx[j + len(stripped_needle) - 1] + 1
    return start, end


# ↓↓ 由 DocxRevisionTool 下沉的模块级纯函数（四层架构静态方法棘轮）
def enable_track_changes(doc: DocumentType) -> None:
    """在文档 settings 中启用修订模式"""
    # 确保 settings part 存在
    settings_part = doc.settings.element
    # 移除已有的 trackChanges
    for existing in settings_part.findall(qn("w:trackChanges")):
        settings_part.remove(existing)
    # 添加 trackChanges 标记
    tc = OxmlElement("w:trackChanges")
    settings_part.append(tc)
