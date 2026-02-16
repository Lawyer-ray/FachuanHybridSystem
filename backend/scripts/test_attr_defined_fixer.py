"""测试AttrDefinedFixer功能"""

from __future__ import annotations

import logging
from pathlib import Path

from mypy_tools.attr_defined_fixer import AttrDefinedFixer
from mypy_tools.error_analyzer import ErrorAnalyzer, ErrorRecord

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_attr_defined_fixer() -> None:
    """测试AttrDefinedFixer基本功能"""
    logger.info("=" * 60)
    logger.info("测试AttrDefinedFixer")
    logger.info("=" * 60)
    
    # 初始化fixer
    backend_path = Path(__file__).parent.parent
    fixer = AttrDefinedFixer(backend_path=backend_path)
    
    logger.info(f"加载了 {len(fixer._django_models)} 个Django Model")
    logger.info(f"示例Model: {list(fixer._django_models)[:10]}")
    
    # 创建测试错误记录
    test_errors = [
        ErrorRecord(
            file_path="apps/cases/models.py",
            line=100,
            column=10,
            error_code="attr-defined",
            message='"Case" has no attribute "id"',
            severity="critical",
            fixable=True,
            fix_pattern="attr-defined"
        ),
        ErrorRecord(
            file_path="apps/cases/models.py",
            line=101,
            column=10,
            error_code="attr-defined",
            message='"Case" has no attribute "pk"',
            severity="critical",
            fixable=True,
            fix_pattern="attr-defined"
        ),
        ErrorRecord(
            file_path="apps/cases/models.py",
            line=102,
            column=10,
            error_code="attr-defined",
            message='"Case" has no attribute "_private_method"',
            severity="critical",
            fixable=True,
            fix_pattern="attr-defined"
        ),
    ]
    
    # 测试can_fix方法
    logger.info("\n测试can_fix方法:")
    for error in test_errors:
        can_fix = fixer.can_fix(error)
        logger.info(f"  {error.message}: {can_fix}")
    
    logger.info("\n测试完成!")


def test_with_real_errors() -> None:
    """使用真实的mypy错误测试"""
    logger.info("=" * 60)
    logger.info("使用真实mypy错误测试")
    logger.info("=" * 60)
    
    backend_path = Path(__file__).parent.parent
    
    # 运行mypy获取错误
    import subprocess
    
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=60
    )
    
    mypy_output = result.stdout + result.stderr
    
    # 解析错误
    analyzer = ErrorAnalyzer()
    all_errors = analyzer.analyze(mypy_output)
    
    # 过滤attr-defined错误
    attr_errors = [e for e in all_errors if e.error_code == 'attr-defined']
    
    logger.info(f"总错误数: {len(all_errors)}")
    logger.info(f"attr-defined错误数: {len(attr_errors)}")
    
    # 按文件分组
    errors_by_file: dict[str, list[ErrorRecord]] = {}
    for error in attr_errors:
        if error.file_path not in errors_by_file:
            errors_by_file[error.file_path] = []
        errors_by_file[error.file_path].append(error)
    
    logger.info(f"涉及文件数: {len(errors_by_file)}")
    
    # 初始化fixer
    fixer = AttrDefinedFixer(backend_path=backend_path)
    
    # 统计可修复的错误
    fixable_count = 0
    for errors in errors_by_file.values():
        for error in errors:
            if fixer.can_fix(error):
                fixable_count += 1
    
    logger.info(f"可自动修复的错误数: {fixable_count}")
    logger.info(f"需要手动修复的错误数: {len(attr_errors) - fixable_count}")
    
    # 显示一些示例
    logger.info("\n可自动修复的错误示例:")
    count = 0
    for error in attr_errors:
        if fixer.can_fix(error) and count < 5:
            logger.info(f"  {error.file_path}:{error.line} - {error.message}")
            count += 1
    
    logger.info("\n需要手动修复的错误示例:")
    count = 0
    for error in attr_errors:
        if not fixer.can_fix(error) and count < 5:
            logger.info(f"  {error.file_path}:{error.line} - {error.message}")
            count += 1


if __name__ == '__main__':
    test_attr_defined_fixer()
    print()
    test_with_real_errors()
