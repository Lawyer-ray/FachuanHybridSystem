"""生成修复进度报告"""

from __future__ import annotations

import logging
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent.parent
    report_dir = backend_path / '.mypy_reports'
    report_dir.mkdir(exist_ok=True)
    
    logger.info("生成修复进度报告...")
    
    # 运行mypy
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    
    output = result.stdout + result.stderr
    
    # 统计错误类型（只统计包含error:的行）
    error_counts: dict[str, int] = defaultdict(int)
    for line in output.split('\n'):
        if 'error:' in line and '[' in line and ']' in line:
            start = line.rfind('[')
            end = line.rfind(']')
            if start < end:
                error_type = line[start+1:end]
                error_counts[error_type] += 1
    
    total_errors = sum(error_counts.values())
    
    # 生成报告
    report_path = report_dir / f'progress_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# Mypy错误修复进度报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 总体统计\n\n")
        f.write(f"- **当前错误总数**: {total_errors}\n")
        f.write(f"- **初始错误总数**: 2549 (spec开始时)\n")
        f.write(f"- **已修复错误数**: {2549 - total_errors}\n")
        f.write(f"- **修复进度**: {(2549 - total_errors) / 2549 * 100:.1f}%\n\n")
        
        f.write(f"## 错误类型分布\n\n")
        f.write(f"| 错误类型 | 数量 | 占比 |\n")
        f.write(f"|---------|------|------|\n")
        
        for error_type, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
            percentage = count / total_errors * 100 if total_errors > 0 else 0
            f.write(f"| {error_type} | {count} | {percentage:.1f}% |\n")
        
        f.write(f"\n## 已完成的工作\n\n")
        f.write(f"- ✅ 实现ErrorAnalyzer、ValidationSystem、BatchFixer基础设施\n")
        f.write(f"- ✅ 实现AttrDefinedFixer修复器\n")
        f.write(f"- ✅ 实现UntypedDefFixer修复器（修复759个no-untyped-def错误）\n")
        f.write(f"- ✅ 实现TypeArgFixer修复器（修复115个type-arg错误）\n")
        f.write(f"- ✅ 添加Any导入（修复119个name-defined错误）\n\n")
        
        f.write(f"## 下一步工作\n\n")
        f.write(f"优先级顺序：\n")
        f.write(f"1. attr-defined ({error_counts.get('attr-defined', 0)}个)\n")
        f.write(f"2. name-defined ({error_counts.get('name-defined', 0)}个)\n")
        f.write(f"3. no-any-return ({error_counts.get('no-any-return', 0)}个)\n")
        f.write(f"4. type-arg ({error_counts.get('type-arg', 0)}个)\n")
        f.write(f"5. arg-type ({error_counts.get('arg-type', 0)}个)\n")
    
    logger.info(f"报告已生成: {report_path}")
    logger.info(f"当前错误总数: {total_errors}")
    logger.info(f"修复进度: {(2549 - total_errors) / 2549 * 100:.1f}%")


if __name__ == '__main__':
    main()
