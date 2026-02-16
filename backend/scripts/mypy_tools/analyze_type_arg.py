"""分析type-arg错误"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加backend目录到Python路径
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_tools.error_analyzer import ErrorAnalyzer
from scripts.mypy_tools.validation_system import ValidationSystem

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("开始分析type-arg错误...")
    
    # 运行mypy
    validator = ValidationSystem(backend_path)
    error_count, mypy_output = validator.run_mypy()
    
    if error_count < 0:
        logger.error("mypy运行失败")
        return
    
    logger.info(f"mypy检查完成，共 {error_count} 个错误")
    
    # 分析错误
    analyzer = ErrorAnalyzer()
    errors = analyzer.analyze(mypy_output)
    
    # 筛选type-arg错误
    type_arg_errors = [e for e in errors if e.error_code == 'type-arg']
    
    logger.info(f"找到 {len(type_arg_errors)} 个type-arg错误")
    
    # 按文件分组
    errors_by_file: dict[str, list] = {}
    for error in type_arg_errors:
        if error.file_path not in errors_by_file:
            errors_by_file[error.file_path] = []
        errors_by_file[error.file_path].append(error)
    
    # 生成报告
    report_path = backend_path / 'type_arg_errors.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# Type-Arg错误分析报告\n\n")
        f.write(f"总错误数: {len(type_arg_errors)}\n\n")
        f.write(f"涉及文件数: {len(errors_by_file)}\n\n")
        
        f.write("## 按文件分组\n\n")
        for file_path in sorted(errors_by_file.keys()):
            file_errors = errors_by_file[file_path]
            f.write(f"### {file_path} ({len(file_errors)}个错误)\n\n")
            for error in file_errors[:10]:  # 每个文件最多显示10个
                f.write(f"- 行{error.line}: {error.message}\n")
            if len(file_errors) > 10:
                f.write(f"- ... 还有 {len(file_errors) - 10} 个错误\n")
            f.write("\n")
    
    logger.info(f"报告已生成: {report_path}")


if __name__ == '__main__':
    main()
