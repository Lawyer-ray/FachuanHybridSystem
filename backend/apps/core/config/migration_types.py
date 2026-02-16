"""Module for migration types."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .clock import utc_now


class MigrationStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationStep:
    name: str
    description: str
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self) -> None:
        self.status = MigrationStatus.IN_PROGRESS
        self.started_at = utc_now()
        self.error_message = None

    def complete(self) -> None:
        self.status = MigrationStatus.COMPLETED
        self.completed_at = utc_now()

    def fail(self, error_message: str) -> None:
        self.status = MigrationStatus.FAILED
        self.error_message = error_message
        self.completed_at = utc_now()


@dataclass
class MigrationLog:
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
