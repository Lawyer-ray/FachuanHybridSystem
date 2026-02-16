"""回滚P0修复脚本"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

# 添加backend到路径
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_final_cleanup.logger_config import setup_logger

logger = setup_logger(__name__)


def find_latest_backup() -> Path | None:
    """查找最新的备份目录"""
    backup_root = backend_path / ".mypy_final_cleanup_backups"

    if not backup_root.exists():
        logger.error("备份目录不存在")
        return None

    # 获取所有备份目录，按时间排序
    backup_dirs = sorted([d for d in backup_root.iterdir() if d.is_dir()], reverse=True)

    if not backup_dirs:
        logger.error("没有找到备份")
        return None

    return backup_dirs[0]


def count_backup_files(backup_dir: Path) -> int:
    """统计备份文件数量"""
    count = 0
    for item in backup_dir.rglob("*"):
        if item.is_file():
            count += 1
    return count


def restore_from_backup(backup_dir: Path) -> int:
    """从备份恢复文件"""
    restored = 0

    # 遍历备份目录中的所有文件
    for backup_file in backup_dir.rglob("*"):
        if not backup_file.is_file():
            continue

        # 计算相对路径
        rel_path = backup_file.relative_to(backup_dir)

        # 目标文件路径
        target_file = backend_path / rel_path

        try:
            # 确保目标目录存在
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件
            shutil.copy2(backup_file, target_file)
            restored += 1
            logger.info(f"已恢复: {rel_path}")

        except Exception as e:
            logger.error(f"恢复失败 {rel_path}: {e}")

    return restored


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("回滚P0修复")
    logger.info("=" * 80)

    # 查找最新备份
    backup_dir = find_latest_backup()
    if not backup_dir:
        logger.error("无法找到备份目录")
        return

    logger.info(f"找到备份: {backup_dir.name}")

    # 统计备份文件
    file_count = count_backup_files(backup_dir)
    logger.info(f"备份包含 {file_count} 个文件")

    # 确认回滚
    print(f"\n将从备份 {backup_dir.name} 恢复 {file_count} 个文件")
    response = input("确认回滚？(yes/no): ")

    if response.lower() != "yes":
        logger.info("取消回滚")
        return

    # 执行回滚
    logger.info("开始回滚...")
    restored = restore_from_backup(backup_dir)

    logger.info(f"\n✅ 回滚完成: 恢复了 {restored} 个文件")
    logger.info("建议：运行 mypy --strict apps/ 验证错误数")


if __name__ == "__main__":
    main()
