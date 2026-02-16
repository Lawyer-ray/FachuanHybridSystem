"""演示AttrDefinedFixer功能"""

from __future__ import annotations

import logging
from pathlib import Path

from mypy_tools.attr_defined_fixer import AttrDefinedFixer
from mypy_tools.error_analyzer import ErrorRecord

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")

logger = logging.getLogger(__name__)


def main() -> None:
    """演示AttrDefinedFixer功能"""
    logger.info("=" * 60)
    logger.info("AttrDefinedFixer 功能演示")
    logger.info("=" * 60)

    # 初始化fixer
    backend_path = Path(__file__).parent.parent
    fixer = AttrDefinedFixer(backend_path=backend_path)

    logger.info(f"\n加载了 {len(fixer._django_models)} 个Django Model")
    logger.info(f"示例Model: {sorted(list(fixer._django_models))[:15]}")

    # 创建测试错误记录
    test_cases = [
        {
            "error": ErrorRecord(
                file_path="apps/cases/models.py",
                line=100,
                column=10,
                error_code="attr-defined",
                message='"Case" has no attribute "id"',
                severity="critical",
                fixable=True,
                fix_pattern="attr-defined",
            ),
            "description": "Django Model id 属性",
        },
        {
            "error": ErrorRecord(
                file_path="apps/cases/models.py",
                line=101,
                column=10,
                error_code="attr-defined",
                message='"Case" has no attribute "pk"',
                severity="critical",
                fixable=True,
                fix_pattern="attr-defined",
            ),
            "description": "Django Model pk 属性",
        },
        {
            "error": ErrorRecord(
                file_path="apps/cases/models.py",
                line=102,
                column=10,
                error_code="attr-defined",
                message='"Case" has no attribute "objects"',
                severity="critical",
                fixable=True,
                fix_pattern="attr-defined",
            ),
            "description": "Django Model objects 管理器",
        },
        {
            "error": ErrorRecord(
                file_path="apps/cases/models.py",
                line=103,
                column=10,
                error_code="attr-defined",
                message='"Case" has no attribute "_private_method"',
                severity="critical",
                fixable=True,
                fix_pattern="attr-defined",
            ),
            "description": "私有方法（应该手动修复）",
        },
        {
            "error": ErrorRecord(
                file_path="apps/cases/models.py",
                line=104,
                column=10,
                error_code="attr-defined",
                message='"UnknownClass" has no attribute "id"',
                severity="critical",
                fixable=True,
                fix_pattern="attr-defined",
            ),
            "description": "未知类（应该手动修复）",
        },
        {
            "error": ErrorRecord(
                file_path="apps/cases/models.py",
                line=105,
                column=10,
                error_code="attr-defined",
                message='"Case" has no attribute "unknown_attr"; maybe "name"?',
                severity="critical",
                fixable=True,
                fix_pattern="attr-defined",
            ),
            "description": "mypy建议的属性（应该手动修复）",
        },
    ]

    # 测试can_fix方法
    logger.info("\n" + "=" * 60)
    logger.info("测试 can_fix() 方法:")
    logger.info("=" * 60)

    for test_case in test_cases:
        error = test_case["error"]
        description = test_case["description"]
        can_fix = fixer.can_fix(error)

        status = "✓ 可自动修复" if can_fix else "✗ 需手动修复"
        logger.info(f"\n{status}")
        logger.info(f"  描述: {description}")
        logger.info(f"  错误: {error.message}")

    # 统计
    fixable_count = sum(1 for tc in test_cases if fixer.can_fix(tc["error"]))
    logger.info("\n" + "=" * 60)
    logger.info(f"统计: {fixable_count}/{len(test_cases)} 个错误可自动修复")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
