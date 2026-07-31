"""
doc转docx Skill

将 .doc 文件转换为 .docx 格式。
直接调用 LibreOffice 实现，无需后端 API。
"""

import logging
from pathlib import Path

from .converter import check_libreoffice, convert_doc_to_docx

logger = logging.getLogger(__name__)

__version__ = '1.1.0'
__all__ = ['convert_doc_to_docx', 'check_libreoffice']


def convert_documents(
    input_paths: list[str | Path],
    output_dir: str | Path | None = None
) -> dict:
    """
    将 .doc 文件转换为 .docx 格式

    Args:
        input_paths: .doc 文件路径列表
        output_dir: 输出目录（可选，默认为第一个文件所在目录下的 converted_docx）

    Returns:
        转换结果字典
    """
    return convert_doc_to_docx(input_paths, output_dir)
