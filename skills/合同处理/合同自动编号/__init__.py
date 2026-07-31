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

from .converter import convert_numbering
from .detector import detect_numbering_structure
from .formats import NUMBERING_FORMATS, get_format
from .utils import format_numbering_mapping, generate_output_path, validate_input_path

logger = logging.getLogger(__name__)

__version__ = '1.1.0'
__all__ = ['convert_contract_numbering', 'NUMBERING_FORMATS']


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
    format_type: str | None = None
) -> dict:
    """
    转换合同文档的自动编号

    Args:
        input_path: 输入文档路径
        output_path: 输出文档路径（可选，默认为 {原文件名}_自动编号.docx）
        format_type: 编号格式类型 ('chinese' 或 'decimal')，None 则询问用户

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

    # 如果未指定格式，询问用户
    if format_type is None:
        format_type = get_user_format_choice()

    # 验证格式类型
    try:
        get_format(format_type)
    except ValueError as e:
        return {'success': False, 'error': str(e)}

    # 读取文档
    doc = Document(input_path)

    # 分析文档结构
    numbered_paras = detect_numbering_structure(doc, format_type)

    # 提取 Level 0 索引
    level0_indices = [idx for idx, level, _, _ in numbered_paras if level == 0]

    # 转换编号
    convert_numbering(doc, numbered_paras, {}, format_type)

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
    }
