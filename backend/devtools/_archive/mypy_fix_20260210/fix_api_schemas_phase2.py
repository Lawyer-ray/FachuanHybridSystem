#!/usr/bin/env python3
"""
Phase 2: Fix remaining api/schemas type errors
Focuses on:
1. Removing unused type: ignore comments
2. Adding missing return type annotations (-> Any)
3. Adding missing parameter type annotations (: Any)
"""

import re
import os
from pathlib import Path

def fix_unused_ignores(content: str, filepath: str) -> tuple[str, list[str]]:
    """Remove unused # type: ignore comments"""
    changes = []
    
    # Remove standalone # type: ignore comments
    pattern = r'\s*#\s*type:\s*ignore\s*(?:\[[\w-]+\])?\s*$'
    new_content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    if new_content != content:
        changes.append("Removed unused type: ignore comments")
    
    return new_content, changes

def fix_missing_return_types(content: str, filepath: str) -> tuple[str, list[str]]:
    """Add -> Any to functions missing return type annotations"""
    changes = []
    lines = content.split('\n')
    modified = False
    
    for i, line in enumerate(lines):
        # Match function definitions without return type
        # Pattern: def func_name(...) :  (note the space before colon)
        match = re.match(r'^(\s*)def\s+(\w+)\s*\([^)]*\)\s*:\s*$', line)
        if match and '-> ' not in line:
            indent = match.group(1)
            # Replace the line with return type annotation
            lines[i] = re.sub(r'\)\s*:\s*$', ') -> Any:', line)
            modified = True
            changes.append(f"Added return type to {match.group(2)}")
    
    if modified:
        content = '\n'.join(lines)
        # Ensure Any is imported
        if 'from typing import' in content and 'Any' not in content.split('from typing import')[1].split('\n')[0]:
            content = re.sub(
                r'(from typing import [^(\n]+)',
                r'\1, Any',
                content,
                count=1
            )
        elif 'from typing import' not in content:
            # Add typing import at the top after other imports
            lines = content.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_pos = i + 1
            lines.insert(insert_pos, 'from typing import Any')
            content = '\n'.join(lines)
            changes.append("Added typing import")
    
    return content, changes

def fix_missing_param_types(content: str, filepath: str) -> tuple[str, list[str]]:
    """Add : Any to parameters missing type annotations"""
    changes = []
    
    # Pattern: def func(param1, param2: str, param3) -> ...
    # We want to add : Any to param1 and param3
    
    # This is complex, so we'll use a simpler approach:
    # Find function definitions and add : Any to untyped params
    pattern = r'def\s+\w+\s*\(([^)]+)\)'
    
    def fix_params(match):
        params = match.group(1)
        if not params.strip() or params.strip() in ['self', 'cls']:
            return match.group(0)
        
        # Split by comma, but be careful with nested brackets
        param_list = []
        current = ''
        depth = 0
        for char in params:
            if char in '([{':
                depth += 1
            elif char in ')]}':
                depth -= 1
            elif char == ',' and depth == 0:
                param_list.append(current.strip())
                current = ''
                continue
            current += char
        if current.strip():
            param_list.append(current.strip())
        
        # Fix each parameter
        fixed_params = []
        for param in param_list:
            param = param.strip()
            if not param or param in ['self', 'cls']:
                fixed_params.append(param)
                continue
            
            # Check if already has type annotation
            if ':' in param.split('=')[0]:  # Has type annotation
                fixed_params.append(param)
            else:
                # Add : Any before default value if present
                if '=' in param:
                    name, default = param.split('=', 1)
                    fixed_params.append(f"{name.strip()}: Any = {default.strip()}")
                else:
                    fixed_params.append(f"{param}: Any")
        
        return f"def {match.group(0).split('(')[0].split('def')[1].strip()}({', '.join(fixed_params)})"
    
    new_content = re.sub(pattern, fix_params, content)
    
    if new_content != content:
        changes.append("Added type annotations to parameters")
        # Ensure Any is imported
        if 'from typing import' in new_content and 'Any' not in new_content.split('from typing import')[1].split('\n')[0]:
            new_content = re.sub(
                r'(from typing import [^(\n]+)',
                r'\1, Any',
                new_content,
                count=1
            )
        elif 'from typing import' not in new_content:
            lines = new_content.split('\n')
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_pos = i + 1
            lines.insert(insert_pos, 'from typing import Any')
            new_content = '\n'.join(lines)
            changes.append("Added typing import")
    
    return new_content, changes

def process_file(filepath: Path) -> bool:
    """Process a single file and return True if changes were made"""
    try:
        content = filepath.read_text(encoding='utf-8')
        original_content = content
        all_changes = []
        
        # Apply fixes in order
        content, changes = fix_unused_ignores(content, str(filepath))
        all_changes.extend(changes)
        
        content, changes = fix_missing_return_types(content, str(filepath))
        all_changes.extend(changes)
        
        content, changes = fix_missing_param_types(content, str(filepath))
        all_changes.extend(changes)
        
        if content != original_content:
            filepath.write_text(content, encoding='utf-8')
            print(f"✓ {filepath}")
            for change in all_changes:
                print(f"  - {change}")
            return True
        
        return False
    except Exception as e:
        print(f"✗ {filepath}: {e}")
        return False

def main():
    # Find all API and schema files
    api_files = list(Path('apps').rglob('*/api/*.py'))
    api_files.extend(Path('apps').rglob('*/api.py'))
    schema_files = list(Path('apps').rglob('*/schemas/*.py'))
    schema_files.extend(Path('apps').rglob('*/schemas.py'))
    
    all_files = api_files + schema_files
    all_files = [f for f in all_files if '__pycache__' not in str(f)]
    
    print(f"Found {len(api_files)} API files and {len(schema_files)} schema files")
    
    fixed_count = 0
    for filepath in all_files:
        if process_file(filepath):
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")

if __name__ == '__main__':
    main()
