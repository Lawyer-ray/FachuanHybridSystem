#!/usr/bin/env python3
"""分析 mypy 错误分布"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

# 错误模式：apps/module/path/file.py:line:col: error: message [error-code]
ERROR_PATTERN = re.compile(
    r"^(apps/[^:]+):(\d+):(\d+): error: (.+?) \[([^\]]+)\]"
)


def analyze_mypy_errors(baseline_file: Path) -> dict[str, Any]:
    """分析 mypy 错误分布"""
    
    # 统计数据
    module_errors: dict[str, int] = defaultdict(int)
    error_type_counts: dict[str, int] = defaultdict(int)
    module_error_types: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    total_errors = 0
    
    # 读取整个文件内容，处理多行错误
    with open(baseline_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 查找所有以 apps/ 开头的行
    lines = content.split("\n")
    current_error = ""
    
    for line in lines:
        # 如果是新的错误行（以 apps/ 开头）
        if line.startswith("apps/"):
            # 处理之前的错误
            if current_error:
                match = ERROR_PATTERN.match(current_error)
                if match:
                    file_path, line_num, col_num, message, error_code = match.groups()
                    
                    # 提取模块名（apps/module_name）
                    parts = file_path.split("/")
                    if len(parts) >= 2:
                        module = f"{parts[0]}/{parts[1]}"
                        
                        # 统计
                        module_errors[module] += 1
                        error_type_counts[error_code] += 1
                        module_error_types[module][error_code] += 1
                        total_errors += 1
            
            # 开始新的错误
            current_error = line
        else:
            # 继续拼接当前错误
            current_error += " " + line.strip()
    
    # 处理最后一个错误
    if current_error:
        match = ERROR_PATTERN.match(current_error)
        if match:
            file_path, line_num, col_num, message, error_code = match.groups()
            parts = file_path.split("/")
            if len(parts) >= 2:
                module = f"{parts[0]}/{parts[1]}"
                module_errors[module] += 1
                error_type_counts[error_code] += 1
                module_error_types[module][error_code] += 1
                total_errors += 1
    
    return {
        "total_errors": total_errors,
        "module_errors": dict(module_errors),
        "error_type_counts": dict(error_type_counts),
        "module_error_types": {k: dict(v) for k, v in module_error_types.items()},
    }


def print_analysis(analysis: dict[str, Any]) -> None:
    """打印分析结果"""
    
    print(f"\n{'='*80}")
    print(f"Mypy 错误分布分析")
    print(f"{'='*80}\n")
    
    print(f"总错误数: {analysis['total_errors']}\n")
    
    # 按模块统计（降序）
    print(f"{'='*80}")
    print("按模块统计错误数（前20个）:")
    print(f"{'='*80}")
    module_errors = sorted(
        analysis["module_errors"].items(),
        key=lambda x: x[1],
        reverse=True
    )
    for i, (module, count) in enumerate(module_errors[:20], 1):
        percentage = (count / analysis["total_errors"]) * 100
        print(f"{i:2d}. {module:50s} {count:5d} ({percentage:5.2f}%)")
    
    # 按错误类型统计（降序）
    print(f"\n{'='*80}")
    print("按错误类型统计（前20个）:")
    print(f"{'='*80}")
    error_type_counts = sorted(
        analysis["error_type_counts"].items(),
        key=lambda x: x[1],
        reverse=True
    )
    for i, (error_type, count) in enumerate(error_type_counts[:20], 1):
        percentage = (count / analysis["total_errors"]) * 100
        print(f"{i:2d}. {error_type:30s} {count:5d} ({percentage:5.2f}%)")
    
    # 识别高错误模块（错误数 > 200）
    print(f"\n{'='*80}")
    print("高错误模块（错误数 > 200）:")
    print(f"{'='*80}")
    high_error_modules = [
        (module, count) for module, count in module_errors
        if count > 200
    ]
    for module, count in high_error_modules:
        percentage = (count / analysis["total_errors"]) * 100
        print(f"  {module:50s} {count:5d} ({percentage:5.2f}%)")
        
        # 显示该模块的主要错误类型
        module_types = sorted(
            analysis["module_error_types"][module].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        for error_type, type_count in module_types:
            type_percentage = (type_count / count) * 100
            print(f"    - {error_type:28s} {type_count:5d} ({type_percentage:5.2f}%)")
    
    print(f"\n{'='*80}\n")


def main() -> None:
    """主函数"""
    baseline_file = Path("backend/mypy_baseline.txt")
    
    if not baseline_file.exists():
        print(f"错误: 找不到基线文件 {baseline_file}")
        return
    
    analysis = analyze_mypy_errors(baseline_file)
    print_analysis(analysis)


if __name__ == "__main__":
    main()
