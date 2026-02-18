"""演示NoAnyReturnFixer的使用"""

from __future__ import annotations

import logging
from pathlib import Path

from mypy_tools.error_analyzer import ErrorAnalyzer, ErrorRecord
from mypy_tools.no_any_return_fixer import NoAnyReturnFixer

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def demo_basic_usage() -> None:
    """演示基本使用"""
    logger.info("=== 演示NoAnyReturnFixer基本使用 ===")

    # 创建fixer
    backend_path = Path(__file__).parent.parent
    fixer = NoAnyReturnFixer(backend_path=backend_path)

    # 模拟一些no-any-return错误
    errors = [
        ErrorRecord(
            file_path="apps/cases/services/case_service.py",
            line=100,
            column=0,
            error_code="no-any-return",
            message='Returning Any from function declared to return "Any"',
            severity="medium",
            fixable=False,
            fix_pattern=None,
        ),
        ErrorRecord(
            file_path="apps/cases/services/case_service.py",
            line=150,
            column=0,
            error_code="no-any-return",
            message="Returning Any from function with Protocol",
            severity="medium",
            fixable=False,
            fix_pattern=None,
        ),
    ]

    # 检查哪些错误可以修复
    for error in errors:
        can_fix = fixer.can_fix(error)
        logger.info(f"错误 {error.line}: {error.message}")
        logger.info(f"  可以自动修复: {can_fix}")

    logger.info("\n演示完成！")


def demo_batch_fix() -> None:
    """演示批量修复"""
    logger.info("\n=== 演示批量修复no-any-return错误 ===")

    backend_path = Path(__file__).parent.parent
    fixer = NoAnyReturnFixer(backend_path=backend_path)

    # 模拟按文件分组的错误
    errors_by_file = {
        "apps/cases/services/case_service.py": [
            ErrorRecord(
                "apps/cases/services/case_service.py", 100, 0, "no-any-return", "Returning Any", "medium", False, None
            ),
            ErrorRecord(
                "apps/cases/services/case_service.py", 150, 0, "no-any-return", "Returning Any", "medium", False, None
            ),
        ],
        "apps/contracts/services/contract_service.py": [
            ErrorRecord(
                "apps/contracts/services/contract_service.py",
                200,
                0,
                "no-any-return",
                "Returning Any",
                "medium",
                False,
                None,
            ),
        ],
    }

    logger.info(f"准备修复 {len(errors_by_file)} 个文件")

    # 注意：这里只是演示，不会真正修复文件
    # 实际使用时调用: report = fixer.batch_fix(errors_by_file)

    logger.info("批量修复演示完成！")


def demo_type_inference() -> None:
    """演示类型推断能力"""
    logger.info("\n=== 演示类型推断能力 ===")

    examples = [
        ("return 42", "推断为 int"),
        ("return 'hello'", "推断为 str"),
        ("return True", "推断为 bool"),
        ("return None", "推断为 None"),
        ("return [1, 2, 3]", "推断为 list[int]"),
        ("return {'key': 'value'}", "推断为 dict[str, str]"),
        ("return {1, 2, 3}", "推断为 set[int]"),
        ("return 42 if flag else 'hello'", "推断为 int | str (Union)"),
        ("return 42 if flag else None", "推断为 int | None (Optional)"),
    ]

    logger.info("NoAnyReturnFixer可以推断以下类型:")
    for code, description in examples:
        logger.info(f"  {code:40} -> {description}")

    logger.info("\n类型推断演示完成！")


if __name__ == "__main__":
    demo_basic_usage()
    demo_batch_fix()
    demo_type_inference()

    logger.info("\n" + "=" * 60)
    logger.info("所有演示完成！")
    logger.info("=" * 60)
