#!/usr/bin/env python3
"""修复validators中的Optional参数"""

from pathlib import Path

def fix_file(file_path: Path) -> int:
    """修复单个文件"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 替换 config: Dict[str, Any] = None 为 config: Optional[Dict[str, Any]] = None
    content = content.replace(
        'config: Dict[str, Any] = None',
        'config: Optional[Dict[str, Any]] = None'
    )
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return content.count('config: Optional[Dict[str, Any]] = None') - original.count('config: Optional[Dict[str, Any]] = None')
    
    return 0

def main() -> None:
    validators_path = Path(__file__).parent.parent / 'apps' / 'core' / 'config' / 'validators'
    
    files = [
        'type_validator.py',
        'range_validator.py',
        'dependency_validator.py'
    ]
    
    total = 0
    for filename in files:
        file_path = validators_path / filename
        if file_path.exists():
            count = fix_file(file_path)
            if count > 0:
                print(f"✓ {filename}: 修复 {count} 处")
                total += count
    
    print(f"\n总计修复: {total} 处")

if __name__ == '__main__':
    main()
