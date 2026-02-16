"""为Django Model添加外键_id字段的类型注解"""

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
    
    logger.info("开始添加外键_id字段类型注解...")
    
    # 运行mypy获取错误
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    output = result.stdout + result.stderr
    
    # 提取_id字段错误
    errors: dict[str, set[str]] = {}  # {model_file: {field_names}}
    
    for line in output.split('\n'):
        if 'has no attribute' in line and '_id"' in line:
            # 提取文件路径和字段名
            file_match = re.search(r'(apps/[^/]+/models[^:]*\.py)', line)
            field_match = re.search(r'has no attribute "([^"]+_id)"', line)
            
            if file_match and field_match:
                file_path = file_match.group(1)
                field_name = field_match.group(1)
                
                if file_path not in errors:
                    errors[file_path] = set()
                errors[file_path].add(field_name)
    
    logger.info(f"找到 {len(errors)} 个Model文件需要添加_id字段注解")
    
    # 修复每个文件
    fixed_count = 0
    for file_path, field_names in errors.items():
        full_path = backend_path / file_path
        if not full_path.exists():
            continue
        
        content = full_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 查找Model类定义
        modified = False
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 查找class定义
            if line.strip().startswith('class ') and '(models.Model)' in line or '(Model)' in line:
                class_match = re.match(r'\s*class\s+(\w+)\s*\(', line)
                if class_match:
                    class_name = class_match.group(1)
                    indent = len(line) - len(line.lstrip())
                    
                    # 在类定义后添加_id字段注解
                    # 找到类的第一行（可能是docstring）
                    j = i + 1
                    while j < len(lines) and (lines[j].strip().startswith('"""') or 
                                              lines[j].strip().startswith("'''") or
                                              lines[j].strip() == '' or
                                              '"""' in lines[j] or "'''" in lines[j]):
                        j += 1
                    
                    # 在这里插入_id字段注解
                    annotations_to_add = []
                    for field_name in sorted(field_names):
                        # 检查是否已经有这个注解
                        if f'{field_name}:' not in content:
                            annotations_to_add.append(f"{' ' * (indent + 4)}{field_name}: int  # Django外键_id字段")
                    
                    if annotations_to_add:
                        # 插入注解
                        for annotation in reversed(annotations_to_add):
                            lines.insert(j, annotation)
                            fixed_count += 1
                            modified = True
                            logger.info(f"添加 {file_path} - {class_name}.{annotation.strip()}")
            
            i += 1
        
        # 写回文件
        if modified:
            full_path.write_text('\n'.join(lines), encoding='utf-8')
    
    logger.info(f"修复完成，共添加 {fixed_count} 个字段注解")


if __name__ == '__main__':
    main()
