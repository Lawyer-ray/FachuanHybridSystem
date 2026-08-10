"""
文件识别 Skill - 文件检测与后端选择

职责:
- 检测文件格式是否支持
- 为文件选择合适的解析后端
- 扫描目录,返回所有支持格式的文件
"""

from __future__ import annotations

import logging
from pathlib import Path

from .formats import (
    ALL_SUPPORTED_FORMATS,
    AUTO_BACKEND_PRIORITY,
    BACKEND_AUTO,
    BACKEND_FEATURES,
    BACKEND_FORMATS,
    DEFAULT_BACKEND,
)

logger = logging.getLogger(__name__)

__all__ = [
    'detect_file_format',
    'is_format_supported',
    'select_backend',
    'scan_directory',
    'get_backend_name',
]


def detect_file_format(file_path: str | Path) -> str | None:
    """检测文件格式(返回扩展名小写,无点)

    Args:
        file_path: 文件路径

    Returns:
        格式字符串(如 'pdf'),无法识别返回 None

    Examples:
        >>> detect_file_format('/path/to/file.PDF')
        'pdf'
        >>> detect_file_format('/path/to/file')
        None
    """
    return Path(file_path).suffix.lower().lstrip('.') or None


def is_format_supported(file_path: str | Path) -> bool:
    """检查文件格式是否被任一后端支持"""
    fmt = detect_file_format(file_path)
    return fmt is not None and fmt in ALL_SUPPORTED_FORMATS


def select_backend(file_path: str | Path, preferred: str = DEFAULT_BACKEND) -> str:
    """为文件选择合适的解析后端

    Args:
        file_path: 文件路径
        preferred: 首选后端(auto/mineru/textin/local)

    Returns:
        实际使用的后端名称

    Raises:
        ValueError: 文件格式不支持,或首选后端不支持该格式
    """
    fmt = detect_file_format(file_path)
    if not fmt:
        raise ValueError(f'无法识别文件格式(无扩展名): {file_path}')

    if fmt not in ALL_SUPPORTED_FORMATS:
        raise ValueError(
            f'不支持的文件格式: .{fmt}。'
            f'支持的格式: {sorted(ALL_SUPPORTED_FORMATS)}'
        )

    if preferred == BACKEND_AUTO:
        # auto:选择支持此格式且功能最全的后端
        for backend in AUTO_BACKEND_PRIORITY:
            if fmt in BACKEND_FORMATS[backend]:
                logger.debug('为 .%s 选择后端: %s', fmt, backend)
                return backend
        # 理论上不会走到这里(已在 ALL_SUPPORTED_FORMATS 校验)
        raise ValueError(f'没有后端支持格式 .{fmt}')

    # 用户指定了具体后端
    if preferred not in BACKEND_FORMATS:
        raise ValueError(
            f'未知后端: {preferred}。可选: auto/mineru/textin/local'
        )
    if fmt not in BACKEND_FORMATS[preferred]:
        raise ValueError(
            f'后端 "{preferred}" 不支持格式 .{fmt}。'
            f'该后端支持: {sorted(BACKEND_FORMATS[preferred])}'
        )
    return preferred


def scan_directory(
    dir_path: str | Path, recursive: bool = False
) -> list[Path]:
    """扫描目录,返回所有支持格式的文件

    Args:
        dir_path: 目录路径
        recursive: 是否递归扫描子目录

    Returns:
        已排序的文件 Path 列表

    Raises:
        NotADirectoryError: 路径不是目录
    """
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise NotADirectoryError(f'不是目录: {dir_path}')

    iterator = dir_path.rglob('*') if recursive else dir_path.iterdir()
    results = [p for p in iterator if p.is_file() and is_format_supported(p)]
    return sorted(results)


def get_backend_name(backend: str) -> str:
    """获取后端的人类可读名称"""
    return BACKEND_FEATURES.get(backend, {}).get('name', backend)
