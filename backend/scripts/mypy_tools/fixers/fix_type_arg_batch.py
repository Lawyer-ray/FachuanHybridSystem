"""批量修复type-arg错误"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# 添加backend目录到Python路径
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("开始批量修复type-arg错误...")
    
    # 运行mypy获取type-arg错误
    logger.info("运行mypy检查...")
    result = subprocess.run(
        ['mypy', 'apps/', '--strict', '--no-error-summary'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    output = result.stdout + result.stderr
    
    # 解析type-arg错误
    type_arg_errors: dict[str, list[tuple[int, str]]] = defaultdict(list)
    
    for line in output.split('\n'):
        if '[type-arg]' in line:
            # 解析行格式: file:line:col: error: message [type-arg]
            parts = line.split(':', 3)
            if len(parts) >= 3:
                file_path = parts[0].strip()
                try:
                    line_no = int(parts[1].strip())
                    message = parts[3] if len(parts) > 3 else ""
                    type_arg_errors[file_path].append((line_no, message))
                except (ValueError, IndexError):
                    continue
    
    logger.info(f"找到 {sum(len(v) for v in type_arg_errors.values())} 个type-arg错误")
    logger.info(f"涉及 {len(type_arg_errors)} 个文件")
    
    # 生成报告
    report_path = backend_path / 'type_arg_errors_report.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# Type-Arg错误分析报告\n\n")
        f.write(f"总错误数: {sum(len(v) for v in type_arg_errors.values())}\n\n")
        f.write(f"涉及文件数: {len(type_arg_errors)}\n\n")
        
        f.write("## 按文件分组\n\n")
        for file_path in sorted(type_arg_errors.keys()):
            errors = type_arg_errors[file_path]
            f.write(f"### {file_path} ({len(errors)}个错误)\n\n")
            for line_no, message in errors[:20]:  # 每个文件最多显示20个
                f.write(f"- 行{line_no}: {message}\n")
            if len(errors) > 20:
                f.write(f"- ... 还有 {len(errors) - 20} 个错误\n")
            f.write("\n")
    
    logger.info(f"报告已生成: {report_path}")
    
    # 统计最常见的类型
    logger.info("\n最常见的泛型类型:")
    type_counts: dict[str, int] = defaultdict(int)
    for errors in type_arg_errors.values():
        for _, message in errors:
            if 'generic type "dict"' in message.lower():
                type_counts['dict'] += 1
            elif 'generic type "list"' in message.lower():
                type_counts['list'] += 1
            elif 'generic type "set"' in message.lower():
                type_counts['set'] += 1
            elif 'generic type "tuple"' in message.lower():
                type_counts['tuple'] += 1
    
    for type_name, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {type_name}: {count}")


if __name__ == '__main__':
    main()
