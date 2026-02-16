#!/usr/bin/env python3
"""生成剩余no-untyped-def错误的详细报告"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    
    print("运行mypy检查...")
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/", "--strict", "--no-pretty", "--no-error-summary"],
        capture_output=True,
        text=True,
        cwd=backend_path,
    )
    
    output = result.stdout + result.stderr
    
    # 解析错误
    pattern = re.compile(
        r'^(apps/[^:]+):(\d+):\d+:\s+error:\s+(.+?)\s+\[no-untyped-def\]'
    )
    
    errors = []
    for line in output.split('\n'):
        match = pattern.match(line)
        if match:
            file_path, line_no, message = match.groups()
            errors.append({
                'file': file_path,
                'line': int(line_no),
                'message': message
            })
    
    print(f"找到 {len(errors)} 个no-untyped-def错误\n")
    
    # 按文件分组
    by_file = defaultdict(list)
    for error in errors:
        by_file[error['file']].append(error)
    
    # 按错误消息类型分类
    by_type = defaultdict(list)
    for error in errors:
        msg = error['message']
        if "missing a return type annotation" in msg:
            by_type['missing_return'].append(error)
        elif "missing a type annotation for one or more arguments" in msg:
            by_type['missing_args'].append(error)
        elif "missing a type annotation" in msg:
            by_type['missing_annotation'].append(error)
        else:
            by_type['other'].append(error)
    
    # 生成报告
    report_path = backend_path / "remaining_no_untyped_def_errors.md"
    with open(report_path, "w") as f:
        f.write("# 剩余no-untyped-def错误报告\n\n")
        f.write(f"总错误数: {len(errors)}\n")
        f.write(f"涉及文件数: {len(by_file)}\n\n")
        
        f.write("## 按错误类型分类\n\n")
        for error_type, error_list in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
            f.write(f"- {error_type}: {len(error_list)}\n")
        
        f.write("\n## 错误最多的前20个文件\n\n")
        sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
        for file_path, file_errors in sorted_files[:20]:
            f.write(f"- {file_path}: {len(file_errors)}\n")
        
        f.write("\n## 详细错误列表\n\n")
        for file_path, file_errors in sorted_files:
            f.write(f"### {file_path} ({len(file_errors)} 个错误)\n\n")
            for error in file_errors:
                f.write(f"- Line {error['line']}: {error['message']}\n")
            f.write("\n")
    
    print(f"报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
