"""
按标题拆分 Skill - 工具函数

提供文件名清洗、结果格式化等通用工具。
"""

from __future__ import annotations

import re
from pathlib import Path

from .formats import ILLEGAL_FILENAME_CHARS, MAX_FILENAME_LENGTH

__all__ = [
    'sanitize_filename',
    'generate_output_path',
    'format_split_summary',
    'validate_md_input',
]


def sanitize_filename(name: str) -> str:
    """清洗文件名:去除非法字符、压缩空白、限制长度

    Args:
        name: 原始文件名(不含扩展名)

    Returns:
        清洗后的文件名

    Examples:
        >>> sanitize_filename('民事起诉状')
        '民事起诉状'
        >>> sanitize_filename('广东省佛山市/顺德区:判决书')
        '广东省佛山市_顺德区_判决书'
    """
    # 替换非法字符
    for ch in ILLEGAL_FILENAME_CHARS:
        name = name.replace(ch, '_')
    # 压缩连续下划线
    name = re.sub(r'_+', '_', name)
    # 去除首尾空白和下划线
    name = name.strip().strip('_')
    # 限制长度
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH]
    return name or '未命名'


def generate_output_path(
    name: str, output_dir: str | Path, index: int, total: int
) -> Path:
    """生成拆分后的输出文件路径

    Args:
        name: 文书名称(会清洗)
        output_dir: 输出目录
        index: 当前片段序号(0-based)
        total: 总片段数(用于补零)

    Returns:
        输出 .md 文件路径
    """
    clean_name = sanitize_filename(name)
    out_dir = Path(output_dir)
    # 序号补零,便于排序
    width = max(2, len(str(total)))
    prefix = f'{index:0{width}d}'
    return out_dir / f'{prefix}_{clean_name}.md'


def format_split_summary(results: list[dict]) -> str:
    """格式化拆分结果为可读字符串

    Args:
        results: apply_split_map 返回的片段列表

    Returns:
        可读的汇总字符串
    """
    total = len(results)
    total_chars = sum(r.get('char_count', 0) for r in results)

    lines = [
        '\n=== 拆分完成 ===',
        f'共拆分为 {total} 个文件,总计 {total_chars} 字符',
        '',
    ]

    for r in results:
        idx = r['index']
        name = r['name']
        chars = r.get('char_count', 0)
        lines_b = r.get('line_count', 0)
        out = Path(r['output']).name
        doc_type = r.get('type', '')
        type_tag = f' [{doc_type}]' if doc_type else ''
        lines.append(f'  {idx + 1:2d}. {out}{type_tag} ({chars} 字符, {lines_b} 行)')

    return '\n'.join(lines)


def validate_md_input(input_path: str | Path) -> Path:
    """验证输入是 .md 文件且存在

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 不是 .md 文件
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f'文件不存在: {path}')
    if path.suffix.lower() != '.md':
        raise ValueError(f'仅支持 .md 文件,当前: {path.suffix}')
    return path
