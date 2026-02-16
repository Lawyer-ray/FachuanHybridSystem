"""分析no-any-return错误并生成报告"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from collections import defaultdict

from mypy_tools.error_analyzer import ErrorRecord

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def parse_mypy_errors(mypy_output: str) -> list[ErrorRecord]:
    """
    解析mypy输出，提取no-any-return错误
    
    mypy输出格式:
    file.py:line:col: error: message [error-code]
        code snippet
        ^~~~
    """
    errors = []
    
    # 匹配错误行的正则表达式 - 只匹配以 apps/ 开头的文件路径
    error_pattern = re.compile(
        r'(apps/[^:]+):(\d+):(\d+):\s+error:\s+(.+?)\s+\[no-any-return\]',
        re.MULTILINE
    )
    
    for match in error_pattern.finditer(mypy_output):
        file_path = match.group(1)
        line = int(match.group(2))
        column = int(match.group(3))
        message = match.group(4)
        
        error = ErrorRecord(
            file_path=file_path,
            line=line,
            column=column,
            error_code='no-any-return',
            message=message,
            severity='medium',
            fixable=False,
            fix_pattern=None
        )
        errors.append(error)
    
    return errors


def analyze_no_any_return_errors() -> None:
    """分析no-any-return错误"""
    logger.info("=== 开始分析no-any-return错误 ===")
    
    # 读取mypy输出
    mypy_output_file = Path(__file__).parent.parent / 'mypy_full_output.txt'
    
    if not mypy_output_file.exists():
        logger.error(f"mypy输出文件不存在: {mypy_output_file}")
        return
    
    mypy_output = mypy_output_file.read_text(encoding='utf-8')
    
    # 解析no-any-return错误
    no_any_return_errors = parse_mypy_errors(mypy_output)
    
    logger.info(f"no-any-return错误数: {len(no_any_return_errors)}")
    
    # 按文件分组
    errors_by_file: dict[str, list[ErrorRecord]] = defaultdict(list)
    for error in no_any_return_errors:
        errors_by_file[error.file_path].append(error)
    
    # 按模块分组
    errors_by_module: dict[str, list[ErrorRecord]] = defaultdict(list)
    for error in no_any_return_errors:
        module = _get_module_from_file(error.file_path)
        errors_by_module[module].append(error)
    
    # 按函数复杂度分类
    simple_errors, complex_errors_list = categorize_by_complexity(no_any_return_errors)
    
    # 生成报告
    generate_report(
        no_any_return_errors,
        dict(errors_by_file),
        dict(errors_by_module),
        simple_errors,
        complex_errors_list
    )
    
    logger.info("=== 分析完成 ===")


def _get_module_from_file(file_path: str) -> str:
    """从文件路径提取模块名"""
    if file_path.startswith('apps/'):
        parts = file_path.split('/')
        if len(parts) >= 2:
            return parts[1]
    return 'other'


def categorize_by_complexity(
    errors: list[ErrorRecord]
) -> tuple[list[ErrorRecord], list[ErrorRecord]]:
    """
    按函数复杂度分类
    
    简单：可以自动推断返回类型的函数
    复杂：需要手动处理的函数（Protocol、Callable、Generic等）
    
    Returns:
        (简单错误列表, 复杂错误列表)
    """
    simple = []
    complex_errors_list = []
    complex_patterns = ['Protocol', 'Callable', 'Generic', 'overload', 'TypeVar']
    
    for error in errors:
        is_complex = any(pattern in error.message for pattern in complex_patterns)
        
        if is_complex:
            complex_errors_list.append(error)
        else:
            simple.append(error)
    
    logger.info(f"简单错误: {len(simple)}, 复杂错误: {len(complex_errors_list)}")
    
    return simple, complex_errors_list


def generate_report(
    all_errors: list[ErrorRecord],
    errors_by_file: dict[str, list[ErrorRecord]],
    errors_by_module: dict[str, list[ErrorRecord]],
    simple_errors: list[ErrorRecord],
    complex_errors_list: list[ErrorRecord]
) -> None:
    """生成分析报告"""
    
    report_file = Path(__file__).parent.parent / 'no_any_return_analysis.txt'
    
    with report_file.open('w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("no-any-return 错误分析报告\n")
        f.write("=" * 80 + "\n\n")
        
        # 总体统计
        f.write("## 总体统计\n\n")
        f.write(f"总错误数: {len(all_errors)}\n")
        f.write(f"简单错误（可自动修复）: {len(simple_errors)}\n")
        f.write(f"复杂错误（需手动处理）: {len(complex_errors_list)}\n\n")
        
        # 按模块统计
        f.write("## 按模块统计\n\n")
        sorted_modules = sorted(
            errors_by_module.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        for module, errors in sorted_modules:
            f.write(f"{module}: {len(errors)} 个错误\n")
        
        f.write("\n")
        
        # 按文件详细列表
        f.write("## 按文件详细列表\n\n")
        
        sorted_files = sorted(
            errors_by_file.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        for file_path, errors in sorted_files:
            f.write(f"\n### {file_path} ({len(errors)} 个错误)\n\n")
            
            # 按行号排序
            sorted_errors = sorted(errors, key=lambda e: e.line)
            
            for error in sorted_errors:
                complexity = "简单" if error in simple_errors else "复杂"
                f.write(f"  行 {error.line}: {error.message} [{complexity}]\n")
        
        f.write("\n")
        
        # 复杂错误详情
        if complex_errors_list:
            f.write("## 复杂错误详情（需手动处理）\n\n")
            
            for error in complex_errors_list:
                f.write(f"{error.file_path}:{error.line}\n")
                f.write(f"  消息: {error.message}\n\n")
    
    logger.info(f"报告已生成: {report_file}")
    
    # 同时输出到控制台
    print("\n" + "=" * 80)
    print("no-any-return 错误分析报告")
    print("=" * 80)
    print(f"\n总错误数: {len(all_errors)}")
    print(f"简单错误（可自动修复）: {len(simple_errors)}")
    print(f"复杂错误（需手动处理）: {len(complex_errors_list)}")
    print(f"\n按模块统计（前10）:")
    
    for module, errors in sorted_modules[:10]:
        print(f"  {module}: {len(errors)} 个错误")
    
    print(f"\n详细报告已保存到: {report_file}")


if __name__ == '__main__':
    analyze_no_any_return_errors()
