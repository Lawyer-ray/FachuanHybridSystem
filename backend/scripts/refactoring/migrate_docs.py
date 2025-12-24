#!/usr/bin/env python3
"""
文档迁移脚本

将文档文件移动到 docs/ 目录的相应子目录中
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.refactoring.migrate_structure import (
    StructureMigrator,
    MoveFileMigration,
    CreateDirectoryMigration
)


def migrate_documentation(dry_run: bool = True):
    """
    迁移文档文件
    
    Args:
        dry_run: 是否为 dry-run 模式
    """
    root_path = Path(__file__).resolve().parent.parent.parent
    migrator = StructureMigrator(root_path)
    
    print("=" * 80)
    print("文档迁移脚本")
    print("=" * 80)
    print(f"模式: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"根目录: {root_path}")
    print("=" * 80)
    print()
    
    # 确保目标目录存在
    docs_subdirs = [
        "docs/api",
        "docs/architecture",
        "docs/guides",
        "docs/operations",
        "docs/quality"
    ]
    
    for subdir in docs_subdirs:
        migrator.add_migration(
            CreateDirectoryMigration(root_path / subdir)
        )
    
    # 定义文档迁移映射
    doc_migrations = [
        # 从根目录迁移
        ("CODE_QUALITY_REVIEW.md", "docs/quality/CODE_QUALITY_REVIEW.md"),
        ("DATA_RECOVERY_GUIDE.md", "docs/operations/DATA_RECOVERY_GUIDE.md"),
        ("PERFORMANCE_MONITORING_IMPLEMENTATION.md", "docs/operations/PERFORMANCE_MONITORING_IMPLEMENTATION.md"),
        ("QUICK_START.md", "docs/guides/QUICK_START.md"),
        
        # 从 docs/ 根目录迁移
        ("docs/API.md", "docs/api/API.md"),
        ("docs/ARCHITECTURE_TRAINING.md", "docs/architecture/ARCHITECTURE_TRAINING.md"),
        ("docs/REFACTORING_BEST_PRACTICES.md", "docs/architecture/REFACTORING_BEST_PRACTICES.md"),
        ("docs/CODE_REVIEW_CHECKLIST.md", "docs/guides/CODE_REVIEW_CHECKLIST.md"),
        ("docs/CODE_REVIEW_PROCESS.md", "docs/guides/CODE_REVIEW_PROCESS.md"),
        ("docs/TEAM_KNOWLEDGE_SHARING.md", "docs/guides/TEAM_KNOWLEDGE_SHARING.md"),
    ]
    
    # 添加文件移动迁移
    for source_rel, dest_rel in doc_migrations:
        source = root_path / source_rel
        destination = root_path / dest_rel
        
        if source.exists():
            migrator.add_migration(
                MoveFileMigration(source, destination)
            )
        else:
            print(f"⚠️  源文件不存在，跳过: {source_rel}")
    
    # 执行迁移
    print("\n开始迁移...")
    print("-" * 80)
    migrator.execute(dry_run=dry_run)
    print("-" * 80)
    
    if dry_run:
        print("\n✅ Dry-run 完成！使用 --execute 参数执行实际迁移。")
    else:
        print("\n✅ 迁移完成！")
    
    return migrator


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="迁移文档文件")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行实际迁移（默认为 dry-run）"
    )
    
    args = parser.parse_args()
    
    try:
        migrate_documentation(dry_run=not args.execute)
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
