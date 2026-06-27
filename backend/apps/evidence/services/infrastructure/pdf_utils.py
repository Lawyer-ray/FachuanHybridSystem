"""PDF 工具函数 — evidence 模块薄包装。

核心实现已迁移到 apps.core.services.pdf_utils，此处保持向后兼容的导入路径。
测试会 patch 本模块的函数名，因此需要定义包装函数而非纯 re-export。
"""

import contextlib
import io
import logging
from typing import Any

from apps.core.services.pdf_utils import (
    _read_django_field_file,
    _read_file_like,
    _read_from_path_attr,
    read_source_bytes,
)
from apps.core.utils.path import Path

logger = logging.getLogger("apps.evidence")

# 向后兼容：原函数名带下划线前缀
_read_source_bytes = read_source_bytes


def get_pdf_page_count_with_error(source: Any, default: int = 1) -> tuple[int, str | None]:
    """代理到 core 实现，保持本模块可被测试 mock。"""
    from apps.core.services.pdf_utils import get_pdf_page_count_with_error as _core_fn

    return _core_fn(source, default=default)


def get_pdf_page_count(source: Any, default: int = 1) -> int:
    """代理到 core 实现，保持本模块可被测试 mock。"""
    count, _ = get_pdf_page_count_with_error(source, default=default)
    return count
