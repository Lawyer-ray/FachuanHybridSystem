#!/usr/bin/env python3
"""批量修复litigation_ai模块的简单类型错误"""

import re
from pathlib import Path
from typing import Any


def fix_type_arg_errors(content: str) -> str:
    """修复泛型类型参数缺失"""
    # Dict -> dict[str, Any]
    content = re.sub(r'\bDict\b(?!\[)', 'dict[str, Any]', content)
    # dict(?![) -> dict[str, Any]
    content = re.sub(r'\bdict\b(?!\[)', 'dict[str, Any]', content)
    # list[dict] -> list[dict[str, Any]]
    content = re.sub(r'list\[dict\]', 'list[dict[str, Any]]', content)
    
    # 确保导入Any
    if 'dict[str, Any]' in content and 'from typing import' in content:
        if 'Any' not in content.split('from typing import')[1].split('\n')[0]:
            content = re.sub(
                r'(from typing import [^\n]+)',
                lambda m: m.group(1).rstrip() + ', Any' if not m.group(1).endswith(',') else m.group(1) + ' Any',
                content,
                count=1
            )
    elif 'dict[str, Any]' in content and 'from typing import' not in content:
        # 在文件开头添加导入
        lines = content.split('\n')
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith('from ') or line.startswith('import '):
                insert_pos = i + 1
            elif line.strip() and not line.startswith('#'):
                break
        lines.insert(insert_pos, 'from typing import Any')
        content = '\n'.join(lines)
    
    return content


def fix_optional_defaults(content: str) -> str:
    """修复Optional默认值问题"""
    # 修复 = None 的参数，添加 | None
    patterns = [
        # config: dict[str, Any] = None -> config: dict[str, Any] | None = None
        (r'(\w+):\s*(dict\[str,\s*Any\])\s*=\s*None', r'\1: \2 | None = None'),
        # selector: str = None -> selector: str | None = None
        (r'(\w+):\s*(str)\s*=\s*None(?!\))', r'\1: \2 | None = None'),
        # preview_page: int = None -> preview_page: int | None = None
        (r'(\w+):\s*(int)\s*=\s*None', r'\1: \2 | None = None'),
        # original_error: Exception = None -> original_error: Exception | None = None
        (r'(\w+):\s*(Exception)\s*=\s*None', r'\1: \2 | None = None'),
        # expected_extensions: list[Any] = None -> expected_extensions: list[Any] | None = None
        (r'(\w+):\s*(list\[Any\])\s*=\s*None', r'\1: \2 | None = None'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    return content


def fix_any_type(content: str) -> str:
    """修复any类型错误"""
    # value: any -> value: Any
    content = re.sub(r':\s*any\b', ': Any', content)
    return content


def fix_return_types(content: str) -> str:
    """为缺少返回类型的函数添加-> None"""
    # def __post_init__(self): -> def __post_init__(self) -> None:
    content = re.sub(
        r'def __post_init__\(self\):',
        'def __post_init__(self) -> None:',
        content
    )
    return content


def fix_unused_ignore_comments(content: str) -> str:
    """移除unused type: ignore注释"""
    # 移除 # type: ignore[attr-defined] 等
    content = re.sub(r'\s*#\s*type:\s*ignore\[[\w-]+\]', '', content)
    return content


def fix_invalid_type_annotations(content: str) -> str:
    """修复无效的类型注解"""
    # -> "from": -> -> "CourtSMSDetailSchema":
    content = re.sub(r'->\s*"from":', '-> "CourtSMSDetailSchema":', content)
    # set[Any][datetime] -> set[datetime]
    content = re.sub(r'set\[Any\]\[datetime\]', 'set[datetime]', content)
    return content


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # 应用所有修复
        content = fix_type_arg_errors(content)
        content = fix_optional_defaults(content)
        content = fix_any_type(content)
        content = fix_return_types(content)
        content = fix_unused_ignore_comments(content)
        content = fix_invalid_type_annotations(content)
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            print(f"✓ 修复: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"✗ 错误 {file_path}: {e}")
        return False


def main() -> None:
    """主函数"""
    base_dir = Path(__file__).parent.parent
    
    # 需要修复的目录
    target_dirs = [
        base_dir / "apps" / "client" / "services",
        base_dir / "apps" / "automation" / "services" / "scraper" / "core",
        base_dir / "apps" / "automation" / "schemas",
        base_dir / "apps" / "automation" / "services" / "document",
        base_dir / "apps" / "automation" / "services" / "fee_notice",
        base_dir / "apps" / "automation" / "utils",
        base_dir / "apps" / "automation" / "services" / "chat",
        base_dir / "apps" / "reminders" / "services",
    ]
    
    fixed_count = 0
    total_count = 0
    
    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
            
        for py_file in target_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            total_count += 1
            if process_file(py_file):
                fixed_count += 1
    
    print(f"\n完成! 修复了 {fixed_count}/{total_count} 个文件")


if __name__ == "__main__":
    main()
