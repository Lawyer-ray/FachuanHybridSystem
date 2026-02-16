"""为Django Model添加外键_id字段的类型注解"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_fk_id_errors(backend_path: Path) -> dict[Path, set[str]]:
    """找出所有外键_id字段的attr-defined错误"""
    
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    # 存储: {文件路径: {字段名集合}}
    fk_errors: dict[Path, set[str]] = {}
    
    lines = result.stdout.split('\n')
    for i, line in enumerate(lines):
        # 查找 has no attribute "_id" 错误
        if 'has no attribute' in line and '_id"' in line:
            # 提取字段名
            match = re.search(r'has no attribute "(\w+_id)"', line)
            if match:
                field_name = match.group(1)
                
                # 向前查找文件路径
                for j in range(max(0, i-5), i+1):
                    if lines[j].startswith('apps/') and ':' in lines[j]:
                        file_path_str = lines[j].split(':')[0]
                        file_path = backend_path / file_path_str
                        if file_path.exists():
                            if file_path not in fk_errors:
                                fk_errors[file_path] = set()
                            fk_errors[file_path].add(field_name)
                            break
    
    return fk_errors


def add_fk_annotations(file_path: Path, field_names: set[str]) -> int:
    """为文件中的Model类添加外键_id字段注解"""
    
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    modified = False
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 查找Model类定义
        if re.match(r'\s*class\s+\w+\s*\(.*Model.*\):', line):
            class_match = re.match(r'(\s*)class\s+(\w+)', line)
            if class_match:
                indent = class_match.group(1)
                class_name = class_match.group(2)
                
                # 跳过docstring
                j = i + 1
                while j < len(lines) and (lines[j].strip().startswith('"""') or 
                                          lines[j].strip().startswith("'''") or
                                          '"""' in lines[j] or "'''" in lines[j] or
                                          lines[j].strip() == ''):
                    j += 1
                
                # 检查需要添加哪些字段
                fields_to_add = []
                for field_name in field_names:
                    # 检查是否已有注解
                    has_annotation = False
                    for k in range(j, min(j + 50, len(lines))):
                        if f'{field_name}:' in lines[k] or f'{field_name} :' in lines[k]:
                            has_annotation = True
                            break
                        # 如果遇到下一个类或方法定义,停止搜索
                        if re.match(r'\s*(class|def)\s+', lines[k]) and k > j:
                            break
                    
                    if not has_annotation:
                        fields_to_add.append(field_name)
                
                # 添加字段注解
                for field_name in sorted(fields_to_add):
                    lines.insert(j, f"{indent}    {field_name}: int  # 外键ID字段")
                    j += 1
                    modified = True
                    logger.info(f"添加 {class_name}.{field_name}")
        
        i += 1
    
    if modified:
        file_path.write_text('\n'.join(lines), encoding='utf-8')
        return len(fields_to_add)
    
    return 0


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent
    
    logger.info("=" * 60)
    logger.info("修复Django Model外键_id字段")
    logger.info("=" * 60)
    
    # 找出所有需要修复的字段
    fk_errors = find_fk_id_errors(backend_path)
    
    logger.info(f"找到{len(fk_errors)}个文件需要修复")
    
    total_fixed = 0
    for file_path, field_names in sorted(fk_errors.items()):
        logger.info(f"\n处理 {file_path.relative_to(backend_path)}")
        logger.info(f"  字段: {', '.join(sorted(field_names))}")
        fixed = add_fk_annotations(file_path, field_names)
        total_fixed += fixed
    
    logger.info("=" * 60)
    logger.info(f"修复完成,共添加{total_fixed}个字段注解")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
