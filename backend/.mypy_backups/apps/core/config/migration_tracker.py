"""
配置迁移状态跟踪器

负责记录和跟踪配置迁移的状态和进度，生成详细的迁移日志。
"""

import os
import json
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import contextmanager

from .exceptions import ConfigException


class MigrationEventType(Enum):
    """迁移事件类型"""
    MIGRATION_STARTED = "migration_started"
    MIGRATION_COMPLETED = "migration_completed"
    MIGRATION_FAILED = "migration_failed"
    MIGRATION_ROLLED_BACK = "migration_rolled_back"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    CONFIG_MIGRATED = "config_migrated"
    CONFIG_VALIDATED = "config_validated"
    CONFIG_ROLLBACK = "config_rollback"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"
    ERROR_OCCURRED = "error_occurred"
    WARNING_ISSUED = "warning_issued"


@dataclass
class MigrationEvent:
    """迁移事件"""
    id: str
    migration_id: str
    event_type: MigrationEventType
    timestamp: datetime
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    step_name: Optional[str] = None
    config_key: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'migration_id': self.migration_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'message': self.message,
            'details': self.details,
            'step_name': self.step_name,
            'config_key': self.config_key,
            'error_code': self.error_code,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MigrationEvent':
        """从字典创建"""
        return cls(
            id=data['id'],
            migration_id=data['migration_id'],
            event_type=MigrationEventType(data['event_type']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            message=data['message'],
            details=data.get('details', {}),
            step_name=data.get('step_name'),
            config_key=data.get('config_key'),
            error_code=data.get('error_code'),
        )


@dataclass
class MigrationProgress:
    """迁移进度"""
    migration_id: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    total_configs: int
    migrated_configs: int
    failed_configs: int
    start_time: datetime
    end_time: Optional[datetime] = None
    current_step: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.now)
    
    @property
    def step_progress_percentage(self) -> float:
        """步骤进度百分比"""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100
    
    @property
    def config_progress_percentage(self) -> float:
        """配置进度百分比"""
        if self.total_configs == 0:
            return 0.0
        return (self.migrated_configs / self.total_configs) * 100
    
    @property
    def overall_progress_percentage(self) -> float:
        """总体进度百分比"""
        return (self.step_progress_percentage + self.config_progress_percentage) / 2
    
    @property
    def duration(self) -> Optional[timedelta]:
        """迁移持续时间"""
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now() - self.start_time
    
    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.end_time is not None and self.failed_steps == 0
    
    @property
    def is_failed(self) -> bool:
        """是否失败"""
        return self.failed_steps > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'migration_id': self.migration_id,
            'total_steps': self.total_steps,
            'completed_steps': self.completed_steps,
            'failed_steps': self.failed_steps,
            'total_configs': self.total_configs,
            'migrated_configs': self.migrated_configs,
            'failed_configs': self.failed_configs,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'current_step': self.current_step,
            'last_updated': self.last_updated.isoformat(),
            'step_progress_percentage': self.step_progress_percentage,
            'config_progress_percentage': self.config_progress_percentage,
            'overall_progress_percentage': self.overall_progress_percentage,
            'duration_seconds': self.duration.total_seconds() if self.duration else None,
            'is_completed': self.is_completed,
            'is_failed': self.is_failed,
        }


@dataclass
class MigrationStatistics:
    """迁移统计信息"""
    total_migrations: int = 0
    successful_migrations: int = 0
    failed_migrations: int = 0
    rolled_back_migrations: int = 0
    total_configs_migrated: int = 0
    total_events: int = 0
    average_duration_seconds: float = 0.0
    last_migration_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_migrations == 0:
            return 0.0
        return (self.successful_migrations / self.total_migrations) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_migrations': self.total_migrations,
            'successful_migrations': self.successful_migrations,
            'failed_migrations': self.failed_migrations,
            'rolled_back_migrations': self.rolled_back_migrations,
            'total_configs_migrated': self.total_configs_migrated,
            'total_events': self.total_events,
            'average_duration_seconds': self.average_duration_seconds,
            'last_migration_time': self.last_migration_time.isoformat() if self.last_migration_time else None,
            'success_rate': self.success_rate,
        }


