#!/usr/bin/env python3
"""
分析 document_delivery 模块的 mypy 类型错误
按错误类型分类统计
"""

import re
from collections import defaultdict
from pathlib import Path


def parse_mypy_output(output_file: Path) -> dict[str, list[str]]:
    """解析 mypy 输出，按错误类型分类"""
    errors_by_type = defaultdict(list)
    
    with open(output_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 分割成单独的错误块
    # 每个错误以 "apps/...error:" 开始
    error_blocks = re.split(r'(?=apps/[^:]+:\d+:\d+: error:)', content)
    
    for block in error_blocks:
        if not block.strip():
            continue
        
        # 提取文件路径、行号、列号
        match = re.match(r'(apps/[^:]+):(\d+):(\d+): error:', block)
        if not match:
            continue
        
        file_path, line_num, col = match.groups()
        
        # 只统计 document_delivery 相关的错误
        if 'document_delivery' not in file_path:
            continue
        
        # 提取错误消息和错误代码
        # 错误代码在方括号中，如 [attr-defined]
        error_code_match = re.search(r'\[([^\]]+)\]', block)
        if error_code_match:
            error_code = error_code_match.group(1)
        else:
            error_code = "unknown"
        
        # 提取完整的错误消息（去除文件路径行和错误代码）
        lines = block.split('\n')
        message_lines = []
        for line in lines[1:]:  # 跳过第一行（文件路径）
            line = line.strip()
            if line and not line.startswith('apps/'):
                # 移除错误代码部分
                if '[' in line and ']' in line:
                    line = line[:line.rfind('[')].strip()
                message_lines.append(line)
        
        full_message = ' '.join(message_lines)
        
        error_info = f"{file_path}:{line_num}:{col}: {full_message}"
        errors_by_type[error_code].append(error_info)
    
    return errors_by_type


def print_statistics(errors_by_type: dict[str, list[str]]) -> None:
    """打印错误统计信息"""
    total_errors = sum(len(errors) for errors in errors_by_type.values())
    
    print("=" * 80)
    print(f"Document Delivery 模块类型错误分析")
    print("=" * 80)
    print(f"\n总错误数: {total_errors}\n")
    
    # 按错误数量排序
    sorted_errors = sorted(errors_by_type.items(), key=lambda x: len(x[1]), reverse=True)
    
    print("错误类型分布:")
    print("-" * 80)
    print(f"{'错误类型':<30} {'数量':<10} {'占比':<10}")
    print("-" * 80)
    
    for error_code, errors in sorted_errors:
        count = len(errors)
        percentage = (count / total_errors * 100) if total_errors > 0 else 0
        print(f"{error_code:<30} {count:<10} {percentage:>6.1f}%")
    
    print("-" * 80)
    print(f"{'总计':<30} {total_errors:<10} {'100.0%':>10}")
    print("=" * 80)
    
    # 打印每种错误类型的详细信息（前3个示例）
    print("\n详细错误示例（每种类型显示前3个）:")
    print("=" * 80)
    
    for error_code, errors in sorted_errors:
        print(f"\n[{error_code}] - {len(errors)} 个错误")
        print("-" * 80)
        for i, error in enumerate(errors[:3], 1):
            print(f"{i}. {error}")
        if len(errors) > 3:
            print(f"   ... 还有 {len(errors) - 3} 个类似错误")


def generate_markdown_report(errors_by_type: dict[str, list[str]], output_file: Path) -> None:
    """生成 Markdown 格式的分析报告"""
    total_errors = sum(len(errors) for errors in errors_by_type.values())
    sorted_errors = sorted(errors_by_type.items(), key=lambda x: len(x[1]), reverse=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Document Delivery 模块类型错误分析\n\n")
        f.write(f"**总错误数**: {total_errors}\n\n")
        
        f.write("## 错误类型分布\n\n")
        f.write("| 错误类型 | 数量 | 占比 |\n")
        f.write("|---------|------|------|\n")
        
        for error_code, errors in sorted_errors:
            count = len(errors)
            percentage = (count / total_errors * 100) if total_errors > 0 else 0
            f.write(f"| `{error_code}` | {count} | {percentage:.1f}% |\n")
        
        f.write(f"\n**总计**: {total_errors} 个错误\n\n")
        
        f.write("## 详细错误列表\n\n")
        
        for error_code, errors in sorted_errors:
            f.write(f"### [{error_code}] - {len(errors)} 个错误\n\n")
            
            for i, error in enumerate(errors, 1):
                f.write(f"{i}. `{error}`\n")
            
            f.write("\n")
        
        f.write("## 修复策略建议\n\n")
        
        for error_code, errors in sorted_errors[:5]:  # 只为前5种错误类型提供建议
            f.write(f"### {error_code}\n\n")
            
            if error_code == "attr-defined":
                f.write("**修复策略**: Django Model 动态属性问题\n")
                f.write("- 使用 `cast()` 进行类型转换\n")
                f.write("- 为 CourtSMS Model 创建类型存根文件\n")
                f.write("- 示例: `cast(int, sms.id)`\n\n")
            
            elif error_code == "no-untyped-def":
                f.write("**修复策略**: 函数缺少类型注解\n")
                f.write("- 为所有参数添加类型注解\n")
                f.write("- 为返回值添加类型注解\n")
                f.write("- 示例: `def func(self, param: str) -> bool:`\n\n")
            
            elif error_code == "no-any-return":
                f.write("**修复策略**: 返回 Any 类型\n")
                f.write("- 使用 `cast()` 明确返回类型\n")
                f.write("- 修正函数返回类型注解\n")
                f.write("- 示例: `return cast(dict[str, Any], result)`\n\n")
            
            elif error_code == "type-arg":
                f.write("**修复策略**: 泛型类型参数缺失\n")
                f.write("- 为 dict 添加类型参数: `dict[str, Any]`\n")
                f.write("- 为 tuple 添加类型参数: `tuple[str, int]`\n")
                f.write("- 为 list 添加类型参数: `list[str]`\n\n")
            
            elif error_code == "call-arg":
                f.write("**修复策略**: 函数调用参数不匹配\n")
                f.write("- 检查函数签名是否正确\n")
                f.write("- 更新调用代码以匹配新的函数签名\n")
                f.write("- 可能需要重构代码以保持一致性\n\n")
            
            else:
                f.write("**修复策略**: 需要根据具体错误分析\n\n")


def main():
    backend_path = Path(__file__).parent.parent
    output_file = backend_path / 'document_delivery_errors.txt'
    report_file = backend_path / 'document_delivery_errors_analysis.md'
    
    if not output_file.exists():
        print(f"错误: 找不到文件 {output_file}")
        print("请先运行: mypy apps/automation/services/document_delivery/ --strict > document_delivery_errors.txt")
        return
    
    errors_by_type = parse_mypy_output(output_file)
    
    # 打印统计信息到控制台
    print_statistics(errors_by_type)
    
    # 生成 Markdown 报告
    generate_markdown_report(errors_by_type, report_file)
    print(f"\n详细报告已保存到: {report_file}")


if __name__ == '__main__':
    main()
