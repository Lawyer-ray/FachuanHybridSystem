from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone

_CST = timezone(timedelta(hours=8))

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

logger = logging.getLogger(__name__)

AUTHOR = "法穿AI"

_rev_id_counter = 1


def _next_rev_id() -> str:
    global _rev_id_counter
    _rev_id_counter += 1
    return str(_rev_id_counter)


class DocxRevisionTool:
    """通过 lxml 操作 OOXML 实现 Track Changes（修订模式）"""

    @staticmethod
    def enable_track_changes(doc: Document) -> None:
        """在文档 settings 中启用修订模式"""
        # 确保 settings part 存在
        settings_part = doc.settings.element
        # 移除已有的 trackChanges
        for existing in settings_part.findall(qn("w:trackChanges")):
            settings_part.remove(existing)
        # 添加 trackChanges 标记
        tc = OxmlElement("w:trackChanges")
        settings_part.append(tc)

    def apply_revision(
        self,
        paragraph: Paragraph,
        original: str,
        replacement: str,
        author: str | None = None,
    ) -> bool:
        """在段落中定位原文，插入 <w:del> 和 <w:ins> 修订标记。
        先尝试单 run 匹配，失败则尝试跨 run 匹配。
        """
        author = author or AUTHOR
        date = datetime.now(tz=_CST).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 尝试单 run 精确匹配
        for run in paragraph.runs:
            if original in run.text:
                self._apply_single_run(paragraph, run, original, replacement, author, date)
                return True

        # 跨 run 匹配：拼接段落全文查找
        full_text = paragraph.text
        if original not in full_text:
            # 尝试去空格匹配
            normalized = original.replace(" ", "").replace("\u3000", "")
            normalized_full = full_text.replace(" ", "").replace("\u3000", "")
            if normalized not in normalized_full:
                logger.warning("未在段落中找到原文: %s", original[:60])
                return False

        # 跨 run 匹配
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
        idx = full_text.find(original)
        if idx < 0:
            return False

        end_idx = idx + len(original)

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
        insert_before = first_elem

        # 移除涉及的 run 元素
        for i in range(first_run, last_run + 1):
            elem = runs[i]._element
            if elem.getparent() is p_elem:
                p_elem.remove(elem)

        # 插入新元素
        insert_pos = list(p_elem).index(insert_before) if insert_before in p_elem else len(list(p_elem))

        elements: list[etree._Element] = []
        if prefix:
            elements.append(_make_run(prefix, ref_elem))
        elements.append(_create_del(original, author, date, ref_elem))
        elements.append(_create_ins(replacement, author, date, ref_elem))
        if suffix:
            elements.append(_make_run(suffix, ref_elem))

        # insert_before 已被移除，用索引插入
        for i, elem in enumerate(elements):
            p_elem.insert(insert_pos + i, elem)

        return True


def _create_del(text: str, author: str, date: str, source_run: etree._Element) -> etree._Element:
    """创建 <w:del> 删除标记"""
    del_elem = OxmlElement("w:del")
    del_elem.set(qn("w:id"), _next_rev_id())
    del_elem.set(qn("w:author"), author)
    del_elem.set(qn("w:date"), date)
    del_elem.append(_make_run(text, source_run, tag="w:delText"))
    return del_elem


def _create_ins(text: str, author: str, date: str, source_run: etree._Element) -> etree._Element:
    """创建 <w:ins> 插入标记"""
    ins_elem = OxmlElement("w:ins")
    ins_elem.set(qn("w:id"), _next_rev_id())
    ins_elem.set(qn("w:author"), author)
    ins_elem.set(qn("w:date"), date)
    ins_elem.append(_make_run(text, source_run))
    return ins_elem


def _make_run(text: str, source_run: etree._Element, tag: str = "w:t") -> etree._Element:
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
