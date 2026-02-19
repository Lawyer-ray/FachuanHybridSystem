"""迁移状态跟踪器的数据模型"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


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
    details: dict[str, Any] = field(default_factory=dict)
    step_name: str | None = None
    config_key: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "migration_id": self.migration_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "details": self.details,
            "step_name": self.step_name,
            "config_key": self.config_key,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MigrationEvent":
        return cls(
            id=data["id"],
            migration_id=data["migration_id"],
            event_type=MigrationEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            message=data["message"],
            details=data.get("details", {}),
            step_name=data.get("step_name"),
            config_key=data.get("config_key"),
            error_code=data.get("error_code"),
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
    end_time: datetime | None = None
    current_step: str | None = None
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def step_progress_percentage(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100

    @property
    def config_progress_percentage(self) -> float:
        if self.total_configs == 0:
            return 0.0
        return (self.migrated_configs / self.total_configs) * 100

    @property
    def overall_progress_percentage(self) -> float:
        return (self.step_progress_percentage + self.config_progress_percentage) / 2

    @property
    def duration(self) -> timedelta | None:
        if self.end_time:
            return self.end_time - self.start_time
        return datetime.now() - self.start_time

    @property
    def is_completed(self) -> bool:
        return self.end_time is not None and self.failed_steps == 0

    @property
    def is_failed(self) -> bool:
        return self.failed_steps > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "total_configs": self.total_configs,
            "migrated_configs": self.migrated_configs,
            "failed_configs": self.failed_configs,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "current_step": self.current_step,
            "last_updated": self.last_updated.isoformat(),
            "step_progress_percentage": self.step_progress_percentage,
            "config_progress_percentage": self.config_progress_percentage,
            "overall_progress_percentage": self.overall_progress_percentage,
            "duration_seconds": self.duration.total_seconds() if self.duration else None,
            "is_completed": self.is_completed,
            "is_failed": self.is_failed,
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
    last_migration_time: datetime | None = None

    @property
    def success_rate(self) -> float:
        if self.total_migrations == 0:
            return 0.0
        return (self.successful_migrations / self.total_migrations) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_migrations": self.total_migrations,
            "successful_migrations": self.successful_migrations,
            "failed_migrations": self.failed_migrations,
            "rolled_back_migrations": self.rolled_back_migrations,
            "total_configs_migrated": self.total_configs_migrated,
            "total_events": self.total_events,
            "average_duration_seconds": self.average_duration_seconds,
            "last_migration_time": (
                self.last_migration_time.isoformat() if self.last_migration_time else None
            ),
            "success_rate": self.success_rate,
        }
