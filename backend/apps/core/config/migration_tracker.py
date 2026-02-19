"""
配置迁移状态跟踪器

负责记录和跟踪配置迁移的状态和进度，生成详细的迁移日志。
"""

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from ._migration_export_mixin import MigrationExportMixin
from ._migration_models import MigrationEvent, MigrationEventType, MigrationProgress, MigrationStatistics
from ._migration_query_mixin import MigrationQueryMixin
from .exceptions import ConfigException

__all__ = [
    "MigrationStateTracker",
    "MigrationEvent",
    "MigrationEventType",
    "MigrationProgress",
    "MigrationStatistics",
]


class MigrationStateTracker(MigrationQueryMixin, MigrationExportMixin):
    """
    迁移状态跟踪器

    负责记录和跟踪配置迁移的状态、进度和事件。
    """

    def __init__(self, db_path: str | None = None, log_file: str | None = None):
        """
        初始化状态跟踪器

        Args:
            db_path: SQLite 数据库路径
            log_file: 日志文件路径
        """
        self.db_path = db_path or self._get_default_db_path()
        self.log_file = log_file or self._get_default_log_file()
        self._lock = threading.Lock()
        self._event_counter = 0

        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        if self.log_file:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # 初始化数据库
        self._init_database()

    def _get_default_db_path(self) -> str:
        """获取默认数据库路径"""
        return os.path.join(os.getcwd(), ".config_migration", "migration_tracker.db")

    def _get_default_log_file(self) -> str:
        """获取默认日志文件路径"""
        return os.path.join(os.getcwd(), ".config_migration", "migration.log")

    def _init_database(self) -> None:
        """初始化数据库"""
        with self._get_db_connection() as conn:
            # 创建事件表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_events (
                    id TEXT PRIMARY KEY,
                    migration_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    step_name TEXT,
                    config_key TEXT,
                    error_code TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 创建进度表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS migration_progress (
                    migration_id TEXT PRIMARY KEY,
                    total_steps INTEGER NOT NULL,
                    completed_steps INTEGER DEFAULT 0,
                    failed_steps INTEGER DEFAULT 0,
                    total_configs INTEGER DEFAULT 0,
                    migrated_configs INTEGER DEFAULT 0,
                    failed_configs INTEGER DEFAULT 0,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    current_step TEXT,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_migration_id ON migration_events(migration_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON migration_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON migration_events(event_type)")

            conn.commit()

    @contextmanager
    def _get_db_connection(self) -> Iterator[sqlite3.Connection]:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _generate_event_id(self) -> str:
        """生成事件ID"""
        with self._lock:
            self._event_counter += 1
            return f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._event_counter:06d}"

    def start_migration(self, migration_id: str, total_steps: int, total_configs: int = 0) -> None:
        """
        开始迁移跟踪

        Args:
            migration_id: 迁移ID
            total_steps: 总步骤数
            total_configs: 总配置数
        """
        with self._lock:
            # 记录进度
            progress = MigrationProgress(
                migration_id=migration_id,
                total_steps=total_steps,
                completed_steps=0,
                failed_steps=0,
                total_configs=total_configs,
                migrated_configs=0,
                failed_configs=0,
                start_time=datetime.now(),
            )

            self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.MIGRATION_STARTED,
                timestamp=datetime.now(),
                message=f"开始迁移 {migration_id}",
                details={"total_steps": total_steps, "total_configs": total_configs},
            )

            self._save_event(event)
            self._write_log(event)

    def complete_migration(self, migration_id: str, migrated_configs: int = 0) -> None:
        """
        完成迁移

        Args:
            migration_id: 迁移ID
            migrated_configs: 已迁移配置数
        """
        with self._lock:
            # 更新进度
            progress = self.get_migration_progress(migration_id)
            if progress:
                progress.end_time = datetime.now()
                progress.migrated_configs = migrated_configs
                progress.last_updated = datetime.now()
                self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.MIGRATION_COMPLETED,
                timestamp=datetime.now(),
                message=f"迁移 {migration_id} 完成",
                details={
                    "migrated_configs": migrated_configs,
                    "duration_seconds": progress.duration.total_seconds() if progress and progress.duration else 0,
                },
            )

            self._save_event(event)
            self._write_log(event)

    def fail_migration(self, migration_id: str, error_message: str, error_code: str | None = None) -> None:
        """
        迁移失败

        Args:
            migration_id: 迁移ID
            error_message: 错误消息
            error_code: 错误代码
        """
        with self._lock:
            # 更新进度
            progress = self.get_migration_progress(migration_id)
            if progress:
                progress.end_time = datetime.now()
                progress.last_updated = datetime.now()
                self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.MIGRATION_FAILED,
                timestamp=datetime.now(),
                message=f"迁移 {migration_id} 失败: {error_message}",
                details={
                    "error_message": error_message,
                    "duration_seconds": progress.duration.total_seconds() if progress and progress.duration else 0,
                },
                error_code=error_code,
            )

            self._save_event(event)
            self._write_log(event)

    def start_step(self, migration_id: str, step_name: str, description: str = "") -> None:
        """
        开始步骤

        Args:
            migration_id: 迁移ID
            step_name: 步骤名称
            description: 步骤描述
        """
        with self._lock:
            # 更新进度
            progress = self.get_migration_progress(migration_id)
            if progress:
                progress.current_step = step_name
                progress.last_updated = datetime.now()
                self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.STEP_STARTED,
                timestamp=datetime.now(),
                message=f"开始步骤: {step_name}",
                details={"description": description},
                step_name=step_name,
            )

            self._save_event(event)
            self._write_log(event)

    def complete_step(self, migration_id: str, step_name: str, details: dict[str, Any] | None = None) -> None:
        """
        完成步骤

        Args:
            migration_id: 迁移ID
            step_name: 步骤名称
            details: 步骤详情
        """
        with self._lock:
            # 更新进度
            progress = self.get_migration_progress(migration_id)
            if progress:
                progress.completed_steps += 1
                progress.current_step = None
                progress.last_updated = datetime.now()
                self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.STEP_COMPLETED,
                timestamp=datetime.now(),
                message=f"完成步骤: {step_name}",
                details=details or {},
                step_name=step_name,
            )

            self._save_event(event)
            self._write_log(event)

    def fail_step(self, migration_id: str, step_name: str, error_message: str, error_code: str | None = None) -> None:
        """
        步骤失败

        Args:
            migration_id: 迁移ID
            step_name: 步骤名称
            error_message: 错误消息
            error_code: 错误代码
        """
        with self._lock:
            # 更新进度
            progress = self.get_migration_progress(migration_id)
            if progress:
                progress.failed_steps += 1
                progress.current_step = None
                progress.last_updated = datetime.now()
                self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.STEP_FAILED,
                timestamp=datetime.now(),
                message=f"步骤失败: {step_name} - {error_message}",
                details={"error_message": error_message},
                step_name=step_name,
                error_code=error_code,
            )

            self._save_event(event)
            self._write_log(event)

    def record_config_migration(
        self, migration_id: str, config_key: str, old_value: Any, new_value: Any, source: str = "django"
    ) -> None:
        """
        记录配置迁移

        Args:
            migration_id: 迁移ID
            config_key: 配置键
            old_value: 旧值
            new_value: 新值
            source: 来源
        """
        with self._lock:
            # 更新进度
            progress = self.get_migration_progress(migration_id)
            if progress:
                progress.migrated_configs += 1
                progress.last_updated = datetime.now()
                self._save_progress(progress)

            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.CONFIG_MIGRATED,
                timestamp=datetime.now(),
                message=f"迁移配置: {config_key}",
                details={
                    "old_value": str(old_value)[:500],  # 限制长度
                    "new_value": str(new_value)[:500],
                    "source": source,
                },
                config_key=config_key,
            )

            self._save_event(event)
            self._write_log(event)

    def record_error(
        self,
        migration_id: str,
        error_message: str,
        error_code: str | None = None,
        step_name: str | None = None,
        config_key: str | None = None,
    ) -> None:
        """
        记录错误

        Args:
            migration_id: 迁移ID
            error_message: 错误消息
            error_code: 错误代码
            step_name: 步骤名称
            config_key: 配置键
        """
        with self._lock:
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.ERROR_OCCURRED,
                timestamp=datetime.now(),
                message=f"错误: {error_message}",
                details={"error_message": error_message},
                step_name=step_name,
                config_key=config_key,
                error_code=error_code,
            )

            self._save_event(event)
            self._write_log(event)

    def record_warning(
        self, migration_id: str, warning_message: str, step_name: str | None = None, config_key: str | None = None
    ) -> None:
        """
        记录警告

        Args:
            migration_id: 迁移ID
            warning_message: 警告消息
            step_name: 步骤名称
            config_key: 配置键
        """
        with self._lock:
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.WARNING_ISSUED,
                timestamp=datetime.now(),
                message=f"警告: {warning_message}",
                details={"warning_message": warning_message},
                step_name=step_name,
                config_key=config_key,
            )

            self._save_event(event)
            self._write_log(event)

    def _save_event(self, event: MigrationEvent) -> None:
        """保存事件到数据库"""
        with self._get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO migration_events
                (id, migration_id, event_type, timestamp, message, details,
                 step_name, config_key, error_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event.id,
                    event.migration_id,
                    event.event_type.value,
                    event.timestamp.isoformat(),
                    event.message,
                    json.dumps(event.details, ensure_ascii=False),
                    event.step_name,
                    event.config_key,
                    event.error_code,
                ),
            )
            conn.commit()

    def _save_progress(self, progress: MigrationProgress) -> None:
        """保存进度到数据库"""
        with self._get_db_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO migration_progress
                (migration_id, total_steps, completed_steps, failed_steps,
                 total_configs, migrated_configs, failed_configs,
                 start_time, end_time, current_step, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    progress.migration_id,
                    progress.total_steps,
                    progress.completed_steps,
                    progress.failed_steps,
                    progress.total_configs,
                    progress.migrated_configs,
                    progress.failed_configs,
                    progress.start_time.isoformat(),
                    progress.end_time.isoformat() if progress.end_time else None,
                    progress.current_step,
                    progress.last_updated.isoformat(),
                ),
            )
            conn.commit()

    def _write_log(self, event: MigrationEvent) -> None:
        """写入日志文件"""
        if not self.log_file:
            return

        try:
            log_entry = f"[{event.timestamp.isoformat()}] {event.event_type.value.upper()}: {event.message}"
            if event.step_name:
                log_entry += f" (步骤: {event.step_name})"
            if event.config_key:
                log_entry += f" (配置: {event.config_key})"
            if event.error_code:
                log_entry += f" (错误代码: {event.error_code})"

            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")
        except Exception:
            # 忽略日志写入错误
            pass
