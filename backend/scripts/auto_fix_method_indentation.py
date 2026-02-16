#!/usr/bin/env python3
"""自动修复方法定义的缩进问题"""
import re
from pathlib import Path
from typing import List, Tuple

def find_indentation_issues(file_path: str) -> List[Tuple[int, str, int, int]]:
    """
    查找缩进问题
    返回: [(行号, 方法名, 当前缩进, 应该的缩进)]
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    issues = []
    class_indent = None
    last_method_indent = None
    
    for i, line in enumerate(lines):
        # 检测类定义
        if re.match(r'^class\s+\w+', line):
            class_indent = 0
            last_method_indent = None
            continue
        
        # 检测方法定义
        match = re.match(r'(\s*)def\s+(\w+)', line)
        if match:
            indent_str, method_name = match.groups()
            current_indent = len(indent_str)
            
            # 如果在类中
            if class_indent is not None:
                expected_indent = 4  # 类方法应该缩进4个空格
                
                # 如果当前缩进远大于预期（比如12而不是4）
                if current_indent > expected_indent + 4:
                    issues.append((i + 1, method_name, current_indent, expected_indent))
                
                last_method_indent = current_indent
    
    return issues

def fix_method_indentation(file_path: str, issues: List[Tuple[int, str, int, int]]) -> bool:
    """修复方法缩进"""
    if not issues:
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 从后往前修复，避免行号变化
    for line_no, method_name, current_indent, expected_indent in reversed(issues):
        line_idx = line_no - 1
        
        # 修复方法定义行
        line = lines[line_idx]
        indent_diff = current_indent - expected_indent
        
        # 移除多余的缩进
        if line.startswith(' ' * current_indent):
            lines[line_idx] = ' ' * expected_indent + line[current_indent:]
        
        # 修复方法体的缩进
        # 找到方法体的结束位置
        method_body_indent = current_indent + 4
        j = line_idx + 1
        while j < len(lines):
            body_line = lines[j]
            
            # 如果是空行或注释，跳过
            if not body_line.strip() or body_line.strip().startswith('#'):
                j += 1
                continue
            
            # 如果遇到同级或更低级的def，停止
            if re.match(r'\s*def\s+', body_line):
                body_indent = len(body_line) - len(body_line.lstrip())
                if body_indent <= expected_indent:
                    break
            
            # 如果遇到类定义或其他顶级定义，停止
            if body_line and not body_line[0].isspace():
                break
            
            # 修复缩进
            body_indent = len(body_line) - len(body_line.lstrip())
            if body_indent >= method_body_indent:
                # 减少缩进
                new_indent = body_indent - indent_diff
                lines[j] = ' ' * new_indent + body_line.lstrip()
            
            j += 1
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    return True

def main():
    print("=== 自动修复方法缩进问题 ===\n")
    
    # 扫描所有Python文件
    files_to_check = [
        "apps/documents/services/placeholders/litigation/defense_party_service.py",
        "apps/documents/services/placeholders/litigation/complaint_party_service.py",
        "apps/documents/services/placeholders/basic/number_service.py",
        "apps/automation/services/ocr/ocr_service.py",
        "apps/documents/services/generation/authorization_material_generation_service.py",
        "apps/automation/services/scraper/scrapers/court_document/base_court_scraper.py",
        "apps/automation/tasks_impl/document_recognition.py",
        "apps/automation/services/scraper/scrapers/court_document_download.py",
    ]
    
    fixed_count = 0
    
    for file_path in files_to_check:
        if not Path(file_path).exists():
            continue
        
        issues = find_indentation_issues(file_path)
        if issues:
            print(f"文件: {file_path}")
            for line_no, method_name, current_indent, expected_indent in issues:
                print(f"  第{line_no}行: {method_name} (当前缩进:{current_indent}, 应为:{expected_indent})")
            
            if fix_method_indentation(file_path, issues):
                print(f"  ✓ 已修复 {len(issues)} 个缩进问题")
                fixed_count += len(issues)
            print()
    
    print(f"总共修复了 {fixed_count} 个缩进问题")

if __name__ == "__main__":
    main()
