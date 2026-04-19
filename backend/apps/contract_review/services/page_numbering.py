from __future__ import annotations

import logging

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

logger = logging.getLogger(__name__)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class PageNumbering:
    """页码标准化：删除旧页码，设置标准居中阿拉伯数字页码"""

    def standardize(self, doc: DocumentType) -> None:
        """删除旧页码域代码，在页脚设置新页码"""
        self._remove_existing_page_numbers(doc)
        self._add_page_number_footer(doc)
        logger.info("页码标准化完成")

    def _remove_existing_page_numbers(self, doc: DocumentType) -> None:
        """检测并删除所有已有页码域代码"""
        body = doc.element.body
        # 查找所有 sectPr 中的页脚引用对应的页码域
        for sect_pr in body.iter(qn("w:sectPr")):
            for footer_ref in sect_pr.findall(qn("w:footerReference")):
                r_id = footer_ref.get(qn("r:id"))
                if not r_id:
                    continue
                part = doc.part.related_parts.get(r_id)
                if part is None:
                    continue
                # 删除包含 PAGE 的 instrText 所在的段落
                for instr in list(part.element.iter(qn("w:instrText"))):
                    if instr.text and "PAGE" in instr.text.upper():
                        # 删除整个段落
                        p = instr.getparent()
                        while p is not None and p.tag != qn("w:p"):
                            p = p.getparent()
                        if p is not None and p.getparent() is not None:
                            p.getparent().remove(p)

    def _add_page_number_footer(self, doc: DocumentType) -> None:
        """通过 OxmlElement 构造域代码设置居中页码"""
        section = doc.sections[-1]
        footer = section.footer
        footer.is_linked_to_previous = False

        # 清空现有内容
        for child in list(footer._element):
            footer._element.remove(child)

        # 创建居中段落
        p = OxmlElement("w:p")
        p_pr = OxmlElement("w:pPr")
        jc = OxmlElement("w:jc")
        jc.set(qn("w:val"), "center")
        p_pr.append(jc)
        p.append(p_pr)

        r = OxmlElement("w:r")

        # fldChar begin
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        r.append(fld_begin)
        p.append(r)

        # instrText
        r2 = OxmlElement("w:r")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = " PAGE "
        r2.append(instr)
        p.append(r2)

        # fldChar separate
        r3 = OxmlElement("w:r")
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        r3.append(fld_sep)
        p.append(r3)

        # 页码占位文本
        r4 = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = "1"
        r4.append(t)
        p.append(r4)

        # fldChar end
        r5 = OxmlElement("w:r")
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        r5.append(fld_end)
        p.append(r5)

        footer._element.append(p)
