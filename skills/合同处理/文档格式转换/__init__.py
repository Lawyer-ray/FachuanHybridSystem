"""
文档格式转换 Skill

将 .doc 文件转换为 .docx 格式。
调用后端 API 实现，底层使用 LibreOffice。
"""

import logging
from pathlib import Path

from .converter import check_health, convert_doc_to_docx

logger = logging.getLogger(__name__)

__version__ = '1.0.0'
__all__ = ['convert_doc_to_docx', 'check_health']


def convert_documents(
    input_paths: list[str | Path],
    output_dir: str | Path | None = None
) -> dict:
    """
    将 .doc 文件转换为 .docx 格式

    Args:
        input_paths: .doc 文件路径列表
        output_dir: 输出目录（可选，默认为第一个文件所在目录）

    Returns:
        转换结果字典
    """
    return convert_doc_to_docx(input_paths, output_dir)
