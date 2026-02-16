"""简单的type-arg错误修复器 - 直接文本替换"""

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
    
    logger.info("开始修复type-arg错误...")
    
    # 运行mypy获取错误
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    output = result.stdout + result.stderr
    
    # 提取type-arg错误的文件和行号
    # 格式可能是多行的，需要合并
    lines = output.split('\n')
    errors: list[tuple[str, int, str]] = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        # 查找包含文件路径和行号的行
        match = re.match(r'^(apps/[^:]+):(\d+):\d+:', line)
        if match:
            file_path = match.group(1)
            line_no = int(match.group(2))
            
            # 检查是否是type-arg错误
            full_line = line
            # 可能错误信息在下一行
            if i + 1 < len(lines) and '[type-arg]' in lines[i + 1]:
                full_line += ' ' + lines[i + 1]
            
            if '[type-arg]' in full_line:
                # 提取泛型类型名称
                type_match = re.search(r'generic type "([^"]+)"', full_line)
                if type_match:
                    generic_type = type_match.group(1)
                    errors.append((file_path, line_no, generic_type))
        i += 1
    
    logger.info(f"找到 {len(errors)} 个type-arg错误")
    
    # 按文件分组
    from collections import defaultdict
    errors_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for file_path, line_no, generic_type in errors:
        errors_by_file[file_path].append((line_no, generic_type))
    
    logger.info(f"涉及 {len(errors_by_file)} 个文件")
    
    # 修复每个文件
    fixed_count = 0
    for file_path, file_errors in errors_by_file.items():
        full_path = backend_path / file_path
        if not full_path.exists():
            continue
        
        # 读取文件
        content = full_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 修复每个错误（从后往前，避免行号变化）
        file_errors_sorted = sorted(file_errors, key=lambda x: x[0], reverse=True)
        modified = False
        
        for line_no, generic_type in file_errors_sorted:
            if line_no <= 0 or line_no > len(lines):
                continue
            
            line = lines[line_no - 1]
            
            # 根据泛型类型进行替换
            new_line = fix_generic_type(line, generic_type)
            if new_line != line:
                lines[line_no - 1] = new_line
                modified = True
                fixed_count += 1
                logger.info(f"修复 {file_path}:{line_no} - {generic_type}")
        
        # 写回文件
        if modified:
            # 确保有future annotations导入
            new_content = '\n'.join(lines)
            if 'from __future__ import annotations' not in new_content:
                # 在文件开头添加（在docstring之后）
                if lines and lines[0].strip().startswith('"""'):
                    # 找到docstring结束
                    end_idx = 0
                    for i in range(1, len(lines)):
                        if '"""' in lines[i]:
                            end_idx = i + 1
                            break
                    lines.insert(end_idx, '')
                    lines.insert(end_idx, 'from __future__ import annotations')
                else:
                    lines.insert(0, 'from __future__ import annotations')
                    lines.insert(1, '')
            
            full_path.write_text('\n'.join(lines), encoding='utf-8')
    
    logger.info(f"修复完成，共修复 {fixed_count} 个错误")


def fix_generic_type(line: str, generic_type: str) -> str:
    """修复一行中的泛型类型"""
    # 常见的泛型类型映射
    type_map = {
        'dict': 'dict[str, Any]',
        'Dict': 'Dict[str, Any]',
        'list': 'list[Any]',
        'List': 'List[Any]',
        'set': 'set[Any]',
        'Set': 'Set[Any]',
        'tuple': 'tuple[Any, ...]',
        'Tuple': 'Tuple[Any, ...]',
        'deque': 'deque[Any]',
        'defaultdict': 'defaultdict[str, Any]',
        'OrderedDict': 'OrderedDict[str, Any]',
        'Callable': 'Callable[..., Any]',
    }
    
    if generic_type not in type_map:
        return line
    
    replacement = type_map[generic_type]
    
    # 替换模式：
    # 1. -> dict: 替换为 -> dict[str, Any]:
    # 2. : dict = 替换为 : dict[str, Any] =
    # 3. : dict) 替换为 : dict[str, Any])
    
    patterns = [
        (rf'-> {generic_type}:', f'-> {replacement}:'),
        (rf': {generic_type} =', f': {replacement} ='),
        (rf': {generic_type}\)', f': {replacement})'),
        (rf': {generic_type},', f': {replacement},'),
        (rf': {generic_type}\s*$', f': {replacement}'),
    ]
    
    for pattern, repl in patterns:
        line = re.sub(pattern, repl, line)
    
    return line


if __name__ == '__main__':
    main()
