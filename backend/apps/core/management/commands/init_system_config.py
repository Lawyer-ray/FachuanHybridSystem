"""
初始化系统配置命令

用于初始化系统配置项并可选地从环境变量同步配置。
"""

import os
from typing import Any

from django.core.management.base import BaseCommand

from apps.core.models import SystemConfig


class Command(BaseCommand):
    help = "初始化系统配置项"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--sync-env",
            action="store_true",
            help="同时从环境变量同步配置值",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="强制覆盖已存在的配置",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="清理已废弃的配置项（不在默认列表中的 key）",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        sync_env = options["sync_env"]
        force = options["force"]
        cleanup = options["cleanup"]

        self.stdout.write("开始初始化系统配置...")

        from apps.core.admin._system_config_data import get_default_configs

        defaults = get_default_configs()
        default_keys = {c["key"] for c in defaults}

        created_count = 0
        updated_count = 0

        for config in defaults:
            key = config["key"]

            env_value = None
            if sync_env:
                env_value = os.environ.get(key)

            value = env_value if env_value else config.get("value", "")

            if force:
                obj, created = SystemConfig.objects.update_or_create(
                    key=key,
                    defaults={
                        "value": value,
                        "category": config["category"],
                        "description": config["description"],
                        "is_secret": config.get("is_secret", False),
                    },
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"  创建: {key}")
                else:
                    updated_count += 1
                    self.stdout.write(f"  更新: {key}")
            else:
                obj, created = SystemConfig.objects.get_or_create(
                    key=key,
                    defaults={
                        "value": value,
                        "category": config["category"],
                        "description": config["description"],
                        "is_secret": config.get("is_secret", False),
                    },
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"  创建: {key}")
                else:
                    self.stdout.write(f"  跳过（已存在）: {key}")

        # 清理废弃配置
        removed_count = 0
        if cleanup:
            stale_configs: list[SystemConfig] = list(SystemConfig.objects.exclude(key__in=default_keys))
            for config in stale_configs:  # type: ignore[assignment]
                self.stdout.write(f"  清理废弃配置: {config.key}")  # type: ignore[attr-defined]
                config.delete()  # type: ignore[attr-defined]
                removed_count += 1

        summary = f"\n完成！创建 {created_count} 个，更新 {updated_count} 个"
        if removed_count:
            summary += f"，清理 {removed_count} 个废弃配置"
        self.stdout.write(self.style.SUCCESS(summary))
