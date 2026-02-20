"""迁移日志导出 Mixin"""

import csv
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .exceptions import ConfigException

if TYPE_CHECKING:
    from .migration_tracker import MigrationEvent, MigrationProgress


class MigrationExportMixin:
    """负责迁移日志的导出功能"""

    def get_migration_progress(self, migration_id: str) -> "MigrationProgress | None": ...  # 由主类提供

    def get_migration_events(
        self,
        migration_id: str,
        event_types: Any = None,
        limit: int | None = None,
    ) -> "list[MigrationEvent]":
        raise NotImplementedError  # 由主类提供

    def export_migration_log(self, migration_id: str, output_file: str, format: str = "json") -> None:
        """导出迁移日志"""
        progress = self.get_migration_progress(migration_id)
        events = self.get_migration_events(migration_id)

        if not progress:
            raise ConfigException(f"找不到迁移: {migration_id}")

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        fmt = format.lower()
        if fmt == "json":
            self._export_log_json(output_file, migration_id, progress, events)
        elif fmt == "csv":
            self._export_log_csv(output_file, events)
        elif fmt == "txt":
            self._export_log_txt(output_file, migration_id, progress, events)
        else:
            raise ConfigException(f"不支持的导出格式: {format}")

    def _export_log_json(
        self,
        output_file: str,
        migration_id: str,
        progress: "MigrationProgress",
        events: "list[MigrationEvent]",
    ) -> None:
        export_data = {
            "migration_id": migration_id,
            "progress": progress.to_dict(),
            "events": [event.to_dict() for event in events],
            "export_time": datetime.now().isoformat(),
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def _export_log_csv(self, output_file: str, events: "list[MigrationEvent]") -> None:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["时间戳", "事件类型", "消息", "步骤", "配置键", "错误代码"])
            for event in events:
                writer.writerow([
                    event.timestamp.isoformat(),
                    event.event_type.value,
                    event.message,
                    event.step_name or "",
                    event.config_key or "",
                    event.error_code or "",
                ])

    def _export_log_txt(
        self,
        output_file: str,
        migration_id: str,
        progress: "MigrationProgress",
        events: "list[MigrationEvent]",
    ) -> None:
        with open(output_file, "w", encoding="utf-8") as f:
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
            f.write("\n事件日志:\n")
            for event in events:
                f.write(f"[{event.timestamp.isoformat()}] {event.event_type.value}: {event.message}\n")
                if event.step_name:
                    f.write(f"  步骤: {event.step_name}\n")
                if event.config_key:
                    f.write(f"  配置: {event.config_key}\n")
                if event.error_code:
                    f.write(f"  错误代码: {event.error_code}\n")
                f.write("\n")
