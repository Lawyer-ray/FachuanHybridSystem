"""目录结构迁移工具"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class MoveFileMigration:
    """文件移动迁移"""

    def __init__(self, source: Path, destination: Path) -> None:
        self.source = source
        self.destination = destination
        self._backup_path: Path | None = None
        self._executed = False

    def execute(self, dry_run: bool = False) -> None:
        if dry_run:
            logger.info("dry-run: move %s -> %s", self.source, self.destination)
            return
        if not self.source.exists():
            raise FileNotFoundError(f"Source not found: {self.source}")
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        if self.destination.exists():
            self._backup_path = self.destination.with_suffix(self.destination.suffix + ".backup")
            shutil.copy2(self.destination, self._backup_path)
        shutil.move(str(self.source), str(self.destination))
        self._executed = True

    def rollback(self) -> None:
        if not self._executed:
            return
        if self.destination.exists():
            shutil.move(str(self.destination), str(self.source))
        if self._backup_path and self._backup_path.exists():
            shutil.move(str(self._backup_path), str(self.destination))


class CreateDirectoryMigration:
    """目录创建迁移"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._created = False
        self._already_existed = False

    def execute(self, dry_run: bool = False) -> None:
        if dry_run:
            logger.info("dry-run: mkdir %s", self.path)
            return
        if self.path.exists():
            self._already_existed = True
            return
        self.path.mkdir(parents=True, exist_ok=True)
        self._created = True

    def rollback(self) -> None:
        if not self._created or self._already_existed:
            return
        if self.path.exists() and not any(self.path.iterdir()):
            self.path.rmdir()


class DeleteFileMigration:
    """文件删除迁移"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._backup_path: Path | None = None
        self._executed = False

    def execute(self, dry_run: bool = False) -> None:
        if dry_run:
            logger.info("dry-run: delete %s", self.path)
            return
        if not self.path.exists():
            return
        self._backup_path = self.path.with_suffix(self.path.suffix + ".backup")
        shutil.copy2(self.path, self._backup_path)
        self.path.unlink()
        self._executed = True

    def rollback(self) -> None:
        if not self._executed or self._backup_path is None:
            return
        if self._backup_path.exists():
            shutil.move(str(self._backup_path), str(self.path))


class StructureMigrator:
    """结构迁移管理器"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.migrations: list[MoveFileMigration | CreateDirectoryMigration | DeleteFileMigration] = []

    def add_migration(self, migration: MoveFileMigration | CreateDirectoryMigration | DeleteFileMigration) -> None:
        self.migrations.append(migration)

    def execute(self, dry_run: bool = False) -> None:
        executed: list[MoveFileMigration | CreateDirectoryMigration | DeleteFileMigration] = []
        try:
            for migration in self.migrations:
                migration.execute(dry_run=dry_run)
                if not dry_run:
                    executed.append(migration)
        except Exception:
            logger.exception("Migration failed, rolling back")
            for m in reversed(executed):
                try:
                    m.rollback()
                except Exception:
                    logger.exception("Rollback failed for %s", m)
            raise

    def rollback(self, executed_count: int | None = None) -> None:
        """回滚已执行的迁移（逆序）。

        Args:
            executed_count: 回滚的迁移数量，None 表示全部回滚。
        """
        targets = self.migrations if executed_count is None else self.migrations[:executed_count]
        for migration in reversed(targets):
            try:
                migration.rollback()
            except Exception:
                logger.exception("Rollback failed for %s", migration)
