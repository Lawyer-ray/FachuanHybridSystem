"""
项目结构迁移工具

提供文件迁移、目录创建、删除等功能，支持 dry-run 模式和回滚机制
"""

from pathlib import Path
from typing import List, Optional
import shutil
import logging

logger = logging.getLogger(__name__)


class Migration:
    """迁移任务基类"""
    
    def execute(self, dry_run: bool = True) -> None:
        """
        执行迁移
        
        Args:
            dry_run: 是否为 dry-run 模式（只打印不执行）
        """
        raise NotImplementedError
    
    def rollback(self) -> None:
        """回滚迁移"""
        raise NotImplementedError


class MoveFileMigration(Migration):
    """文件移动迁移"""
    
    def __init__(self, source: Path, destination: Path):
        """
        初始化文件移动迁移
        
        Args:
            source: 源文件路径
            destination: 目标文件路径
        """
        self.source = source
        self.destination = destination
        self.backup_path: Optional[Path] = None
    
    def execute(self, dry_run: bool = True) -> None:
        """
        移动文件
        
        Args:
            dry_run: 是否为 dry-run 模式
        """
        if dry_run:
            print(f"[DRY RUN] Move {self.source} -> {self.destination}")
            return
        
        # 检查源文件是否存在
        if not self.source.exists():
            raise FileNotFoundError(f"源文件不存在: {self.source}")
        
        # 创建目标目录
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果目标文件已存在，先备份
        if self.destination.exists():
            self.backup_path = self.destination.with_suffix(
                self.destination.suffix + '.backup'
            )
            shutil.move(str(self.destination), str(self.backup_path))
            logger.info(f"备份已存在的文件: {self.destination} -> {self.backup_path}")
        
        # 移动文件
        shutil.move(str(self.source), str(self.destination))
        logger.info(f"文件移动成功: {self.source} -> {self.destination}")
    
    def rollback(self) -> None:
        """回滚移动"""
        if not self.destination.exists():
            logger.warning(f"目标文件不存在，无法回滚: {self.destination}")
            return
        
        # 恢复原文件
        shutil.move(str(self.destination), str(self.source))
        logger.info(f"回滚文件移动: {self.destination} -> {self.source}")
        
        # 如果有备份，恢复备份
        if self.backup_path and self.backup_path.exists():
            shutil.move(str(self.backup_path), str(self.destination))
            logger.info(f"恢复备份文件: {self.backup_path} -> {self.destination}")


class CreateDirectoryMigration(Migration):
    """目录创建迁移"""
    
    def __init__(self, path: Path):
        """
        初始化目录创建迁移
        
        Args:
            path: 要创建的目录路径
        """
        self.path = path
        self.created = False
    
    def execute(self, dry_run: bool = True) -> None:
        """
        创建目录
        
        Args:
            dry_run: 是否为 dry-run 模式
        """
        if dry_run:
            print(f"[DRY RUN] Create directory {self.path}")
            return
        
        # 如果目录已存在，标记为未创建（回滚时不删除）
        if self.path.exists():
            logger.info(f"目录已存在: {self.path}")
            self.created = False
            return
        
        # 创建目录
        self.path.mkdir(parents=True, exist_ok=True)
        self.created = True
        logger.info(f"目录创建成功: {self.path}")
    
    def rollback(self) -> None:
        """回滚创建"""
        # 只删除本次创建的空目录
        if not self.created:
            logger.info(f"目录不是本次创建，跳过删除: {self.path}")
            return
        
        if not self.path.exists():
            logger.warning(f"目录不存在，无法回滚: {self.path}")
            return
        
        # 只删除空目录
        if not any(self.path.iterdir()):
            self.path.rmdir()
            logger.info(f"回滚目录创建: {self.path}")
        else:
            logger.warning(f"目录非空，无法删除: {self.path}")


class DeleteFileMigration(Migration):
    """文件删除迁移"""
    
    def __init__(self, path: Path):
        """
        初始化文件删除迁移
        
        Args:
            path: 要删除的文件路径
        """
        self.path = path
        self.backup_path: Optional[Path] = None
    
    def execute(self, dry_run: bool = True) -> None:
        """
        删除文件
        
        Args:
            dry_run: 是否为 dry-run 模式
        """
        if dry_run:
            print(f"[DRY RUN] Delete {self.path}")
            return
        
        # 检查文件是否存在
        if not self.path.exists():
            logger.warning(f"文件不存在，无法删除: {self.path}")
            return
        
        # 备份文件
        self.backup_path = self.path.with_suffix(self.path.suffix + '.backup')
        shutil.move(str(self.path), str(self.backup_path))
        logger.info(f"文件删除成功（已备份）: {self.path} -> {self.backup_path}")
    
    def rollback(self) -> None:
        """回滚删除"""
        if not self.backup_path or not self.backup_path.exists():
            logger.warning(f"备份文件不存在，无法回滚: {self.backup_path}")
            return
        
        # 恢复文件
        shutil.move(str(self.backup_path), str(self.path))
        logger.info(f"回滚文件删除: {self.backup_path} -> {self.path}")


class StructureMigrator:
    """项目结构迁移管理器"""
    
    def __init__(self, root_path: Path):
        """
        初始化迁移管理器
        
        Args:
            root_path: 项目根目录路径
        """
        self.root_path = root_path
        self.migrations: List[Migration] = []
    
    def add_migration(self, migration: Migration) -> None:
        """
        添加迁移任务
        
        Args:
            migration: 迁移任务对象
        """
        self.migrations.append(migration)
    
    def execute(self, dry_run: bool = True) -> None:
        """
        执行所有迁移任务
        
        Args:
            dry_run: 是否为 dry-run 模式
        """
        if dry_run:
            print(f"\n{'='*60}")
            print(f"DRY RUN MODE - 以下操作不会实际执行")
            print(f"{'='*60}\n")
        
        logger.info(f"开始执行迁移，共 {len(self.migrations)} 个任务")
        
        for i, migration in enumerate(self.migrations, 1):
            try:
                if not dry_run:
                    logger.info(f"执行迁移 {i}/{len(self.migrations)}")
                migration.execute(dry_run)
            except Exception as e:
                logger.error(f"迁移执行失败: {e}")
                if not dry_run:
                    logger.info("开始回滚已执行的迁移...")
                    self.rollback(executed_count=i-1)
                raise
        
        if dry_run:
            print(f"\n{'='*60}")
            print(f"DRY RUN 完成 - 共 {len(self.migrations)} 个操作")
            print(f"{'='*60}\n")
        else:
            logger.info(f"所有迁移执行成功，共 {len(self.migrations)} 个任务")
    
    def rollback(self, executed_count: Optional[int] = None) -> None:
        """
        回滚迁移
        
        Args:
            executed_count: 已执行的迁移数量（None 表示回滚所有）
        """
        count = executed_count if executed_count is not None else len(self.migrations)
        logger.info(f"开始回滚迁移，共 {count} 个任务")
        
        # 按相反顺序回滚
        for i, migration in enumerate(reversed(self.migrations[:count]), 1):
            try:
                logger.info(f"回滚迁移 {i}/{count}")
                migration.rollback()
            except Exception as e:
                logger.error(f"回滚失败: {e}")
                # 继续回滚其他任务
        
        logger.info(f"回滚完成，共 {count} 个任务")
