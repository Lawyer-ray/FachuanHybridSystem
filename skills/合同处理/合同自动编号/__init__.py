"""
合同自动编号 Skill

将合同文档中的手动编号转换为 Word 自动编号。

支持两种格式：
1. 一、1.（1）① （中文格式）
2. 1. 1.1 1.1.1 1.1.1.1 1.1.1.1.1 （纯数字格式）

支持两种工作模式：
- 自动模式：正则检测编号结构（适合格式规范的合同）
- AI 辅助模式：输出段落结构供 AI 判断层级，再应用编号（适合复杂格式）
"""

import json
import logging
import re
from pathlib import Path

from docx import Document

from .converter import convert_numbering, verify_numbering
from .detector import detect_chinese_level0, detect_decimal_level0, detect_numbering_structure, is_signature_section
from .formats import NUMBERING_FORMATS, get_format
from .utils import format_numbering_mapping, generate_output_path, validate_input_path

logger = logging.getLogger(__name__)

__version__ = '1.5.0'
__all__ = ['convert_contract_numbering', 'analyze_document', 'apply_numbering_map', 'NUMBERING_FORMATS']

# 最大重试次数
MAX_RETRIES = 3


def _extract_prefix(text: str) -> str:
    """提取段落开头的编号前缀（如"一、""1.""（一）""1.1、"等）"""
    patterns = [
        r'^[（(][一二三四五六七八九十]+[）)]\s*',
        r'^[（(]\d+[）)]\s*',
        r'^[一二三四五六七八九十]+、\s*',
        r'^\d+\.\d+[.、]?\s*',
        r'^\d+[.、]\s*',
        r'^\d+[）)]\s*',
    ]
    for pattern in patterns:
        m = re.match(pattern, text)
        if m:
            return m.group(0)
    return ''


def get_user_format_choice() -> str:
    """询问用户选择编号格式

    Returns:
        格式类型 ('chinese' 或 'decimal')
    """
    logger.info("\n请选择编号格式：")
    logger.info("  1. 一、1.（1）① （中文格式）")
    logger.info("  2. 1. 1.1 1.1.1 1.1.1.1 （纯数字格式）")
    logger.info("")

    while True:
        choice = input("请输入选项 (1 或 2): ").strip()
        if choice == '1':
            return 'chinese'
        elif choice == '2':
            return 'decimal'
        else:
            logger.warning("无效选项，请输入 1 或 2")


def convert_contract_numbering(
    input_path: str | Path,
    output_path: str | Path | None = None,
    format_type: str | None = None,
    verify: bool = True
) -> dict:
    """
    转换合同文档的自动编号

    Args:
        input_path: 输入文档路径
        output_path: 输出文档路径（可选，默认为 {原文件名}_自动编号.docx）
        format_type: 编号格式类型 ('chinese' 或 'decimal')，None 则询问用户
        verify: 是否验证转换结果

    Returns:
        dict: 转换结果信息（含审计报告）
    """
    # 验证输入路径
    try:
        input_path = validate_input_path(input_path)
    except (FileNotFoundError, ValueError) as e:
        return {'success': False, 'error': str(e)}

    # 生成输出路径
    if output_path is None:
        output_path = generate_output_path(input_path)
    else:
        output_path = Path(output_path)

    # 如果未指定格式，询问用户
    if format_type is None:
        format_type = get_user_format_choice()

    # 验证格式类型
    try:
        get_format(format_type)
    except ValueError as e:
        return {'success': False, 'error': str(e)}

    # 预读取原始文档（供审计使用）
    original_doc_for_audit = Document(input_path)

    # 重试循环
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("尝试第 %d 次转换...", attempt)

        # 读取文档（每次重新读取以重新开始）
        doc = Document(input_path)

        # 分析文档结构
        numbered_paras = detect_numbering_structure(doc, format_type)

        # 提取 Level 0 索引
        level0_indices = [idx for idx, level, _, _ in numbered_paras if level == 0]

        # 转换编号
        convert_numbering(doc, numbered_paras, {}, format_type)

        # 验证转换结果
        if verify:
            verification = verify_numbering(
                doc, numbered_paras,
                original_doc=original_doc_for_audit,
                format_type=format_type,
            )

            if verification['all_valid']:
                logger.info("✓ 验证通过！所有 %d 个段落编号正确", verification['total'])

                # 保存文档
                doc.save(output_path)

                return {
                    'success': True,
                    'input_path': str(input_path),
                    'output_path': str(output_path),
                    'format_type': format_type,
                    'format_name': NUMBERING_FORMATS[format_type]['name'],
                    'total_paragraphs': len(numbered_paras),
                    'level0_count': len(level0_indices),
                    'numbered_paras': numbered_paras,
                    'verification': verification,
                    'audit': verification.get('audit'),
                }
            else:
                logger.warning("✗ 验证失败！%d/%d 个段落编号不正确",
                             verification['invalid_count'], verification['total'])

                # 显示失败详情
                for r in verification['results']:
                    if not r['valid']:
                        expected = f"L{r['expected_level']}" if r['expected_level'] is not None else "无编号"
                        actual = f"L{r['actual_level']}" if r['actual_level'] is not None else "无"
                        logger.warning("  [%d] 期望 %s, 实际 %s: %s",
                                     r['para_idx'], expected, actual, r['text'])

                # 显示审计报告（增强信息）
                if verification.get('audit'):
                    audit = verification['audit']
                    if not audit['all_clear']:
                        logger.warning("\n⚠ 审计发现以下问题：")
                        logger.warning(audit['summary'])

                if attempt < MAX_RETRIES:
                    logger.info("正在重试...")
                else:
                    logger.error("已达到最大重试次数 %d，转换失败", MAX_RETRIES)
                    return {
                        'success': False,
                        'error': f'验证失败：{verification["invalid_count"]} 个段落编号不正确',
                        'verification': verification,
                        'audit': verification.get('audit'),
                    }
        else:
            # 不验证，直接保存
            doc.save(output_path)

            return {
                'success': True,
                'input_path': str(input_path),
                'output_path': str(output_path),
                'format_type': format_type,
                'format_name': NUMBERING_FORMATS[format_type]['name'],
                'total_paragraphs': len(numbered_paras),
                'level0_count': len(level0_indices),
                'numbered_paras': numbered_paras,
            }

    # 不应该到这里
    return {'success': False, 'error': '未知错误'}