class MigrationStateTracker:
    """
    迁移状态跟踪器
    
    负责记录和跟踪配置迁移的状态、进度和事件。
    """
    
    def __init__(self, db_path: Optional[str] = None, 
                 log_file: Optional[str] = None):
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
        return os.path.join(os.getcwd(), '.config_migration', 'migration_tracker.db')
    
    def _get_default_log_file(self) -> str:
        """获取默认日志文件路径"""
        return os.path.join(os.getcwd(), '.config_migration', 'migration.log')
    
    def _init_database(self) -> None:
        """初始化数据库"""
        with self._get_db_connection() as conn:
            # 创建事件表
            conn.execute('''
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
            ''')
            
            # 创建进度表
            conn.execute('''
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
            ''')
            
            # 创建索引
            conn.execute('CREATE INDEX IF NOT EXISTS idx_events_migration_id ON migration_events(migration_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON migration_events(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON migration_events(event_type)')
            
            conn.commit()
    
    @contextmanager
    def _get_db_connection(self):
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
    
    def start_migration(self, migration_id: str, total_steps: int, 
                       total_configs: int = 0) -> None:
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
                start_time=datetime.now()
            )
            
            self._save_progress(progress)
            
            # 记录事件
            event = MigrationEvent(
                id=self._generate_event_id(),
                migration_id=migration_id,
                event_type=MigrationEventType.MIGRATION_STARTED,
                timestamp=datetime.now(),
                message=f"开始迁移 {migration_id}",
                details={
                    'total_steps': total_steps,
                    'total_configs': total_configs
                }
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def complete_migration(self, migration_id: str, 
                          migrated_configs: int = 0) -> None:
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
                    'migrated_configs': migrated_configs,
                    'duration_seconds': progress.duration.total_seconds() if progress and progress.duration else 0
                }
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def fail_migration(self, migration_id: str, error_message: str, 
                      error_code: Optional[str] = None) -> None:
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
                    'error_message': error_message,
                    'duration_seconds': progress.duration.total_seconds() if progress and progress.duration else 0
                },
                error_code=error_code
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def start_step(self, migration_id: str, step_name: str, 
                   description: str = "") -> None:
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
                details={'description': description},
                step_name=step_name
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def complete_step(self, migration_id: str, step_name: str, 
                     details: Optional[Dict[str, Any]] = None) -> None:
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
                step_name=step_name
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def fail_step(self, migration_id: str, step_name: str, 
                  error_message: str, error_code: Optional[str] = None) -> None:
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
                details={'error_message': error_message},
                step_name=step_name,
                error_code=error_code
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def record_config_migration(self, migration_id: str, config_key: str, 
                               old_value: Any, new_value: Any, 
                               source: str = "django") -> None:
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
                    'old_value': str(old_value)[:500],  # 限制长度
                    'new_value': str(new_value)[:500],
                    'source': source
                },
                config_key=config_key
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def record_error(self, migration_id: str, error_message: str, 
                    error_code: Optional[str] = None, 
                    step_name: Optional[str] = None,
                    config_key: Optional[str] = None) -> None:
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
                details={'error_message': error_message},
                step_name=step_name,
                config_key=config_key,
                error_code=error_code
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def record_warning(self, migration_id: str, warning_message: str, 
                      step_name: Optional[str] = None,
                      config_key: Optional[str] = None) -> None:
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
                details={'warning_message': warning_message},
                step_name=step_name,
                config_key=config_key
            )
            
            self._save_event(event)
            self._write_log(event)
    
    def _save_event(self, event: MigrationEvent) -> None:
        """保存事件到数据库"""
        with self._get_db_connection() as conn:
            conn.execute('''
                INSERT INTO migration_events 
                (id, migration_id, event_type, timestamp, message, details, 
                 step_name, config_key, error_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.id,
                event.migration_id,
                event.event_type.value,
                event.timestamp.isoformat(),
                event.message,
                json.dumps(event.details, ensure_ascii=False),
                event.step_name,
                event.config_key,
                event.error_code
            ))
            conn.commit()
    
    def _save_progress(self, progress: MigrationProgress) -> None:
        """保存进度到数据库"""
        with self._get_db_connection() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO migration_progress 
                (migration_id, total_steps, completed_steps, failed_steps,
                 total_configs, migrated_configs, failed_configs,
                 start_time, end_time, current_step, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
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
                progress.last_updated.isoformat()
            ))
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
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception:
            # 忽略日志写入错误
            pass
    
    def get_migration_progress(self, migration_id: str) -> Optional[MigrationProgress]:
        """
        获取迁移进度
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            Optional[MigrationProgress]: 迁移进度
        """
        with self._get_db_connection() as conn:
            row = conn.execute(
                'SELECT * FROM migration_progress WHERE migration_id = ?',
                (migration_id,)
            ).fetchone()
            
            if row:
                return MigrationProgress(
                    migration_id=row['migration_id'],
                    total_steps=row['total_steps'],
                    completed_steps=row['completed_steps'],
                    failed_steps=row['failed_steps'],
                    total_configs=row['total_configs'],
                    migrated_configs=row['migrated_configs'],
                    failed_configs=row['failed_configs'],
                    start_time=datetime.fromisoformat(row['start_time']),
                    end_time=datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
                    current_step=row['current_step'],
                    last_updated=datetime.fromisoformat(row['last_updated'])
                )
        
        return None
    
    def get_migration_events(self, migration_id: str, 
                           event_types: Optional[List[MigrationEventType]] = None,
                           limit: Optional[int] = None) -> List[MigrationEvent]:
        """
        获取迁移事件
        
        Args:
            migration_id: 迁移ID
            event_types: 事件类型过滤
            limit: 限制数量
            
        Returns:
            List[MigrationEvent]: 事件列表
        """
        with self._get_db_connection() as conn:
            query = 'SELECT * FROM migration_events WHERE migration_id = ?'
            params = [migration_id]
            
            if event_types:
                placeholders = ','.join('?' * len(event_types))
                query += f' AND event_type IN ({placeholders})'
                params.extend([et.value for et in event_types])
            
            query += ' ORDER BY timestamp DESC'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            
            events = []
            for row in rows:
                events.append(MigrationEvent(
                    id=row['id'],
                    migration_id=row['migration_id'],
                    event_type=MigrationEventType(row['event_type']),
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    message=row['message'],
                    details=json.loads(row['details']) if row['details'] else {},
                    step_name=row['step_name'],
                    config_key=row['config_key'],
                    error_code=row['error_code']
                ))
            
            return events
    
    def list_migrations(self, limit: Optional[int] = None) -> List[MigrationProgress]:
        """
        列出所有迁移
        
        Args:
            limit: 限制数量
            
        Returns:
            List[MigrationProgress]: 迁移进度列表
        """
        with self._get_db_connection() as conn:
            query = 'SELECT * FROM migration_progress ORDER BY start_time DESC'
            
            if limit:
                query += ' LIMIT ?'
                rows = conn.execute(query, (limit,)).fetchall()
            else:
                rows = conn.execute(query).fetchall()
            
            migrations = []
            for row in rows:
                migrations.append(MigrationProgress(
                    migration_id=row['migration_id'],
                    total_steps=row['total_steps'],
                    completed_steps=row['completed_steps'],
                    failed_steps=row['failed_steps'],
                    total_configs=row['total_configs'],
                    migrated_configs=row['migrated_configs'],
                    failed_configs=row['failed_configs'],
                    start_time=datetime.fromisoformat(row['start_time']),
                    end_time=datetime.fromisoformat(row['end_time']) if row['end_time'] else None,
                    current_step=row['current_step'],
                    last_updated=datetime.fromisoformat(row['last_updated'])
                ))
            
            return migrations
    
    def get_migration_statistics(self) -> MigrationStatistics:
        """
        获取迁移统计信息
        
        Returns:
            MigrationStatistics: 统计信息
        """
        with self._get_db_connection() as conn:
            # 基本统计
            stats_row = conn.execute('''
                SELECT 
                    COUNT(*) as total_migrations,
                    SUM(CASE WHEN end_time IS NOT NULL AND failed_steps = 0 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN failed_steps > 0 THEN 1 ELSE 0 END) as failed,
                    SUM(migrated_configs) as total_configs,
                    MAX(start_time) as last_migration
                FROM migration_progress
            ''').fetchone()
            
            # 回滚统计
            rollback_count = conn.execute('''
                SELECT COUNT(DISTINCT migration_id) 
                FROM migration_events 
                WHERE event_type = ?
            ''', (MigrationEventType.MIGRATION_ROLLED_BACK.value,)).fetchone()[0]
            
            # 事件统计
            event_count = conn.execute('SELECT COUNT(*) FROM migration_events').fetchone()[0]
            
            # 平均持续时间
            duration_row = conn.execute('''
                SELECT AVG(
                    CASE WHEN end_time IS NOT NULL THEN
                        (julianday(end_time) - julianday(start_time)) * 86400
                    ELSE NULL END
                ) as avg_duration
                FROM migration_progress
                WHERE end_time IS NOT NULL
            ''').fetchone()
            
            return MigrationStatistics(
                total_migrations=stats_row['total_migrations'] or 0,
                successful_migrations=stats_row['successful'] or 0,
                failed_migrations=stats_row['failed'] or 0,
                rolled_back_migrations=rollback_count or 0,
                total_configs_migrated=stats_row['total_configs'] or 0,
                total_events=event_count or 0,
                average_duration_seconds=duration_row['avg_duration'] or 0.0,
                last_migration_time=datetime.fromisoformat(stats_row['last_migration']) if stats_row['last_migration'] else None
            )
    
    def export_migration_log(self, migration_id: str, 
                           output_file: str, format: str = 'json') -> None:
        """
        导出迁移日志
        
        Args:
            migration_id: 迁移ID
            output_file: 输出文件路径
            format: 导出格式 ('json', 'csv', 'txt')
        """
        progress = self.get_migration_progress(migration_id)
        events = self.get_migration_events(migration_id)
        
        if not progress:
            raise ConfigException(f"找不到迁移: {migration_id}")
        
        # 准备导出数据
        export_data = {
            'migration_id': migration_id,
            'progress': progress.to_dict(),
            'events': [event.to_dict() for event in events],
            'export_time': datetime.now().isoformat()
        }
        
        # 确保目录存在
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        if format.lower() == 'json':
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        elif format.lower() == 'csv':
            import csv
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['时间戳', '事件类型', '消息', '步骤', '配置键', '错误代码'])
                for event in events:
                    writer.writerow([
                        event.timestamp.isoformat(),
                        event.event_type.value,
                        event.message,
                        event.step_name or '',
                        event.config_key or '',
                        event.error_code or ''
                    ])
        
        elif format.lower() == 'txt':
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"迁移日志: {migration_id}\n")
                f.write(f"导出时间: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                
                f.write("进度信息:\n")
                f.write(f"  总步骤: {progress.total_steps}\n")
                f.write(f"  已完成: {progress.completed_steps}\n")
                f.write(f"  失败: {progress.failed_steps}\n")
                f.write(f"  总配置: {progress.total_configs}\n")
                f.write(f"  已迁移: {progress.migrated_configs}\n")
                f.write(f"  开始时间: {progress.start_time.isoformat()}\n")
                if progress.end_time:
                    f.write(f"  结束时间: {progress.end_time.isoformat()}\n")
                f.write("\n")
                
                f.write("事件日志:\n")
                for event in events:
                    f.write(f"[{event.timestamp.isoformat()}] {event.event_type.value}: {event.message}\n")
                    if event.step_name:
                        f.write(f"  步骤: {event.step_name}\n")
                    if event.config_key:
                        f.write(f"  配置: {event.config_key}\n")
                    if event.error_code:
                        f.write(f"  错误代码: {event.error_code}\n")
                    f.write("\n")
        
        else:
            raise ConfigException(f"不支持的导出格式: {format}")
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """
        清理旧数据
        
        Args:
            days: 保留天数
            
        Returns:
            int: 清理的记录数
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self._get_db_connection() as conn:
            # 获取要删除的迁移ID
            migration_ids = conn.execute('''
                SELECT migration_id FROM migration_progress 
                WHERE start_time < ?
            ''', (cutoff_date.isoformat(),)).fetchall()
            
            if not migration_ids:
                return 0
            
            migration_id_list = [row['migration_id'] for row in migration_ids]
            placeholders = ','.join('?' * len(migration_id_list))
            
            # 删除事件
            event_count = conn.execute(f'''
                DELETE FROM migration_events 
                WHERE migration_id IN ({placeholders})
            ''', migration_id_list).rowcount
            
            # 删除进度
            progress_count = conn.execute(f'''
                DELETE FROM migration_progress 
                WHERE migration_id IN ({placeholders})
            ''', migration_id_list).rowcount
            
            conn.commit()
            
            return event_count + progress_count