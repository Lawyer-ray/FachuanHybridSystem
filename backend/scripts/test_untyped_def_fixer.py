"""测试UntypedDefFixer修复器"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加scripts目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from mypy_tools.error_analyzer import ErrorAnalyzer, ErrorRecord
from mypy_tools.untyped_def_fixer import UntypedDefFixer
from mypy_tools.validation_system import ValidationSystem

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    logger.info("=" * 60)
    logger.info("测试 UntypedDefFixer")
    logger.info("=" * 60)
    
    # 初始化组件
    backend_path = Path(__file__).parent.parent
    analyzer = ErrorAnalyzer()
    fixer = UntypedDefFixer(backend_path=backend_path)
    validator = ValidationSystem(backend_path=backend_path)
    
    # 运行mypy获取当前错误
    logger.info("\n步骤1: 运行mypy检查获取no-untyped-def错误...")
    error_count, mypy_output = validator.run_mypy()
    
    if error_count < 0:
        logger.error("mypy运行失败")
        return
    
    logger.info(f"发现 {error_count} 个错误")
    
    # 解析错误
    logger.info("\n步骤2: 解析mypy输出...")
    all_errors = analyzer.analyze(mypy_output)
    
    # 过滤no-untyped-def错误
    untyped_def_errors = [e for e in all_errors if e.error_code == 'no-untyped-def']
    logger.info(f"发现 {len(untyped_def_errors)} 个no-untyped-def错误")
    
    if not untyped_def_errors:
        logger.info("没有no-untyped-def错误需要修复")
        return
    
    # 显示前10个错误
    logger.info("\n前10个no-untyped-def错误:")
    for i, error in enumerate(untyped_def_errors[:10], 1):
        logger.info(f"{i}. {error.file_path}:{error.line} - {error.message}")
    
    # 按文件分组
    logger.info("\n步骤3: 按文件分组错误...")
    errors_by_file: dict[str, list[ErrorRecord]] = {}
    for error in untyped_def_errors:
        if error.file_path not in errors_by_file:
            errors_by_file[error.file_path] = []
        errors_by_file[error.file_path].append(error)
    
    logger.info(f"涉及 {len(errors_by_file)} 个文件")
    
    # 统计可修复的错误
    logger.info("\n步骤4: 统计可修复的错误...")
    fixable_count = sum(1 for e in untyped_def_errors if fixer.can_fix(e))
    logger.info(f"可自动修复: {fixable_count} 个")
    logger.info(f"需要手动修复: {len(untyped_def_errors) - fixable_count} 个")
    
    # 显示需要手动修复的错误示例
    manual_errors = [e for e in untyped_def_errors if not fixer.can_fix(e)]
    if manual_errors:
        logger.info("\n需要手动修复的错误示例（前5个）:")
        for i, error in enumerate(manual_errors[:5], 1):
            logger.info(f"{i}. {error.file_path}:{error.line} - {error.message}")
    
    # 询问是否执行修复
    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)
    logger.info(f"总计: {len(untyped_def_errors)} 个no-untyped-def错误")
    logger.info(f"可自动修复: {fixable_count} 个")
    logger.info(f"需要手动修复: {len(untyped_def_errors) - fixable_count} 个")
    logger.info("\n注意: 此脚本仅用于测试，不会实际修复文件")


if __name__ == '__main__':
    main()
