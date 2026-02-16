#!/usr/bin/env python3
"""批量修复name-defined错误"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 添加backend目录到Python路径
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_final_cleanup.backup_manager import BackupManager
from scripts.mypy_final_cleanup.error_analyzer import ErrorAnalyzer
from scripts.mypy_final_cleanup.import_fixer import ImportFixer
from scripts.mypy_final_cleanup.logger_config import setup_logger


def main() -> None:
    """主函数"""
    logger = setup_logger()

    logger.info("=" * 60)
    logger.info("开始批量修复name-defined错误")
    logger.info("=" * 60)

    # 1. 运行mypy生成错误报告
    logger.info("步骤1: 运行mypy生成错误报告...")
    import subprocess

    mypy_output_file = backend_path / "mypy_output.txt"

    # 检查是否已有mypy输出文件
    if mypy_output_file.exists():
        logger.info(f"使用已有的mypy输出文件: {mypy_output_file}")
    else:
        logger.info("运行mypy（这可能需要几分钟）...")
        result = subprocess.run(
            ["mypy", "apps/", "--strict"], cwd=backend_path, capture_output=True, text=True, timeout=300  # 5分钟超时
        )

        mypy_output_file.write_text(result.stdout + result.stderr, encoding="utf-8")
        logger.info(f"mypy输出已保存到: {mypy_output_file}")

    # 2. 解析错误
    logger.info("步骤2: 解析name-defined错误...")
    analyzer = ErrorAnalyzer()
    errors = analyzer.parse_mypy_output(str(mypy_output_file))

    name_defined_errors = analyzer.get_fixable_errors("name-defined", errors)
    logger.info(f"找到 {len(name_defined_errors)} 个name-defined错误")

    if not name_defined_errors:
        logger.info("没有name-defined错误需要修复")
        return

    # 3. 按文件分组
    logger.info("步骤3: 按文件分组错误...")
    errors_by_file: dict[str, list] = {}
    for error in name_defined_errors:
        if error.file_path not in errors_by_file:
            errors_by_file[error.file_path] = []
        errors_by_file[error.file_path].append(error)

    logger.info(f"涉及 {len(errors_by_file)} 个文件")

    # 4. 应用ImportFixer修复
    logger.info("步骤4: 应用ImportFixer修复...")
    backup_manager = BackupManager()
    fixer = ImportFixer(backup_manager)

    total_fixed = 0
    fixed_files = 0

    for file_path, file_errors in errors_by_file.items():
        logger.info(f"处理文件: {file_path} ({len(file_errors)}个错误)")

        try:
            fixes_count = fixer.fix_file(file_path)
            if fixes_count > 0:
                total_fixed += fixes_count
                fixed_files += 1
                logger.info(f"  ✓ 修复了 {fixes_count} 个导入")
            else:
                logger.info(f"  - 未检测到缺失的导入")
        except Exception as e:
            logger.error(f"  ✗ 修复失败: {e}")

    # 5. 验证修复结果（可选，跳过以节省时间）
    logger.info("步骤5: 跳过验证步骤（可手动运行mypy验证）")

    # 6. 生成报告
    logger.info("=" * 60)
    logger.info("修复完成")
    logger.info("=" * 60)
    logger.info(f"修复前: {len(name_defined_errors)} 个name-defined错误")
    logger.info(f"处理文件: {fixed_files} 个")
    logger.info(f"添加导入: {total_fixed} 个")
    logger.info("=" * 60)
    logger.info("请手动运行 mypy apps/ --strict 验证修复结果")

    # 列出备份文件
    backups = backup_manager.list_backups()
    if backups:
        logger.info(f"已备份 {len(backups)} 个文件到: {backup_manager.session_backup_dir}")
        logger.info("如需回滚，请运行: python scripts/mypy_final_cleanup/rollback.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
