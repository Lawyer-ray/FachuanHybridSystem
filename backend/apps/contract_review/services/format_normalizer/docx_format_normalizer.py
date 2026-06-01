"""合同格式规范化工具 - 精确匹配修订版格式

通过分析修订版文档的精确格式，逐段落匹配并应用格式。
"""

import logging
import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm

logger = logging.getLogger(__name__)

# 页边距（EMU 单位）
MARGIN_TOP = Cm(2.54)
MARGIN_BOTTOM = Cm(2.54)
MARGIN_LEFT = Cm(3.17)
MARGIN_RIGHT = Cm(3.17)

# 字号（半磅为单位）
FONT_SIZE_BODY = 24        # 12 磅
FONT_SIZE_TITLE = 52       # 26 磅

# 行距（twips）
LINE_SPACING = 360         # 1.5 倍行距

# 字体
FONT_CHINESE = "宋体"
FONT_ENGLISH = "Times New Roman"


class DocxFormatNormalizer:
    """合同格式规范化器 - 精确匹配修订版"""

    def __init__(self, input_path: str | Path, output_path: str | Path | None = None):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path) if output_path else self.input_path.parent / f"{self.input_path.stem}_规范化{self.input_path.suffix}"
        self.doc: Document | None = None

    def normalize(self) -> Path:
        """执行格式规范化，返回输出文件路径"""
        logger.info("开始规范化: %s", self.input_path)
        self.doc = Document(str(self.input_path))

        # 1. 设置页边距
        self._normalize_margins()

        # 2. 定义编号样式
        self._setup_numbering()

        # 3. 规范化段落格式（精确匹配）
        self._normalize_paragraphs()

        # 4. 保存
        self.doc.save(str(self.output_path))
        logger.info("规范化完成: %s", self.output_path)
        return self.output_path

    def _normalize_margins(self) -> None:
        """统一页边距为 A4 标准"""
        for section in self.doc.sections:
            section.top_margin = MARGIN_TOP
            section.bottom_margin = MARGIN_BOTTOM
            section.left_margin = MARGIN_LEFT
            section.right_margin = MARGIN_RIGHT
        logger.debug("页边距已标准化")

    def _setup_numbering(self) -> None:
        """设置自动编号样式（匹配修订版）"""
        try:
            numbering_part = self.doc.part.numbering_part
            numbering_elm = numbering_part._element
        except (KeyError, NotImplementedError):
            numbering_elm = self._create_numbering_part()

        # 创建 abstractNum（匹配修订版格式）
        abstractNum = OxmlElement('w:abstractNum')
        abstractNum.set(qn('w:abstractNumId'), '0')

        # 一级：一、二、三...
        lvl0 = self._create_level('0', 'chineseCounting', '%1、', '400')
        abstractNum.append(lvl0)

        # 二级：1. 2. 3.
        lvl1 = self._create_level('1', 'decimal', '%2．', '400')
        abstractNum.append(lvl1)

        # 三级：（1）（2）（3）
        lvl2 = self._create_level('2', 'decimal', '（%3）', '402')
        abstractNum.append(lvl2)

        # 插入到 numbering 元素开头
        numbering_elm.insert(0, abstractNum)

        # 创建 num 实例（numId=1，引用 abstractNumId=0）
        num = OxmlElement('w:num')
        num.set(qn('w:numId'), '1')
        abstractNumRef = OxmlElement('w:abstractNumId')
        abstractNumRef.set(qn('w:val'), '0')
        num.append(abstractNumRef)
        numbering_elm.append(num)

        # 如果是新创建的 part，需要更新其内容
        if hasattr(self, '_numbering_part'):
            from lxml import etree
            self._numbering_part._blob = etree.tostring(numbering_elm, xml_declaration=True, encoding='UTF-8', standalone=True)

        logger.debug("编号样式已创建")

    def _create_numbering_part(self) -> Any:
        """手动创建 numbering part"""
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.opc.part import Part
        from docx.opc.packuri import PackURI
        from lxml import etree

        nsmap = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        numbering_elm = etree.SubElement(etree.Element('root'), qn('w:numbering'), nsmap=nsmap)
        numbering_xml = etree.tostring(numbering_elm, xml_declaration=True, encoding='UTF-8', standalone=True)

        part_name = PackURI('/word/numbering.xml')
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'
        numbering_part = Part(part_name, content_type, numbering_xml, self.doc.part.package)
        self.doc.part.relate_to(numbering_part, RT.NUMBERING)
        self._numbering_part = numbering_part

        return numbering_elm

    def _create_level(self, ilvl: str, num_fmt: str, level_text: str, first_line: str) -> OxmlElement:
        """创建编号级别定义"""
        lvl = OxmlElement('w:lvl')
        lvl.set(qn('w:ilvl'), ilvl)
        lvl.set(qn('w:tentative'), '0')

        start = OxmlElement('w:start')
        start.set(qn('w:val'), '1')
        lvl.append(start)

        numFmt = OxmlElement('w:numFmt')
        numFmt.set(qn('w:val'), num_fmt)
        lvl.append(numFmt)

        suff = OxmlElement('w:suff')
        suff.set(qn('w:val'), 'nothing')
        lvl.append(suff)

        lvlText = OxmlElement('w:lvlText')
        lvlText.set(qn('w:val'), level_text)
        lvl.append(lvlText)

        lvlJc = OxmlElement('w:lvlJc')
        lvlJc.set(qn('w:val'), 'left')
        lvl.append(lvlJc)

        pPr = OxmlElement('w:pPr')
        ind = OxmlElement('w:ind')
        ind.set(qn('w:left'), '0')
        ind.set(qn('w:firstLine'), first_line)
        pPr.append(ind)
        lvl.append(pPr)

        rPr = OxmlElement('w:rPr')
        rFonts = OxmlElement('w:rFonts')
        rFonts.set(qn('w:hint'), 'eastAsia')
        rPr.append(rFonts)
        lvl.append(rPr)

        return lvl

    def _normalize_paragraphs(self) -> None:
        """规范化所有段落格式（精确匹配修订版）"""
        for i, para in enumerate(self.doc.paragraphs):
            self._normalize_single_paragraph(para, i)

        logger.debug("段落格式已规范化")

    def _normalize_single_paragraph(self, para: Any, index: int) -> None:
        """规范化单个段落"""
        text = para.text.strip()
        pPr = para._element.get_or_add_pPr()

        # 清除旧的格式
        self._clear_old_format(pPr)

        # 基础格式：行距 360，左缩进 0
        self._set_spacing(pPr)
        self._set_indent(pPr, left='0')

        # 根据内容判断格式
        if not text:
            # 空行：清除 run 属性，不设置对齐
            self._clear_run_properties(para)
            return

        # 标题（合同标题）
        if self._is_contract_title(text):
            self._set_alignment(pPr, 'center')
            self._set_run_font(para, FONT_SIZE_TITLE, bold=True)
            return

        # 甲方/乙方行
        if self._is_party_header(text):
            self._set_alignment(pPr, 'both')
            self._set_run_font(para, FONT_SIZE_BODY)
            return

        # 乙方详细信息（法定代表人、地址、信用代码）- 需要加粗
        if self._is_party_b_detail(text):
            self._set_run_font(para, FONT_SIZE_BODY, bold=True)
            return

        # 甲方详细信息（法定代表人、地址、信用代码）
        if self._is_party_a_detail(text):
            self._set_alignment(pPr, 'left')
            self._set_run_font(para, FONT_SIZE_BODY)
            return

        # 条标题（第一条、第二条...）
        if self._is_article_title(text):
            self._set_numbering(pPr, num_id='1', ilvl='1')
            self._set_run_font(para, FONT_SIZE_BODY)
            return

        # 正文：左对齐
        self._set_alignment(pPr, 'left')
        self._set_run_font(para, FONT_SIZE_BODY)

    def _is_contract_title(self, text: str) -> bool:
        """判断是否为合同标题"""
        title_keywords = ['合同', '协议', '契约', '合约']
        return any(kw in text for kw in title_keywords) and len(text) < 30

    def _is_party_header(self, text: str) -> bool:
        """判断是否为甲方/乙方行"""
        return bool(re.match(r'^[甲乙丙丁]方[：:]', text))

    def _is_party_a_detail(self, text: str) -> bool:
        """判断是否为甲方详细信息"""
        # 甲方的法定代表人、地址、信用代码
        if not self._is_detail_pattern(text):
            return False
        # 简化处理：所有详细信息都当作甲方
        return True

    def _is_party_b_detail(self, text: str) -> bool:
        """判断是否为乙方详细信息（需要加粗）"""
        # 乙方的法定代表人、地址、信用代码
        if not self._is_detail_pattern(text):
            return False
        # 简化处理：假设第二个出现的详细信息是乙方
        # 这需要更复杂的逻辑来判断，暂时返回 False
        return False

    def _is_detail_pattern(self, text: str) -> bool:
        """判断是否为详细信息模式"""
        detail_patterns = [
            r'^法定代表人[：:]',
            r'^地址[：:]',
            r'^统一社会信用代码[：:]',
            r'^联系人[/／]电话',
            r'^电话[：:]',
            r'^法人[：:]',
        ]
        return any(re.match(p, text) for p in detail_patterns)

    def _is_article_title(self, text: str) -> bool:
        """判断是否为条标题（第X条）"""
        return bool(re.match(r'^第[一二三四五六七八九十百]+条', text))

    def _clear_old_format(self, pPr: Any) -> None:
        """清除旧的格式定义"""
        for tag in ['w:spacing', 'w:ind', 'w:jc', 'w:numPr']:
            old = pPr.find(qn(tag))
            if old is not None:
                pPr.remove(old)

    def _clear_run_properties(self, para: Any) -> None:
        """清除段落中所有 run 的属性"""
        for run in para.runs:
            rPr = run._element.find(qn('w:rPr'))
            if rPr is not None:
                run._element.remove(rPr)

    def _set_alignment(self, pPr: Any, align: str) -> None:
        """设置对齐方式"""
        jc = OxmlElement('w:jc')
        jc.set(qn('w:val'), align)
        pPr.append(jc)

    def _set_spacing(self, pPr: Any) -> None:
        """设置行距"""
        spacing = OxmlElement('w:spacing')
        spacing.set(qn('w:line'), str(LINE_SPACING))
        spacing.set(qn('w:lineRule'), 'auto')
        spacing.set(qn('w:before'), '0')
        spacing.set(qn('w:after'), '0')
        pPr.append(spacing)

    def _set_indent(self, pPr: Any, left: str = '0') -> None:
        """设置缩进"""
        ind = OxmlElement('w:ind')
        ind.set(qn('w:left'), left)
        pPr.append(ind)

    def _set_numbering(self, pPr: Any, num_id: str, ilvl: str) -> None:
        """设置编号"""
        numPr = OxmlElement('w:numPr')
        ilvl_el = OxmlElement('w:ilvl')
        ilvl_el.set(qn('w:val'), ilvl)
        numPr.append(ilvl_el)

        numId = OxmlElement('w:numId')
        numId.set(qn('w:val'), num_id)
        numPr.append(numId)

        pPr.append(numPr)

    def _set_run_font(self, para: Any, size: int, bold: bool = False) -> None:
        """设置 run 的字体和字号"""
        for run in para.runs:
            rPr = run._element.get_or_add_rPr()

            # 清除旧字体设置
            old_rFonts = rPr.find(qn('w:rFonts'))
            if old_rFonts is not None:
                rPr.remove(old_rFonts)

            # 设置新字体
            rFonts = OxmlElement('w:rFonts')
            rFonts.set(qn('w:ascii'), FONT_ENGLISH)
            rFonts.set(qn('w:hAnsi'), FONT_ENGLISH)
            rFonts.set(qn('w:eastAsia'), FONT_CHINESE)
            rFonts.set(qn('w:cs'), FONT_ENGLISH)
            rPr.insert(0, rFonts)

            # 清除旧字号
            for tag in ['w:sz', 'w:szCs']:
                old = rPr.find(qn(tag))
                if old is not None:
                    rPr.remove(old)

            # 设置字号
            sz = OxmlElement('w:sz')
            sz.set(qn('w:val'), str(size))
            rPr.append(sz)

            szCs = OxmlElement('w:szCs')
            szCs.set(qn('w:val'), str(size))
            rPr.append(szCs)

            # 清除旧加粗
            old_b = rPr.find(qn('w:b'))
            if old_b is not None:
                rPr.remove(old_b)

            # 设置加粗
            if bold:
                b = OxmlElement('w:b')
                rPr.append(b)
