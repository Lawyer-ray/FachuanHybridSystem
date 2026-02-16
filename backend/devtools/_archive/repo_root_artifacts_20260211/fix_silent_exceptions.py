#!/usr/bin/env python3
"""
Fix silent except Exception blocks by adding logger.exception() calls.
"""
import ast
import re
from pathlib import Path
from typing import List, Tuple

def has_logger_import(content: str) -> bool:
    """Check if file already imports logger."""
    return bool(re.search(r'from .* import .*logger|import .*logger', content))

def add_logger_import(content: str) -> str:
    """Add logger import if not present."""
    if has_logger_import(content):
        return content
    
    # Find the best place to add the import (after other imports)
    lines = content.split('\n')
    last_import_idx = -1
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            last_import_idx = i
    
    # Add after last import or at the beginning
    insert_idx = last_import_idx + 1 if last_import_idx >= 0 else 0
    
    # Add logger import
    logger_import = "import logging\n\nlogger = logging.getLogger(__name__)"
    lines.insert(insert_idx, logger_import)
    
    return '\n'.join(lines)

def fix_silent_exception(content: str, lineno: int) -> str:
    """Add logger.exception() to a silent except Exception block."""
    lines = content.split('\n')
    
    # Find the except Exception line (lineno is 1-indexed)
    except_idx = lineno - 1
    
    if except_idx >= len(lines):
        return content
    
    # Find the indentation of the except block
    except_line = lines[except_idx]
    base_indent = len(except_line) - len(except_line.lstrip())
    body_indent = base_indent + 4
    
    # Find the body of the except block
    body_start = except_idx + 1
    body_end = body_start
    
    # Find where the except block ends
    for i in range(body_start, len(lines)):
        line = lines[i]
        if line.strip() == '':
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= base_indent:
            body_end = i
            break
    else:
        body_end = len(lines)
    
    # Check if body only contains 'pass' or 'continue'
    body_lines = lines[body_start:body_end]
    non_empty_body = [l for l in body_lines if l.strip() and not l.strip().startswith('#')]
    
    if len(non_empty_body) == 1 and non_empty_body[0].strip() in ('pass', 'continue'):
        # Replace pass/continue with logger.exception()
        logger_line = ' ' * body_indent + 'logger.exception("Unexpected error")'
        lines[body_start] = logger_line
        if non_empty_body[0].strip() == 'continue':
            # Keep the continue after logging
            lines.insert(body_start + 1, ' ' * body_indent + 'continue')
    else:
        # Insert logger.exception() at the beginning of the body
        logger_line = ' ' * body_indent + 'logger.exception("Unexpected error")'
        lines.insert(body_start, logger_line)
    
    return '\n'.join(lines)

def process_file(filepath: Path, issues: List[Tuple[int, str]]) -> bool:
    """Process a file and fix all silent exceptions."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Add logger import if needed
        content = add_logger_import(content)
        
        # Fix each silent exception (in reverse order to preserve line numbers)
        for lineno, _ in sorted(issues, reverse=True):
            content = fix_silent_exception(content, lineno)
        
        # Only write if content changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

# Issues data from analysis
ISSUES = {
    "backend/apps/core/config/migrator.py": [193, 247],
}

def main():
    fixed_count = 0
    
    for filepath_str, linenos in ISSUES.items():
        filepath = Path(filepath_str)
        if not filepath.exists():
            print(f"File not found: {filepath}")
            continue
        
        issues = [(lineno, "Silent except Exception") for lineno in linenos]
        if process_file(filepath, issues):
            fixed_count += 1
            print(f"Fixed {filepath}")
    
    print(f"\nFixed {fixed_count} files")

if __name__ == "__main__":
    main()
