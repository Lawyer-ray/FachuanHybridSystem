#!/usr/bin/env python3
"""分析 SMS 模块的 mypy 类型错误"""

import re
from collections import defaultdict
from pathlib import Path

def parse_mypy_output(output_file: str) -> list[dict]:
    """解析 mypy 输出"""
    errors = []
    with open(output_file, 'r', encoding='utf-8') as f:
        for line in f:
            # 匹配错误行格式: file:line:col: error: message [error-code]
            match = re.match(r'^(apps/automation/services/sms/[^:]+):(\d+):(\d+): error: (.+?) \[([^\]]+)\]', line)
            if match:
                file_path, line_num, col, message, error_code = match.groups()
                errors.append({
                    'file': file_path,
                    'line': int(line_num),
                    'col': int(col),
                    'message': message,
                    'error_code': error_code
                })
    return errors

def categorize_errors(errors: list[dict]) -> dict:
    """按错误类型分类"""
    by_code = defaultdict(list)
    by_file = defaultdict(list)
    
    for error in errors:
        by_code[error['error_code']].append(error)
        by_file[error['file']].append(error)
    
    return {
        'by_code': dict(by_code),
        'by_file': dict(by_file),
        'total': len(errors)
    }

def generate_report(categorized: dict) -> str:
    """生成分析报告"""
    lines = []
    lines.append("# SMS 模块 Mypy 类型错误分析报告\n")
    lines.append(f"**总错误数**: {categorized['total']}\n")
    
    # 按错误类型统计
    lines.append("## 按错误类型分类\n")
    sorted_codes = sorted(categorized['by_code'].items(), key=lambda x: len(x[1]), reverse=True)
    
    for error_code, error_list in sorted_codes:
        count = len(error_list)
        percentage = (count / categorized['total'] * 100) if categorized['total'] > 0 else 0
        lines.append(f"### {error_code} ({count} 个, {percentage:.1f}%)\n")
        
        # 显示前3个示例
        for i, error in enumerate(error_list[:3], 1):
            lines.append(f"{i}. `{error['file']}:{error['line']}`")
            lines.append(f"   - {error['message']}\n")
        
        if len(error_list) > 3:
            lines.append(f"   ... 还有 {len(error_list) - 3} 个类似错误\n")
        lines.append("")
    
    # 按文件统计
    lines.append("## 按文件分类\n")
    sorted_files = sorted(categorized['by_file'].items(), key=lambda x: len(x[1]), reverse=True)
    
    lines.append("| 文件 | 错误数 |")
    lines.append("|------|--------|")
    for file_path, error_list in sorted_files[:20]:  # 只显示前20个
        file_name = Path(file_path).name
        lines.append(f"| {file_name} | {len(error_list)} |")
    
    if len(sorted_files) > 20:
        lines.append(f"| ... 还有 {len(sorted_files) - 20} 个文件 | ... |")
    
    lines.append("")
    
    # 错误类型说明
    lines.append("## 错误类型说明\n")
    lines.append("- **attr-defined**: 属性不存在（模型字段缺失或类型存根问题）")
    lines.append("- **no-any-return**: 函数返回 Any 类型但声明了具体类型")
    lines.append("- **assignment**: 类型不兼容的赋值")
    lines.append("- **arg-type**: 参数类型不匹配")
    lines.append("- **type-arg**: 缺少泛型类型参数")
    lines.append("- **no-untyped-def**: 函数缺少类型注解")
    lines.append("- **name-defined**: 名称未定义")
    lines.append("- **misc**: 其他类型错误")
    lines.append("")
    
    return "\n".join(lines)

def main():
    output_file = "sms_only_errors.txt"
    
    # 解析错误
    errors = parse_mypy_output(output_file)
    
    if not errors:
        print("未找到 SMS 模块的类型错误")
        return
    
    # 分类统计
    categorized = categorize_errors(errors)
    
    # 生成报告
    report = generate_report(categorized)
    
    # 保存报告
    report_file = "sms_errors_analysis.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"分析完成！")
    print(f"- 总错误数: {categorized['total']}")
    print(f"- 错误类型数: {len(categorized['by_code'])}")
    print(f"- 涉及文件数: {len(categorized['by_file'])}")
    print(f"- 报告已保存到: {report_file}")

if __name__ == "__main__":
    main()
