"""为使用Any的文件添加typing导入"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent.parent
    
    logger.info("开始添加Any导入...")
    
    # 运行mypy获取name-defined错误
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    output = result.stdout + result.stderr
    
    # 提取 Name "Any" is not defined 错误
    files_need_any: set[str] = set()
    
    for line in output.split('\n'):
        if 'Name "Any" is not defined' in line or 'name-defined' in line:
            match = re.match(r'^(apps/[^:]+):', line)
            if match:
                file_path = match.group(1)
                # 检查文件是否使用了Any
                full_path = backend_path / file_path
                if full_path.exists():
                    content = full_path.read_text(encoding='utf-8')
                    if 'Any' in content and 'from typing import' in content:
                        files_need_any.add(file_path)
    
    logger.info(f"找到 {len(files_need_any)} 个文件需要添加Any导入")
    
    # 修复每个文件
    fixed_count = 0
    for file_path in files_need_any:
        full_path = backend_path / file_path
        content = full_path.read_text(encoding='utf-8')
        
        # 检查是否已经导入了Any
        if re.search(r'from typing import.*\bAny\b', content):
            continue
        
        # 查找typing导入行
        lines = content.split('\n')
        modified = False
        
        for i, line in enumerate(lines):
            # 找到 from typing import ... 的行
            if line.strip().startswith('from typing import'):
                # 检查是否是多行导入
                if '(' in line:
                    # 多行导入，找到结束的)
                    end_idx = i
                    for j in range(i, len(lines)):
                        if ')' in lines[j]:
                            end_idx = j
                            break
                    
                    # 在最后一个导入后添加Any
                    last_line = lines[end_idx]
                    if last_line.strip() == ')':
                        # 在)之前添加
                        lines[end_idx - 1] = lines[end_idx - 1].rstrip(',') + ','
                        lines.insert(end_idx, '    Any,')
                    else:
                        # 在)之前添加
                        lines[end_idx] = last_line.replace(')', ', Any)')
                    modified = True
                    break
                else:
                    # 单行导入
                    if not line.strip().endswith(','):
                        lines[i] = line.rstrip() + ', Any'
                    else:
                        lines[i] = line.rstrip() + ' Any'
                    modified = True
                    break
        
        if modified:
            full_path.write_text('\n'.join(lines), encoding='utf-8')
            fixed_count += 1
            logger.info(f"修复 {file_path}")
    
    logger.info(f"修复完成，共修复 {fixed_count} 个文件")


if __name__ == '__main__':
    main()
