"""测试BatchFixer基类功能"""

from __future__ import annotations

import logging
from pathlib import Path

# 直接导入
from mypy_tools import BatchFixer, ErrorRecord, FixResult

# backend路径
backend_path = Path(__file__).parent.parent

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestFixer(BatchFixer):
    """测试用的修复器实现"""

    def can_fix(self, error: ErrorRecord) -> bool:
        """测试：只修复type-arg错误"""
        return error.error_code == "type-arg"

    def fix_file(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        """测试：模拟修复文件"""
        logger.info(f"模拟修复文件: {file_path}，错误数: {len(errors)}")

        # 模拟成功修复
        return FixResult(
            file_path=file_path,
            errors_fixed=len(errors),
            errors_remaining=0,
            fix_pattern=self.fix_pattern,
            success=True,
            error_message=None,
        )


def test_batch_fixer() -> None:
    """测试BatchFixer基类功能"""
    logger.info("开始测试BatchFixer...")

    # 创建测试修复器
    fixer = TestFixer(fix_pattern="test_pattern", backend_path=backend_path)

    # 测试1: AST解析
    logger.info("\n测试1: AST解析")
    test_file = backend_path / "scripts" / "mypy_tools" / "batch_fixer.py"
    tree = fixer.parse_ast(test_file)
    if tree:
        logger.info(f"✓ AST解析成功: {test_file.name}")
    else:
        logger.error(f"✗ AST解析失败: {test_file.name}")

    # 测试2: 文件备份和恢复
    logger.info("\n测试2: 文件备份和恢复")
    test_file_path = "scripts/mypy_tools/batch_fixer.py"
    backup_path = fixer.backup_file(test_file_path)
    if backup_path and backup_path.exists():
        logger.info(f"✓ 文件备份成功: {backup_path}")

        # 测试恢复
        if fixer.restore_file(test_file_path):
            logger.info(f"✓ 文件恢复成功")
        else:
            logger.error(f"✗ 文件恢复失败")
    else:
        logger.error(f"✗ 文件备份失败")

    # 测试3: can_fix方法
    logger.info("\n测试3: can_fix方法")
    error1 = ErrorRecord(
        file_path="test.py",
        line=1,
        column=1,
        error_code="type-arg",
        message="Missing type parameters",
        severity="medium",
        fixable=True,
        fix_pattern="add_generic_params",
    )
    error2 = ErrorRecord(
        file_path="test.py",
        line=2,
        column=1,
        error_code="attr-defined",
        message="Attribute not defined",
        severity="critical",
        fixable=False,
        fix_pattern=None,
    )

    if fixer.can_fix(error1):
        logger.info(f"✓ 正确识别可修复错误: {error1.error_code}")
    else:
        logger.error(f"✗ 未能识别可修复错误: {error1.error_code}")

    if not fixer.can_fix(error2):
        logger.info(f"✓ 正确识别不可修复错误: {error2.error_code}")
    else:
        logger.error(f"✗ 错误识别为可修复: {error2.error_code}")

    # 测试4: 批量修复
    logger.info("\n测试4: 批量修复")
    errors_by_file = {
        "test1.py": [error1],
        "test2.py": [error2],
        "test3.py": [error1, error1],
    }

    report = fixer.batch_fix(errors_by_file)
    logger.info(f"修复报告:")
    logger.info(f"  总文件数: {report.total_files}")
    logger.info(f"  修改的文件数: {len(report.files_modified)}")
    logger.info(f"  修复的错误数: {report.total_errors_fixed}")
    logger.info(f"  失败的文件数: {len(report.failed_files)}")

    # 测试5: 生成报告
    logger.info("\n测试5: 生成报告")
    report_text = fixer.generate_report(report)
    logger.info(f"生成的报告:\n{report_text}")

    logger.info("\n所有测试完成！")


if __name__ == "__main__":
    test_batch_fixer()
