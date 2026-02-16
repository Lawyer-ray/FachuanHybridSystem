"""修复缺少Any导入的文件"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_any_imports(backend_path: Path) -> int:
    """修复缺少Any导入的文件"""
    
    # 运行mypy找出所有缺少Any导入的文件
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    files_need_any: set[Path] = set()
    
    lines = result.stdout.split('\n')
    for i, line in enumerate(lines):
        if 'Name "Any" is not defined' in line:
            # 向前查找文件路径(在前面的行)
            for j in range(max(0, i-5), i+1):
                if lines[j].startswith('apps/') and ':' in lines[j]:
                    file_path_str = lines[j].split(':')[0]
                    file_path = backend_path / file_path_str
                    if file_path.exists():
                        files_need_any.add(file_path)
                        break
    
    logger.info(f"找到{len(files_need_any)}个文件缺少Any导入")
    
    fixed = 0
    for file_path in sorted(files_need_any):
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 查找typing导入行
        typing_line_idx = -1
        for i, line in enumerate(lines):
            if re.match(r'from typing import', line):
                typing_line_idx = i
                break
        
        if typing_line_idx >= 0:
            # 检查是否已有Any
            if 'Any' not in lines[typing_line_idx]:
                # 添加Any到导入
                lines[typing_line_idx] = lines[typing_line_idx].rstrip() + ', Any'
                file_path.write_text('\n'.join(lines), encoding='utf-8')
                fixed += 1
                logger.info(f"修复 {file_path.relative_to(backend_path)}")
        else:
            # 没有typing导入,需要添加
            # 找到合适的位置插入(在from __future__ import之后,在其他导入之前)
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('from __future__'):
                    insert_idx = i + 1
                    break
                elif line.startswith('import ') or line.startswith('from '):
                    insert_idx = i
                    break
            
            lines.insert(insert_idx, 'from typing import Any')
            file_path.write_text('\n'.join(lines), encoding='utf-8')
            fixed += 1
            logger.info(f"添加Any导入 {file_path.relative_to(backend_path)}")
    
    return fixed


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent
    
    logger.info("=" * 60)
    logger.info("修复缺少Any导入的文件")
    logger.info("=" * 60)
    
    fixed = fix_any_imports(backend_path)
    
    logger.info("=" * 60)
    logger.info(f"修复完成,共修复{fixed}个文件")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
