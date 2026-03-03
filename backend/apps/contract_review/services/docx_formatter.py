from __future__ import annotations

import logging

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt

logger = logging.getLogger(__name__)

# 字号映射（中文字号 → 磅值）
_FONT_SIZE = {
    "小二": Pt(18),
    "小四": Pt(12),
}

_HEADING_STYLES = {
    "Heading 1",
    "Heading 2",
    "Heading 3",
    "Heading1",
    "Heading2",
    "Heading3",
    "标题 1",
    "标题 2",
    "标题 3",
    "Title",
}


class DocxFormatter:
    """合同文档格式标准化"""

    def format_document(self, doc: Document) -> None:
        """标题黑体小二，正文宋体小四，全文统一段落间距和行距"""
        self._clean_style_indent_chars(doc)
        title_elem = self._find_title_element(doc)

        for para in doc.paragraphs:
            is_title = para._element is title_elem
            self._set_paragraph_spacing(para, is_title=is_title)
            if is_title:
                self._set_font(para, "黑体", _FONT_SIZE["小二"])
            else:
                self._set_font(para, "宋体", _FONT_SIZE["小四"])

        logger.info("文档格式标准化完成")

    @staticmethod
    def _clean_style_indent_chars(doc: Document) -> None:
        """清除所有样式中的字符单位缩进属性，防止覆盖绝对值设置"""
        chars_attrs = [qn(a) for a in ("w:firstLineChars", "w:leftChars", "w:rightChars", "w:hangingChars")]
        for style in doc.styles:
            s_pPr = style.element.find(qn("w:pPr"))
            if s_pPr is None:
                continue
            ind = s_pPr.find(qn("w:ind"))
            if ind is None:
                continue
            for key in chars_attrs:
                if ind.get(key) is not None:
                    del ind.attrib[key]

    @staticmethod
    def _find_title_element(doc: Document) -> object | None:
        """找到合同标题段落的 XML 元素"""
        for p in doc.paragraphs:
            style_name = p.style.name if p.style else ""
            if style_name in _HEADING_STYLES:
                return p._element
            if p.text.strip():
                return p._element
        return None

    @staticmethod
    def _set_paragraph_spacing(para: object, *, is_title: bool = False) -> None:
        """段前段后0、行距1.5倍；正文首行缩进2字符(24pt)，标题不缩进"""
        fmt = para.paragraph_format  # type: ignore[union-attr]
        fmt.left_indent = Pt(0)
        fmt.right_indent = Pt(0)
        fmt.first_line_indent = Pt(0) if is_title else Pt(24)
        fmt.space_before = Pt(0)
        fmt.space_after = Pt(0)
        fmt.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        fmt.line_spacing = 1.5

        # 清除 Chars 属性（优先级高于绝对值，会覆盖上面的设置）
        p_pr = para._element.find(qn("w:pPr"))  # type: ignore[union-attr]
        ind = p_pr.find(qn("w:ind")) if p_pr is not None else None
        if ind is not None:
            for attr in ("w:firstLineChars", "w:leftChars", "w:rightChars", "w:hangingChars"):
                key = qn(attr)
                if ind.get(key) is not None:
                    del ind.attrib[key]

    @staticmethod
    def _set_font(para: object, font_name: str, size: Pt) -> None:
        """设置段落所有 run 的字体和字号"""
        for run in para.runs:  # type: ignore[union-attr]
            run.font.name = font_name
            run.font.size = size
            # 设置东亚字体
            r_elem = run._element
            rpr = r_elem.find(qn("w:rPr"))
            if rpr is None:
                from docx.oxml import OxmlElement

                rpr = OxmlElement("w:rPr")
                r_elem.insert(0, rpr)
            rfonts = rpr.find(qn("w:rFonts"))
            if rfonts is None:
                from docx.oxml import OxmlElement

                rfonts = OxmlElement("w:rFonts")
                rpr.insert(0, rfonts)
            rfonts.set(qn("w:eastAsia"), font_name)
