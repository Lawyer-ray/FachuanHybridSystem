#!/usr/bin/env python3
"""批量修复Django Model动态属性的attr-defined错误"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

# 添加backend目录到Python路径
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_tools.attr_defined_fixer import AttrDefinedFixer
from scripts.mypy_tools.error_analyzer import ErrorAnalyzer, ErrorRecord
from scripts.mypy_tools.validation_system import ValidationSystem

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def extract_errors_from_file(errors_file: Path) -> list[ErrorRecord]:
    """从错误文件中提取ErrorRecord列表"""
    errors: list[ErrorRecord] = []

    with open(errors_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # 解析错误行: file:line:col: error: message [attr-defined]
            match = re.match(r"^([^:]+):(\d+):(\d+):\s+error:\s+(.+?)\s+\[attr-defined\]", line)

            if match:
                file_path, line_num, col, message = match.groups()

                error = ErrorRecord(
                    file_path=file_path,
                    line=int(line_num),
                    column=int(col),
                    error_code="attr-defined",
                    message=message,
                    severity="critical",
                    fixable=True,
                    fix_pattern="attr-defined",
                )
                errors.append(error)

    return errors


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("开始批量修复Django Model动态属性")
    logger.info("=" * 80)

    # 读取错误列表
    errors_file = backend_path / "attr_defined_errors.txt"
    if not errors_file.exists():
        logger.error(f"错误文件不存在: {errors_file}")
        return

    errors = extract_errors_from_file(errors_file)
    logger.info(f"从文件中提取了 {len(errors)} 个错误")

    # 过滤Django Model相关错误
    django_attrs = {"id", "pk", "objects", "DoesNotExist", "MultipleObjectsReturned"}
    django_errors = [e for e in errors if any(f'has no attribute "{attr}"' in e.message for attr in django_attrs)]

    logger.info(f"识别出 {len(django_errors)} 个Django Model动态属性错误")

    if not django_errors:
        logger.info("没有需要修复的Django Model错误")
        return

    # 按文件分组
    by_file: dict[str, list[ErrorRecord]] = {}
    for error in django_errors:
        if error.file_path not in by_file:
            by_file[error.file_path] = []
        by_file[error.file_path].append(error)

    logger.info(f"涉及 {len(by_file)} 个文件")

    # 初始化修复器
    fixer = AttrDefinedFixer(backend_path)

    # 统计
    total_fixed = 0
    total_failed = 0
    fixed_files = []
    failed_files = []

    # 逐文件修复
    for file_path, file_errors in by_file.items():
        logger.info(f"\n处理文件: {file_path} ({len(file_errors)} 个错误)")

        # 备份文件
        full_path = backend_path / file_path
        if not full_path.exists():
            logger.warning(f"文件不存在，跳过: {file_path}")
            continue

        fixer.backup_file(full_path)

        try:
            # 修复文件
            result = fixer.fix_file(file_path, file_errors)

            if result.success and result.errors_fixed > 0:
                logger.info(f"✓ 成功修复 {result.errors_fixed} 个错误")
                total_fixed += result.errors_fixed
                fixed_files.append(file_path)
            elif result.success:
                logger.info(f"○ 文件无需修复或无法自动修复")
            else:
                logger.warning(f"✗ 修复失败: {result.error_message}")
                total_failed += len(file_errors)
                failed_files.append(file_path)
                # 恢复备份
                backup_path = full_path.with_suffix(full_path.suffix + ".bak")
                if backup_path.exists():
                    fixer.restore_file(backup_path, full_path)

        except Exception as e:
            logger.error(f"✗ 处理文件时发生异常: {e}")
            total_failed += len(file_errors)
            failed_files.append(file_path)
            # 恢复备份
            backup_path = full_path.with_suffix(full_path.suffix + ".bak")
            if backup_path.exists():
                fixer.restore_file(backup_path, full_path)

    # 输出统计
    logger.info("\n" + "=" * 80)
    logger.info("修复统计")
    logger.info("=" * 80)
    logger.info(f"总错误数: {len(django_errors)}")
    logger.info(f"成功修复: {total_fixed}")
    logger.info(f"修复失败: {total_failed}")
    logger.info(f"修复文件数: {len(fixed_files)}")
    logger.info(f"失败文件数: {len(failed_files)}")

    if fixed_files:
        logger.info(f"\n成功修复的文件 (前20个):")
        for file_path in fixed_files[:20]:
            logger.info(f"  {file_path}")
        if len(fixed_files) > 20:
            logger.info(f"  ... 还有 {len(fixed_files) - 20} 个文件")

    if failed_files:
        logger.info(f"\n修复失败的文件:")
        for file_path in failed_files:
            logger.info(f"  {file_path}")

    # 验证修复效果
    logger.info("\n" + "=" * 80)
    logger.info("验证修复效果")
    logger.info("=" * 80)

    validation_system = ValidationSystem(backend_path)
    error_count, mypy_output = validation_system.run_mypy()

    if error_count >= 0:
        logger.info(f"修复后剩余错误数: {error_count}")

        # 统计attr-defined错误
        attr_defined_count = mypy_output.count("[attr-defined]")
        logger.info(f"修复后attr-defined错误数: {attr_defined_count}")
        logger.info(f"减少了 {len(errors) - attr_defined_count} 个attr-defined错误")

    logger.info("\n" + "=" * 80)
    logger.info("修复完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
