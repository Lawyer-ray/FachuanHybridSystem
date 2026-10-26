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

        # 跨 run 匹配：拼接段落全文查找。模板空位（下划线空格）与编辑器
        # 复制会把连续空格折叠或展开，精确比对必然误判「找不到」——统一走
        # 空白容忍的 _find_span（真实内容不同才算找不到）
        if _find_span(paragraph.text, original) is None:
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
        """原文跨多个 run 的情况：找到覆盖原文的 run 范围，整体替换"""
        runs = paragraph.runs
        if not runs:
            return False

        # 构建 run 文本偏移映射
        offsets: list[tuple[int, int]] = []  # (start, end) for each run
        pos = 0
        for r in runs:
            length = len(r.text)
            offsets.append((pos, pos + length))
            pos += length

        full_text = "".join(r.text for r in runs)
        span = _find_span(full_text, original)
        if span is None:
            return False

        idx, end_idx = span

        # 找到覆盖 [idx, end_idx) 的 run 范围
        first_run = last_run = -1
        for i, (s, e) in enumerate(offsets):
            if s < end_idx and e > idx:
                if first_run < 0:
                    first_run = i
                last_run = i

        if first_run < 0:
            return False

        # 收集第一个 run 的格式作为参考
        ref_elem = runs[first_run]._element

        # 计算前缀和后缀
        prefix = full_text[offsets[first_run][0] : idx]
        suffix = full_text[end_idx : offsets[last_run][1]]

        # 在 paragraph XML 中定位并替换
        p_elem = paragraph._element
        first_elem = runs[first_run]._element

        # 必须在移除循环之前记录插入位置：first_elem 被移除后 `first_elem in p_elem` 恒为
        # False，旧写法会退化成段尾插入，修订块落到段落末尾、残余 run 语序被打乱。
        # （index 处的元素就是 first_elem 的原位，移除后按该下标插入即可回到原位置。）
        insert_pos = list(p_elem).index(first_elem)

        # 移除涉及的 run 元素
        for i in range(first_run, last_run + 1):
            elem = runs[i]._element
            if elem.getparent() is p_elem:
                p_elem.remove(elem)

        # 插入新元素（insert_pos 已在移除前记录）

        # 删除痕迹必须写文档**实际**区间文本：空白容忍匹配下选区与原文的
        # 空白可能不一致，照抄 original 会让 del 内容与被删 run 对不上账
        elements: list[etree._Element] = []
        if prefix:
            elements.append(_make_run(prefix, ref_elem))
        elements.append(_create_del(full_text[idx:end_idx], author, date, ref_elem))
        elements.append(_create_ins(replacement, author, date, ref_elem))
        if suffix:
            elements.append(_make_run(suffix, ref_elem))

        # insert_before 已被移除，用索引插入
        for i, elem in enumerate(elements):
            p_elem.insert(insert_pos + i, elem)

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
