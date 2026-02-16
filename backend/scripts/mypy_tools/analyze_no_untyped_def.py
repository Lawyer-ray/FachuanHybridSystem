#!/usr/bin/env python3
"""分析no-untyped-def错误"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# 添加mypy_tools到路径
sys.path.insert(0, str(Path(__file__).parent))

from mypy_tools.error_analyzer import ErrorAnalyzer


def main() -> None:
    """主函数"""
    print("运行mypy检查...")
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    
    mypy_output = result.stdout + result.stderr
    
    # 使用ErrorAnalyzer分析错误
    analyzer = ErrorAnalyzer()
    all_errors = analyzer.analyze(mypy_output)
    
    # 过滤no-untyped-def错误
    untyped_def_errors = [e for e in all_errors if e.error_code == "no-untyped-def"]
    
    print(f"\n总错误数: {len(all_errors)}")
    print(f"no-untyped-def错误数: {len(untyped_def_errors)}")
    
    # 按文件分组
    by_file = defaultdict(list)
    for error in untyped_def_errors:
        by_file[error.file_path].append(error)
    
    print(f"\n涉及文件数: {len(by_file)}")
    
    # 按错误消息分类
    by_message_type = defaultdict(list)
    for error in untyped_def_errors:
        if "missing a return type annotation" in error.message:
            by_message_type["missing_return_type"].append(error)
        elif "missing a type annotation" in error.message and "argument" in error.message:
            by_message_type["missing_arg_type"].append(error)
        elif "missing a type annotation" in error.message:
            by_message_type["missing_type"].append(error)
        else:
            by_message_type["other"].append(error)
    
    print("\n按错误类型分类:")
    for msg_type, errors in sorted(by_message_type.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {msg_type}: {len(errors)}")
    
    # 显示错误最多的前10个文件
    print("\n错误最多的前10个文件:")
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
    for file_path, errors in sorted_files[:10]:
        print(f"  {file_path}: {len(errors)}")
    
    # 显示一些示例错误
    print("\n示例错误:")
    for i, error in enumerate(untyped_def_errors[:5], 1):
        print(f"\n{i}. {error.file_path}:{error.line}:{error.column}")
        print(f"   {error.message}")
    
    # 保存详细报告
    report_path = Path(__file__).parent.parent / "no_untyped_def_analysis.txt"
    with open(report_path, "w") as f:
        f.write(f"no-untyped-def错误分析报告\n")
        f.write(f"=" * 80 + "\n\n")
        f.write(f"总错误数: {len(untyped_def_errors)}\n")
        f.write(f"涉及文件数: {len(by_file)}\n\n")
        
        f.write("按错误类型分类:\n")
        for msg_type, errors in sorted(by_message_type.items(), key=lambda x: len(x[1]), reverse=True):
            f.write(f"  {msg_type}: {len(errors)}\n")
        
        f.write("\n按文件分组:\n")
        for file_path, errors in sorted_files:
            f.write(f"\n{file_path} ({len(errors)} 个错误):\n")
            for error in errors:
                f.write(f"  Line {error.line}: {error.message}\n")
    
    print(f"\n详细报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
