"""修复QuerySet类型参数"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_queryset_types(file_path: Path) -> int:
    """修复文件中的QuerySet类型参数"""
    
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复 QuerySet[Model] -> QuerySet[Model, Model]
    # 匹配 QuerySet[XXX] 但不匹配已经有两个参数的
    pattern = r'QuerySet\[([A-Za-z_][A-Za-z0-9_]*)\](?!\[)'
    replacement = r'QuerySet[\1, \1]'
    
    content = re.sub(pattern, replacement, content)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        count = len(re.findall(pattern, original))
        logger.info(f"修复 {file_path.name}: {count}处")
        return count
    
    return 0


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent
    
    logger.info("=" * 60)
    logger.info("修复QuerySet类型参数")
    logger.info("=" * 60)
    
    total_fixed = 0
    
    # 查找所有Python文件
    for py_file in backend_path.glob('apps/**/*.py'):
        fixed = fix_queryset_types(py_file)
        total_fixed += fixed
    
    logger.info("=" * 60)
    logger.info(f"修复完成,共修复{total_fixed}处")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
