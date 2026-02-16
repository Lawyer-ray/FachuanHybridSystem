#!/usr/bin/env python3
"""
批量修复 api/schemas 层的类型注解问题
基于错误分析的综合修复策略
"""
import re
import sys
from pathlib import Path
from typing import Any

def fix_api_file(file_path: Path) -> tuple[int, list[str]]:
    """修复 API 文件的类型注解"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        changes = []
        
        # 1. 修复 API 函数缺少类型注解
        # def func(request): → def func(request: Any) -> Any:
        # def func(request, param: Type): → def func(request: Any, param: Type) -> Any:
        
        # 匹配没有返回类型的函数定义
        pattern = r'(@router\.\w+[^\n]*\n)?def (\w+)\(([^)]+)\):'
        
        def add_types(match: re.Match[str]) -> str:
            decorator = match.group(1) or ''
            func_name = match.group(2)
            params = match.group(3)
            
            # 处理参数
            param_list = [p.strip() for p in params.split(',')]
            typed_params = []
            
            for param in param_list:
                if ':' in param:
                    # 已有类型注解
                    typed_params.append(param)
                elif '=' in param:
                    # 有默认值但无类型
                    param_name = param.split('=')[0].strip()
                    default_val = param.split('=')[1].strip()
                    typed_params.append(f"{param_name}: Any = {default_val}")
                else:
                    # 无类型无默认值
                    typed_params.append(f"{param}: Any")
            
            new_params = ', '.join(typed_params)
            return f"{decorator}def {func_name}({new_params}) -> Any:"
        
        # 只修复没有返回类型的函数
        lines = content.split('\n')
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # 检查是否是函数定义且没有 ->
            if line.strip().startswith('def ') and ')' in line and '->' not in line and line.strip().endswith(':'):
                # 检查参数中是否有未类型化的参数
                func_match = re.match(r'(\s*)def (\w+)\(([^)]+)\):', line)
                if func_match:
                    indent = func_match.group(1)
                    func_name = func_match.group(2)
                    params = func_match.group(3)
                    
                    # 处理参数
                    param_list = [p.strip() for p in params.split(',')]
                    typed_params = []
                    needs_fix = False
                    
                    for param in param_list:
                        if ':' not in param and '=' not in param:
                            # 需要添加类型
                            typed_params.append(f"{param}: Any")
                            needs_fix = True
                        elif '=' in param and ':' not in param.split('=')[0]:
                            # 有默认值但无类型
                            param_name = param.split('=')[0].strip()
                            default_val = param.split('=', 1)[1].strip()
                            typed_params.append(f"{param_name}: Any = {default_val}")
                            needs_fix = True
                        else:
                            typed_params.append(param)
                    
                    if needs_fix or True:  # 总是添加返回类型
                        new_params = ', '.join(typed_params)
                        new_lines.append(f"{indent}def {func_name}({new_params}) -> Any:")
                        changes.append(f"Added type annotations to {func_name}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
            i += 1
        
        content = '\n'.join(new_lines)
        
        # 2. 确保有 Any 导入
        if 'Any' in content and 'from typing import' in content:
            if not re.search(r'from typing import.*\bAny\b', content):
                content = re.sub(
                    r'(from typing import)([^(\n]*?)(\n)',
                    lambda m: f"{m.group(1)}{m.group(2)}, Any{m.group(3)}" if 'Any' not in m.group(2) else m.group(0),
                    content,
                    count=1
                )
                changes.append("Added Any to typing imports")
        elif 'Any' in content and 'from typing import' not in content:
            # 在第一个 import 之前添加
            import_match = re.search(r'^(from |import )', content, re.MULTILINE)
            if import_match:
                pos = import_match.start()
                content = content[:pos] + "from typing import Any\n\n" + content[pos:]
                changes.append("Added typing import")
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return (1, changes)
        return (0, [])
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return (0, [])

def fix_schema_file(file_path: Path) -> tuple[int, list[str]]:
    """修复 Schema 文件的类型注解"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        changes = []
        
        # 1. 修复 from_model 方法
        class_name_match = re.search(r'class\s+(\w+)', content)
        if class_name_match:
            class_name = class_name_match.group(1)
            # def from_model(cls, obj): → def from_model(cls, obj: Any) -> "ClassName":
            pattern = r'(\s+)@classmethod\s*\n\s+def from_model\(cls,\s*obj\):'
            replacement = rf'\1@classmethod\n\1def from_model(cls, obj: Any) -> "{class_name}":'
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                changes.append(f"Added type annotation to from_model method")
            
            # 没有 @classmethod 的情况
            pattern = r'(\s+)def from_model\(cls,\s*obj\):'
            replacement = rf'\1def from_model(cls, obj: Any) -> "{class_name}":'
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                changes.append(f"Added type annotation to from_model method")
        
        # 2. 确保有 Any 导入
        if 'Any' in content and 'from typing import' in content:
            if not re.search(r'from typing import.*\bAny\b', content):
                content = re.sub(
                    r'(from typing import)([^(\n]*?)(\n)',
                    lambda m: f"{m.group(1)}{m.group(2)}, Any{m.group(3)}" if 'Any' not in m.group(2) else m.group(0),
                    content,
                    count=1
                )
                changes.append("Added Any to typing imports")
        elif 'Any' in content and 'from typing import' not in content:
            import_match = re.search(r'^(from |import )', content, re.MULTILINE)
            if import_match:
                pos = import_match.start()
                content = content[:pos] + "from typing import Any\n\n" + content[pos:]
                changes.append("Added typing import")
        
        if content != original:
            file_path.write_text(content, encoding='utf-8')
            return (1, changes)
        return (0, [])
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return (0, [])

def main() -> None:
    """主函数"""
    backend_dir = Path(__file__).parent
    
    # 收集所有 api 和 schemas 文件
    api_files = list(backend_dir.glob("apps/*/api/**/*.py"))
    api_files += list(backend_dir.glob("apps/*/api.py"))
    
    schema_files = list(backend_dir.glob("apps/*/schemas/**/*.py"))
    schema_files += list(backend_dir.glob("apps/*/schemas.py"))
    
    print(f"Found {len(api_files)} API files and {len(schema_files)} schema files")
    
    fixed_count = 0
    
    # 修复 API 文件
    for file_path in api_files:
        if file_path.name == "__init__.py":
            continue
        
        count, changes = fix_api_file(file_path)
        if count > 0:
            fixed_count += 1
            print(f"✓ {file_path.relative_to(backend_dir)}")
            for change in changes:
                print(f"  - {change}")
    
    # 修复 Schema 文件
    for file_path in schema_files:
        if file_path.name == "__init__.py":
            continue
        
        count, changes = fix_schema_file(file_path)
        if count > 0:
            fixed_count += 1
            print(f"✓ {file_path.relative_to(backend_dir)}")
            for change in changes:
                print(f"  - {change}")
    
    print(f"\nFixed {fixed_count} files")

if __name__ == "__main__":
    main()
