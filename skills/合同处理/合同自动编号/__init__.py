"""
合同自动编号 Skill

将合同文档中的手动编号转换为 Word 自动编号。

支持两种格式：
1. 一、1.（1）① （中文格式）
2. 1. 1.1 1.1.1 1.1.1.1 1.1.1.1.1 （纯数字格式）
"""

import logging
from pathlib import Path

from docx import Document

from .converter import convert_numbering, verify_numbering
from .detector import detect_numbering_structure
from .formats import NUMBERING_FORMATS, get_format
from .utils import format_numbering_mapping, generate_output_path, validate_input_path

logger = logging.getLogger(__name__)

__version__ = '1.4.0'
__all__ = ['convert_contract_numbering', 'NUMBERING_FORMATS']

# 最大重试次数
MAX_RETRIES = 3


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
