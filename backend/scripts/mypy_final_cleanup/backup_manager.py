"""BackupManager - 文件备份和回滚机制"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupManager:
    """管理文件备份和回滚"""
    
    def __init__(self, backend_path: Path | None = None) -> None:
        """
        初始化BackupManager
        
        Args:
            backend_path: backend目录路径，默认为当前文件的父目录的父目录的父目录
        """
        if backend_path is None:
            # 默认路径：scripts/mypy_final_cleanup -> scripts -> backend
            self.backend_path = Path(__file__).parent.parent.parent
        else:
            self.backend_path = backend_path
        
        # 备份目录
        self.backup_root = self.backend_path / ".mypy_final_cleanup_backups"
        self.backup_root.mkdir(exist_ok=True)
        
        # 当前会话的备份目录（使用时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_backup_dir = self.backup_root / timestamp
        self.session_backup_dir.mkdir(exist_ok=True)
        
        logger.info(f"BackupManager初始化，备份目录: {self.session_backup_dir}")
    
    def backup_file(self, file_path: str) -> Path | None:
        """
        备份文件
        
        Args:
            file_path: 文件路径（相对于backend目录）
            
        Returns:
            备份文件路径，备份失败返回None
        """
        try:
            source_path = self.backend_path / file_path
            if not source_path.exists():
                logger.error(f"文件不存在，无法备份: {file_path}")
                return None
            
            # 创建备份路径，保持目录结构
            relative_path = Path(file_path)
            backup_path = self.session_backup_dir / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            shutil.copy2(source_path, backup_path)
            logger.info(f"已备份: {file_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"备份失败 {file_path}: {e}")
            return None
    
    def restore_file(self, file_path: str) -> bool:
        """
        从备份恢复文件
        
        Args:
            file_path: 文件路径（相对于backend目录）
            
        Returns:
            是否恢复成功
        """
        try:
            source_path = self.backend_path / file_path
            relative_path = Path(file_path)
            backup_path = self.session_backup_dir / relative_path
            
            if not backup_path.exists():
                logger.error(f"备份不存在，无法恢复: {file_path}")
                return False
            
            # 恢复文件
            shutil.copy2(backup_path, source_path)
            logger.info(f"已恢复: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"恢复失败 {file_path}: {e}")
            return False
    
    def restore_all(self) -> int:
        """
        恢复所有备份的文件
        
        Returns:
            成功恢复的文件数量
        """
        restored_count = 0
        
        # 遍历备份目录中的所有文件
        for backup_file in self.session_backup_dir.rglob("*"):
            if backup_file.is_file():
                # 计算相对路径
                relative_path = backup_file.relative_to(self.session_backup_dir)
                file_path = str(relative_path)
                
                if self.restore_file(file_path):
                    restored_count += 1
        
        logger.info(f"恢复完成，共恢复 {restored_count} 个文件")
        return restored_count
    
    def clear_backups(self) -> bool:
        """
        清理当前会话的备份
        
        Returns:
            是否清理成功
        """
        try:
            if self.session_backup_dir.exists():
                shutil.rmtree(self.session_backup_dir)
                logger.info(f"已清理备份: {self.session_backup_dir}")
                return True
            return False
        except Exception as e:
            logger.error(f"清理备份失败: {e}")
            return False
    
    def list_backups(self) -> list[str]:
        """
        列出当前会话备份的所有文件
        
        Returns:
            备份文件路径列表（相对于backend目录）
        """
        backup_files: list[str] = []
        
        for backup_file in self.session_backup_dir.rglob("*"):
            if backup_file.is_file():
                relative_path = backup_file.relative_to(self.session_backup_dir)
                backup_files.append(str(relative_path))
        
        return backup_files
