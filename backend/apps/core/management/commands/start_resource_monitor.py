"""Django management command."""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any

from django.core.management.base import BaseCommand

from apps.core.infrastructure import resource_monitor

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """启动资源监控服务的管理命令"""

    help: str = "Start resource monitoring service"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--interval", type=int, default=60, help="Monitoring interval in seconds (default: 60)")
        parser.add_argument("--daemon", action="store_true", help="Run as daemon process")

    def handle(self, *args: Any, **options: Any) -> None:
        interval = options["interval"]
        daemon = options["daemon"]
        self.stdout.write(self.style.SUCCESS(f"Starting resource monitor with {interval}s interval"))

        def signal_handler(signum: int, frame: Any) -> None:
            self.stdout.write(self.style.WARNING("Received shutdown signal, stopping resource monitor..."))
            resource_monitor.stop_monitoring()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        try:
            resource_monitor.start_monitoring(interval)
            if daemon:
                self.stdout.write(self.style.SUCCESS("Resource monitor started in daemon mode"))
                while True:
                    time.sleep(60)
            else:
                self.stdout.write(self.style.SUCCESS("Resource monitor started in foreground mode"))
                self.stdout.write("Press Ctrl+C to stop...")
                while True:
                    try:
                        time.sleep(60)
                        status = resource_monitor.check_resource_health()
                        if status["status"] == "critical":
                            self.stdout.write(self.style.ERROR(f"CRITICAL: {status['message']}"))
                        elif status["status"] == "warning":
                            self.stdout.write(self.style.WARNING(f"WARNING: {status['message']}"))
                        else:
                            self.stdout.write(self.style.SUCCESS(f"OK: {status['message']}"))
                        if "details" in status:
                            details = status["details"]
                            self.stdout.write(
                                f"  CPU: {details.get('cpu_percent', 'N/A'):.1f}% | Memory: {details.get('memory_percent', 'N/A'):.1f}% | Disk: {details.get('disk_percent', 'N/A'):.1f}%"
                            )
                    except KeyboardInterrupt:
                        break
        except Exception as e:
            logger.exception("操作失败")
            self.stdout.write(self.style.ERROR(f"Error starting resource monitor: {e}"))
            return
        finally:
            resource_monitor.stop_monitoring()
            self.stdout.write(self.style.SUCCESS("Resource monitor stopped"))
