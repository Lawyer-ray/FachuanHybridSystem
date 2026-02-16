#!/usr/bin/env python3
"""修复logging.py中的**kwargs类型注解"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def fix_logging_file() -> None:
    """修复logging.py文件"""
    file_path = Path(__file__).parent.parent / "apps/automation/utils/logging.py"
    
    logger.info(f"读取文件: {file_path}")
    content = file_path.read_text()
    
    # 替换**kwargs为**kwargs: Any
    # 需要导入Any
    if "from typing import" in content and "Any" not in content:
        # 在现有的typing导入中添加Any
        content = content.replace(
            "from typing import Optional",
            "from typing import Any, Optional"
        )
    elif "from typing import" not in content:
        # 添加新的typing导入
        lines = content.split('\n')
        # 找到第一个import语句后插入
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                lines.insert(i + 1, "from typing import Any")
                break
        content = '\n'.join(lines)
    
    # 替换所有的**kwargs为**kwargs: Any
    content = content.replace("**kwargs\n", "**kwargs: Any\n")
    content = content.replace("**kwargs)", "**kwargs: Any)")
    
    logger.info(f"写入修复后的文件")
    file_path.write_text(content)
    logger.info("修复完成")


if __name__ == "__main__":
    fix_logging_file()