# ============================================================
# AI 辅助模式
# ============================================================


def analyze_document(input_path: str | Path, format_type: str = 'chinese') -> str:
    """提取文档段落结构，输出 JSON 供 AI 分析层级

    流程：读取文档 → 提取每个段落的索引/文本/编号前缀 → 输出 JSON
    AI 拿到 JSON 后，根据语义理解分配层级（0/1/2/3），生成 numbering_map

    Args:
        input_path: 输入文档路径
        format_type: 编号格式类型（影响 Level 0 的检测方式）

    Returns:
        JSON 字符串，结构为：
        {
            "format_type": "chinese",
            "paragraphs": [
                {"index": 0, "text": "合作协议", "prefix": "", "is_level0": false, "is_signature": false},
                {"index": 10, "text": "一、合作期限", "prefix": "一、", "is_level0": true, "is_signature": false},
                {"index": 13, "text": "（一）甲方权责", "prefix": "（一）", "is_level0": false, "is_signature": false},
                ...
            ]
        }
    """
    input_path = validate_input_path(input_path)
    get_format(format_type)  # 验证格式
    doc = Document(input_path)

    paragraphs = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        prefix = _extract_prefix(text)

        # 检测是否是 Level 0 标题
        is_level0 = False
        if format_type == 'chinese':
            matched, _ = detect_chinese_level0(text)
        else:
            matched, _ = detect_decimal_level0(text)
        if matched:
            is_level0 = True

        # 检测是否是签名区
        is_sig = is_signature_section(text)

        paragraphs.append({
            'index': i,
            'text': text[:200],  # 截断长文本，AI 不需要看全文
            'prefix': prefix,
            'is_level0': is_level0,
            'is_signature': is_sig,
        })

    result = {
        'format_type': format_type,
        'total_paragraphs': len(doc.paragraphs),
        'paragraphs': paragraphs,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def apply_numbering_map(
    input_path: str | Path,
    numbering_map: str | list[dict],
    output_path: str | Path | None = None,
    format_type: str = 'chinese',
    verify: bool = True,
) -> dict:
    """根据 AI 提供的层级映射应用自动编号

    流程：读取 AI 生成的 numbering_map → 构建 numbered_paras → 应用编号 → 验证 → 保存

    Args:
        input_path: 输入文档路径
        numbering_map: AI 生成的层级映射，可以是 JSON 字符串或已解析的列表
                       格式: [{"index": 10, "level": 0}, {"index": 13, "level": 1}, ...]
                       level: 0=一级标题, 1=二级, 2=三级, 3=四级
                       不在列表中的段落不会被编号
        output_path: 输出文档路径
        format_type: 编号格式类型
        verify: 是否验证转换结果

    Returns:
        dict: 转换结果信息
    """
    # 验证输入路径
    try:
        input_path = validate_input_path(input_path)
    except (FileNotFoundError, ValueError) as e:
        return {'success': False, 'error': str(e)}

    # 生成输出路径
    if output_path is None:
        output_path = generate_output_path(input_path)
    else:
        output_path = Path(output_path)

    # 验证格式
    try:
        get_format(format_type)
    except ValueError as e:
        return {'success': False, 'error': str(e)}

    # 解析 numbering_map
    if isinstance(numbering_map, str):
        mapping_data = json.loads(numbering_map)
    else:
        mapping_data = numbering_map

    # 读取文档
    original_doc_for_audit = Document(input_path)
    doc = Document(input_path)

    # 构建 numbered_paras: list of (para_idx, level, matched_text, original_text)
    numbered_paras = []
    for item in mapping_data:
        idx = item['index']
        level = item['level']
        para = doc.paragraphs[idx]
        text = para.text.strip()
        prefix = _extract_prefix(text)
        numbered_paras.append((idx, level, prefix, text))

    # 提取 Level 0 索引
    level0_indices = [idx for idx, level, _, _ in numbered_paras if level == 0]

    if not level0_indices:
        return {'success': False, 'error': '层级映射中没有 Level 0 段落，无法应用编号'}

    # 应用编号
    convert_numbering(doc, numbered_paras, {}, format_type)

    # 验证
    if verify:
        verification = verify_numbering(
            doc, numbered_paras,
            original_doc=original_doc_for_audit,
            format_type=format_type,
        )

        if not verification['all_valid']:
            logger.warning("验证发现问题：\n%s", verification.get('audit', {}).get('summary', ''))

    # 保存
    doc.save(output_path)

    return {
        'success': True,
        'input_path': str(input_path),
        'output_path': str(output_path),
        'format_type': format_type,
        'format_name': NUMBERING_FORMATS[format_type]['name'],
        'total_paragraphs': len(numbered_paras),
        'level0_count': len(level0_indices),
        'numbered_paras': numbered_paras,
        'verification': verification if verify else None,
    }
