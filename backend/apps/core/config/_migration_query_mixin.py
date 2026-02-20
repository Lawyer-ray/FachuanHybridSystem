"""迁移状态查询 Mixin"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from ._migration_models import (
    MigrationEvent,
    MigrationEventType,
    MigrationProgress,
    MigrationStatistics,
)


class MigrationQueryMixin:
    """负责迁移状态的查询和统计功能"""

    db_path: str  # 由主类提供

    @contextmanager
    def _get_db_connection(self) -> Iterator[sqlite3.Connection]:
        """由主类提供"""
        ...  # pragma: no cover
        yield  # type: ignore[misc]

    def get_migration_progress(self, migration_id: str) -> MigrationProgress | None:
        with self._get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM migration_progress WHERE migration_id = ?", (migration_id,)
            ).fetchone()
            if row:
                return MigrationProgress(
                    migration_id=row["migration_id"],
                    total_steps=row["total_steps"],
                    completed_steps=row["completed_steps"],
                    failed_steps=row["failed_steps"],
                    total_configs=row["total_configs"],
                    migrated_configs=row["migrated_configs"],
                    failed_configs=row["failed_configs"],
                    start_time=datetime.fromisoformat(row["start_time"]),
                    end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
                    current_step=row["current_step"],
                    last_updated=datetime.fromisoformat(row["last_updated"]),
                )
        return None

    def get_migration_events(
        self,
        migration_id: str,
        event_types: list[MigrationEventType] | None = None,
        limit: int | None = None,
    ) -> list[MigrationEvent]:
        with self._get_db_connection() as conn:
            query = "SELECT * FROM migration_events WHERE migration_id = ?"
            params: list[str | int] = [migration_id]

            if event_types:
                placeholders = ",".join("?" * len(event_types))
                query += f" AND event_type IN ({placeholders})"
                params.extend([et.value for et in event_types])

            query += " ORDER BY timestamp DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                MigrationEvent(
                    id=row["id"],
                    migration_id=row["migration_id"],
                    event_type=MigrationEventType(row["event_type"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    message=row["message"],
                    details=json.loads(row["details"]) if row["details"] else {},
                    step_name=row["step_name"],
                    config_key=row["config_key"],
                    error_code=row["error_code"],
                )
                for row in rows
            ]

    def list_migrations(self, limit: int | None = None) -> list[MigrationProgress]:
        with self._get_db_connection() as conn:
            query = "SELECT * FROM migration_progress ORDER BY start_time DESC"
            if limit:
                rows = conn.execute(query + " LIMIT ?", (limit,)).fetchall()
            else:
                rows = conn.execute(query).fetchall()
            return [
                MigrationProgress(
                    migration_id=row["migration_id"],
                    total_steps=row["total_steps"],
                    completed_steps=row["completed_steps"],
                    failed_steps=row["failed_steps"],
                    total_configs=row["total_configs"],
                    migrated_configs=row["migrated_configs"],
                    failed_configs=row["failed_configs"],
                    start_time=datetime.fromisoformat(row["start_time"]),
                    end_time=datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
                    current_step=row["current_step"],
                    last_updated=datetime.fromisoformat(row["last_updated"]),
                )
                for row in rows
            ]

    def get_migration_statistics(self) -> MigrationStatistics:
        with self._get_db_connection() as conn:
            stats_row = conn.execute(
                """
                SELECT
                    COUNT(*) as total_migrations,
                    SUM(CASE WHEN end_time IS NOT NULL AND failed_steps = 0 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN failed_steps > 0 THEN 1 ELSE 0 END) as failed,
                    SUM(migrated_configs) as total_configs,
                    MAX(start_time) as last_migration
                FROM migration_progress
                """
            ).fetchone()

            rollback_count = conn.execute(
                "SELECT COUNT(DISTINCT migration_id) FROM migration_events WHERE event_type = ?",
                (MigrationEventType.MIGRATION_ROLLED_BACK.value,),
            ).fetchone()[0]

            event_count = conn.execute("SELECT COUNT(*) FROM migration_events").fetchone()[0]

            duration_row = conn.execute(
                """
                SELECT AVG(
                    CASE WHEN end_time IS NOT NULL THEN
                        (julianday(end_time) - julianday(start_time)) * 86400
                    ELSE NULL END
                ) as avg_duration
                FROM migration_progress WHERE end_time IS NOT NULL
                """
            ).fetchone()

            return MigrationStatistics(
                total_migrations=stats_row["total_migrations"] or 0,
                successful_migrations=stats_row["successful"] or 0,
                failed_migrations=stats_row["failed"] or 0,
                rolled_back_migrations=rollback_count or 0,
                total_configs_migrated=stats_row["total_configs"] or 0,
                total_events=event_count or 0,
                average_duration_seconds=duration_row["avg_duration"] or 0.0,
                last_migration_time=(
                    datetime.fromisoformat(stats_row["last_migration"])
                    if stats_row["last_migration"]
                    else None
                ),
            )

    def cleanup_old_data(self, days: int = 30) -> int:
        cutoff_date = datetime.now() - timedelta(days=days)
        with self._get_db_connection() as conn:
            migration_ids_rows = conn.execute(
                "SELECT migration_id FROM migration_progress WHERE start_time < ?",
                (cutoff_date.isoformat(),),
            ).fetchall()

            if not migration_ids_rows:
                return 0

            migration_id_list = [row["migration_id"] for row in migration_ids_rows]
            placeholders = ",".join("?" * len(migration_id_list))

            event_count = conn.execute(
                f"DELETE FROM migration_events WHERE migration_id IN ({placeholders})",  # nosec B608
                migration_id_list,
            ).rowcount
            progress_count = conn.execute(
                f"DELETE FROM migration_progress WHERE migration_id IN ({placeholders})",  # nosec B608
                migration_id_list,
            ).rowcount
            conn.commit()
            return event_count + progress_count
