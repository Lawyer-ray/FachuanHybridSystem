#!/usr/bin/env python3
"""
Analyze all 'except Exception' blocks in the codebase.
Categorize them as:
1. Has logger - OK
2. Has raise - OK
3. Silent (no logger, no raise) - NEEDS FIX
"""
import ast
import os
from pathlib import Path
from typing import List, Tuple

class ExceptionAnalyzer(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.issues: List[Tuple[int, str]] = []
        
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # Check if this is 'except Exception'
        if node.type and isinstance(node.type, ast.Name) and node.type.id == "Exception":
            has_logger = False
            has_raise = False
            
            # Check the body for logger calls or raise statements
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Raise):
                    has_raise = True
                elif isinstance(stmt, ast.Call):
                    # Check for logger.* calls
                    if isinstance(stmt.func, ast.Attribute):
                        if isinstance(stmt.func.value, ast.Name) and stmt.func.value.id == "logger":
                            has_logger = True
            
            # If neither logger nor raise, it's a silent exception
            if not has_logger and not has_raise:
                self.issues.append((node.lineno, "Silent except Exception (no logger, no raise)"))
        
        self.generic_visit(node)

def analyze_file(filepath: Path) -> List[Tuple[int, str]]:
    """Analyze a single Python file for silent except Exception blocks."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content, filename=str(filepath))
        analyzer = ExceptionAnalyzer(str(filepath))
        analyzer.visit(tree)
        return analyzer.issues
    except Exception as e:
        return [(0, f"Error parsing file: {e}")]

def main():
    backend_dir = Path("backend/apps")
    issues_by_file = {}
    total_issues = 0
    
    for py_file in backend_dir.rglob("*.py"):
        # Skip migrations
        if "migrations" in py_file.parts:
            continue
            
        issues = analyze_file(py_file)
        if issues:
            issues_by_file[str(py_file)] = issues
            total_issues += len(issues)
    
    # Print results
    print(f"Found {total_issues} silent 'except Exception' blocks:\n")
    
    for filepath, issues in sorted(issues_by_file.items()):
        print(f"\n{filepath}:")
        for lineno, msg in issues:
            print(f"  Line {lineno}: {msg}")
    
    print(f"\n\nTotal files with issues: {len(issues_by_file)}")
    print(f"Total silent except Exception blocks: {total_issues}")

if __name__ == "__main__":
    main()
