"""
配置迁移器数据模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

__all__: list[str] = ["MigrationStatus", "MigrationStep", "MigrationLog"]


class MigrationStatus(Enum):
    """迁移状态枚举"""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationStep:
    """迁移步骤"""

    name: str
    description: str
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> None:
        """开始步骤"""
        self.status = MigrationStatus.IN_PROGRESS
        self.started_at = datetime.now()
        self.error_message = None

    def complete(self) -> None:
        """完成步骤"""
        self.status = MigrationStatus.COMPLETED
        self.completed_at = datetime.now()

    def fail(self, error_message: str) -> None:
        """失败步骤"""
        self.status = MigrationStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now()


@dataclass
class MigrationLog:
    """迁移日志"""

    migration_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    steps: list[MigrationStep] = field(default_factory=list)
    total_configs: int = 0
    migrated_configs: int = 0
    error_message: str | None = None
    rollback_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "migration_id": self.migration_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "steps": [
                {
                    "name": step.name,
                    "description": step.description,
                    "status": step.status.value,
                    "error_message": step.error_message,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                }
                for step in self.steps
            ],
            "total_configs": self.total_configs,
            "migrated_configs": self.migrated_configs,
            "error_message": self.error_message,
            "rollback_available": self.rollback_available,
        }
