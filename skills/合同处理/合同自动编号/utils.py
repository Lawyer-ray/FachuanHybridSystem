"""
工具函数模块

提供通用的工具函数。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_input_path(input_path: str | Path) -> Path:
    """验证输入文件路径

    Args:
        input_path: 输入文件路径

    Returns:
        验证后的 Path 对象

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不支持
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if path.suffix.lower() not in ['.docx']:
        raise ValueError(f"不支持的文件格式: {path.suffix}，仅支持 .docx")

    return path


def generate_output_path(input_path: Path, suffix: str = '_自动编号') -> Path:
    """生成输出文件路径

    Args:
        input_path: 输入文件路径
        suffix: 文件名后缀

    Returns:
        输出文件路径
    """
    return input_path.parent / f"{input_path.stem}{suffix}{input_path.suffix}"


def format_numbering_mapping(numbered_paras: list[tuple[int, int, str, str]], max_display: int = 30) -> str:
    """格式化编号映射为可读字符串

    Args:
        numbered_paras: 编号段落列表
        max_display: 最大显示数量

    Returns:
        格式化的字符串
    """
    lines = []
    displayed = 0

    for idx, level, matched, text in numbered_paras:
        if displayed >= max_display:
            remaining = len(numbered_paras) - max_display
            lines.append(f"\n... 还有 {remaining} 个段落")
            break

        if level == 0:
            lines.append(f"\n--- {text[:20]} ---")
        else:
            prefix = '  ' * level
            note = ' [推断]' if matched == '' else ''
            lines.append(f"[{idx:3d}] {prefix}L{level}: {text[:40]}{note}")

        displayed += 1

    return '\n'.join(lines)


def get_level_name(level: int) -> str:
    """获取层级名称

    Args:
        level: 层级索引

    Returns:
        层级名称
    """
    names = {
        0: '一级标题',
        1: '二级标题',
        2: '三级标题',
        3: '四级标题',
        4: '五级标题',
    }
    return names.get(level, f'{level}级标题')
