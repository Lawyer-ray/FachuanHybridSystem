"""
编号转换模块

将检测到的手动编号转换为 Word 自动编号。
"""

import logging

from docx import Document
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from .formats import get_format, get_max_level

logger = logging.getLogger(__name__)


def create_numbering_part(doc: Document) -> tuple[Part, etree._Element]:
    """创建或获取 numbering part

    Args:
        doc: Word 文档

    Returns:
        (numbering_part, numbering_elem) 元组
    """
    try:
        return doc.part.numbering_part, doc.part.numbering_part.element
    except (AttributeError, Exception):
        package = doc.part.package
        partnames = {part.partname for part in package.iter_parts()}
        partname = PackURI('/word/numbering.xml')
        if partname in partnames:
            partname = package.next_partname('/word/numbering%d.xml')

        numbering_xml = '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        numbering_part = Part(
            partname,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml',
            numbering_xml.encode('utf-8'),
            package
        )
        doc.part.relate_to(numbering_part, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering')
        numbering_elem = etree.fromstring(numbering_xml.encode('utf-8'))
        return numbering_part, numbering_elem


def create_abstract_numbering(numbering_elem: etree._Element, abstract_id: int, format_type: str) -> None:
    """创建 abstractNum 定义

    Args:
        numbering_elem: numbering XML 元素
        abstract_id: abstractNum ID
        format_type: 格式类型
    """
    abstract_num = OxmlElement('w:abstractNum')
    abstract_num.set(qn('w:abstractNumId'), str(abstract_id))

    multi_level = OxmlElement('w:multiLevelType')
    multi_level.set(qn('w:val'), 'multilevel')
    abstract_num.append(multi_level)

    # 获取格式定义
    format_def = get_format(format_type)
    levels = format_def['levels']

    for lvl_def in levels:
        lvl = OxmlElement('w:lvl')
        lvl.set(qn('w:ilvl'), lvl_def['ilvl'])

        start = OxmlElement('w:start')
        start.set(qn('w:val'), lvl_def['start'])
        lvl.append(start)

        num_fmt = OxmlElement('w:numFmt')
        num_fmt.set(qn('w:val'), lvl_def['numFmt'])
        lvl.append(num_fmt)

        suff = OxmlElement('w:suff')
        suff.set(qn('w:val'), 'nothing')
        lvl.append(suff)

        lvl_text = OxmlElement('w:lvlText')
        lvl_text.set(qn('w:val'), lvl_def['lvlText'])
        lvl.append(lvl_text)

        lvl_jc = OxmlElement('w:lvlJc')
        lvl_jc.set(qn('w:val'), 'left')
        lvl.append(lvl_jc)

        p_pr = OxmlElement('w:pPr')
        ind = OxmlElement('w:ind')
        ind.set(qn('w:left'), '0')
        ind.set(qn('w:leftChars'), '0')
        ind.set(qn('w:hanging'), '0')
        ind.set(qn('w:hangingChars'), '0')
        p_pr.append(ind)
        lvl.append(p_pr)

        abstract_num.append(lvl)

    numbering_elem.append(abstract_num)


def create_num_instances(
    numbering_elem: etree._Element,
    abstract_id: int,
    level0_indices: list[int],
    format_type: str
) -> dict[int, int]:
    """为每个 Level 0 创建独立的 num 实例

    Args:
        numbering_elem: numbering XML 元素
        abstract_id: abstractNum ID
        level0_indices: Level 0 段落索引列表
        format_type: 格式类型

    Returns:
        {para_idx: num_id} 映射
    """
    num_id_map = {}

    # 找出已存在的最大 numId，避免冲突
    existing_num_ids = [
        int(num.get(qn('w:numId'), 0))
        for num in numbering_elem.findall(qn('w:num'))
    ]
    next_num_id = max(existing_num_ids, default=0) + 1

    # 获取格式定义中的最大层级
    max_level = get_max_level(format_type)

    for para_idx in level0_indices:
        num_elem = OxmlElement('w:num')
        num_elem.set(qn('w:numId'), str(next_num_id))
        abstract_ref = OxmlElement('w:abstractNumId')
        abstract_ref.set(qn('w:val'), str(abstract_id))
        num_elem.append(abstract_ref)

        # 重置 Level 1 到 max_level 的计数器
        for reset_level in range(1, max_level + 1):
            lvl_override = OxmlElement('w:lvlOverride')
            lvl_override.set(qn('w:ilvl'), str(reset_level))
            start_override = OxmlElement('w:startOverride')
            start_override.set(qn('w:val'), '1')
            lvl_override.append(start_override)
            num_elem.append(lvl_override)

        numbering_elem.append(num_elem)
        num_id_map[para_idx] = next_num_id
        next_num_id += 1

    return num_id_map


def apply_numbering_to_paragraph(para, level: int, num_id: int, text: str) -> None:
    """应用自动编号到单个段落

    Args:
        para: 段落元素
        level: 编号层级
        num_id: 编号 ID
        text: 段落文本（已去除手动编号）
    """
    # 清除并重设文本
    for run in para.runs:
        run.text = ''
    if para.runs:
        para.runs[0].text = text

    # 应用自动编号
    p_pr = para._element.find(qn('w:pPr'))
    if p_pr is None:
        p_pr = OxmlElement('w:pPr')
        para._element.insert(0, p_pr)

    # 移除旧的 numPr
    old_num_pr = p_pr.find(qn('w:numPr'))
    if old_num_pr is not None:
        p_pr.remove(old_num_pr)

    # 移除旧的缩进
    old_ind = p_pr.find(qn('w:ind'))
    if old_ind is not None:
        p_pr.remove(old_ind)

    # 创建新的 numPr
    num_pr = OxmlElement('w:numPr')

    ilvl = OxmlElement('w:ilvl')
    ilvl.set(qn('w:val'), str(level))
    num_pr.append(ilvl)

    num_id_elem = OxmlElement('w:numId')
    num_id_elem.set(qn('w:val'), str(num_id))
    num_pr.append(num_id_elem)

    p_pr.append(num_pr)

    # 设置缩进为 0
    ind = OxmlElement('w:ind')
    ind.set(qn('w:left'), '0')
    ind.set(qn('w:leftChars'), '0')
    ind.set(qn('w:hanging'), '0')
    ind.set(qn('w:hangingChars'), '0')
    p_pr.append(ind)


def convert_numbering(
    doc: Document,
    numbered_paras: list[tuple[int, int, str, str]],
    num_id_map: dict[int, int],
    format_type: str
) -> None:
    """转换文档中的编号

    Args:
        doc: Word 文档
        numbered_paras: 编号段落列表
        num_id_map: {para_idx: num_id} 映射（如果为空则自动创建）
        format_type: 格式类型
    """
    # 创建 numbering part
    numbering_part, numbering_elem = create_numbering_part(doc)

    # 创建 abstractNum
    create_abstract_numbering(numbering_elem, abstract_id=0, format_type=format_type)

    # 创建 num 实例
    level0_indices = [idx for idx, level, _, _ in numbered_paras if level == 0]
    num_id_map = create_num_instances(numbering_elem, abstract_id=0, level0_indices=level0_indices, format_type=format_type)

    # 更新 numbering part
    if hasattr(numbering_part, '_blob'):
        numbering_part._blob = etree.tostring(numbering_elem, xml_declaration=True, encoding='UTF-8', standalone=True)

    # 创建已编号段落的索引集合
    numbered_indices = {idx for idx, _, _, _ in numbered_paras}

    # 首先清除所有非签名段落的旧编号
    from .detector import is_signature_section
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        # 跳过已编号段落（后面会处理）
        if i in numbered_indices:
            continue

        # 跳过签名部分
        if is_signature_section(text):
            continue

        # 清除其他段落的编号
        p_pr = para._element.find(qn('w:pPr'))
        if p_pr is not None:
            old_num_pr = p_pr.find(qn('w:numPr'))
            if old_num_pr is not None:
                p_pr.remove(old_num_pr)

    # 应用自动编号
    current_num_id = None

    for para_idx, level, matched, original_text in numbered_paras:
        para = doc.paragraphs[para_idx]

        # 去除手动编号
        if matched:
            new_text = original_text[len(matched):].lstrip()
        else:
            new_text = original_text

        # 确定 numId
        if level == 0:
            current_num_id = num_id_map.get(para_idx)

        # 应用自动编号
        num_id_to_use = current_num_id if level >= 1 else num_id_map.get(para_idx)
        apply_numbering_to_paragraph(para, level, num_id_to_use, new_text)


def verify_numbering(doc: Document, numbered_paras: list[tuple[int, int, str, str]]) -> dict:
    """验证自动编号是否正确应用

    Args:
        doc: Word 文档
        numbered_paras: 编号段落列表

    Returns:
        验证结果字典
    """
    from .detector import is_signature_section

    results = []
    all_valid = True

    # 创建已编号段落的索引集合
    numbered_indices = {idx for idx, _, _, _ in numbered_paras}

    # 验证所有段落
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        p_pr = para._element.find(qn('w:pPr'))
        has_num = False
        actual_level = None
        num_id = None

        if p_pr is not None:
            num_pr = p_pr.find(qn('w:numPr'))
            if num_pr is not None:
                has_num = True
                ilvl_elem = num_pr.find(qn('w:ilvl'))
                num_id_elem = num_pr.find(qn('w:numId'))
                if ilvl_elem is not None:
                    actual_level = int(ilvl_elem.get(qn('w:val'), -1))
                if num_id_elem is not None:
                    num_id = num_id_elem.get(qn('w:val'))

        # 检查是否是签名部分
        is_signature = is_signature_section(text)

        # 判断是否有效
        if i in numbered_indices:
            # 应该编号的段落
            expected_level = next(level for idx, level, _, _ in numbered_paras if idx == i)
            is_valid = has_num and actual_level == expected_level
        elif is_signature:
            # 签名部分不应该编号
            is_valid = not has_num
        else:
            # 其他段落不检查
            is_valid = True

        results.append({
            'para_idx': i,
            'expected_level': expected_level if i in numbered_indices else None,
            'actual_level': actual_level,
            'has_num': has_num,
            'num_id': num_id,
            'is_signature': is_signature,
            'text': text[:50],
            'valid': is_valid,
        })

        if not is_valid:
            all_valid = False

    return {
        'all_valid': all_valid,
        'total': len(results),
        'valid_count': sum(1 for r in results if r['valid']),
        'invalid_count': sum(1 for r in results if not r['valid']),
        'results': [r for r in results if not r['valid']],  # 只返回失败的
    }
