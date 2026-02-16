#!/usr/bin/env python3
"""批量修复 SMS 模块的 Django ORM 类型错误"""

import re
from pathlib import Path
from typing import Any


def fix_court_sms_attributes(content: str) -> str:
    """修复 CourtSMS 动态属性访问"""
    # sms.id -> cast(int, sms.pk)
    content = re.sub(r'(\bsms)\.id\b', r'cast(int, \1.pk)', content)
    
    # sms.case_id -> 需要手动处理，因为这不是 Model 的标准属性
    # 保持原样，让开发者手动检查
    
    return content


def fix_scraper_task_attributes(content: str) -> str:
    """修复 ScraperTask 动态属性访问"""
    # task.id -> cast(int, task.pk)
    content = re.sub(r'(\btask)\.id\b', r'cast(int, \1.pk)', content)
    
    # scraper_task.id -> cast(int, scraper_task.pk)
    content = re.sub(r'(\bscraper_task)\.id\b', r'cast(int, \1.pk)', content)
    
    return content


def fix_case_attribute_access(content: str) -> str:
    """修复 case 属性访问"""
    # case.id -> cast(int, case.pk)
    content = re.sub(r'(\bcase)\.id\b', r'cast(int, \1.pk)', content)
    
    # case.name -> 需要使用 getattr 或 cast
    # 保持原样，因为 name 是实际字段
    
    return content


def fix_case_log_attribute_access(content: str) -> str:
    """修复 case_log 属性访问"""
    # case_log.id -> cast(int, case_log.pk)
    content = re.sub(r'(\bcase_log)\.id\b', r'cast(int, \1.pk)', content)
    
    return content


def ensure_cast_import(content: str) -> str:
    """确保导入了 cast"""
    if 'from typing import' in content and 'cast' not in content:
        # 在现有的 typing 导入中添加 cast
        content = re.sub(
            r'from typing import ([^\n]+)',
            lambda m: f'from typing import {m.group(1)}, cast' if 'cast' not in m.group(1) else m.group(0),
            content,
            count=1
        )
    elif 'from typing import' not in content and 'cast(' in content:
        # 添加 cast 导入
        lines = content.split('\n')
        import_index = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                import_index = i + 1
        lines.insert(import_index, 'from typing import cast')
        content = '\n'.join(lines)
    
    return content


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    sms_path = backend_path / 'apps' / 'automation' / 'services' / 'sms'
    
    if not sms_path.exists():
        print(f"SMS 路径不存在: {sms_path}")
        return
    
    fixed_files = 0
    
    for py_file in sms_path.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            original = content
            
            # 应用修复
            content = fix_court_sms_attributes(content)
            content = fix_scraper_task_attributes(content)
            content = fix_case_attribute_access(content)
            content = fix_case_log_attribute_access(content)
            content = ensure_cast_import(content)
            
            if content != original:
                py_file.write_text(content, encoding='utf-8')
                fixed_files += 1
                print(f"✓ {py_file.relative_to(backend_path)}")
        
        except Exception as e:
            print(f"✗ {py_file.relative_to(backend_path)}: {e}")
    
    print(f"\n修复了 {fixed_files} 个文件")


if __name__ == '__main__':
    main()
