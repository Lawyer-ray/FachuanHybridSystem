"""File cleanup tasks for temporary and export files.

Scheduled via DjangoQTaskScheduler to periodically remove stale
files from MEDIA_ROOT/tmp/ and MEDIA_ROOT/exports/.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger("apps.core.tasking.cleanup")


def cleanup_temp_files(max_age_hours: int = 24) -> dict[str, Any]:
    """Remove files older than *max_age_hours* from ``MEDIA_ROOT/tmp/``.

    Returns a summary dict with counts of removed/failed files.
    """
    media_root = Path(settings.MEDIA_ROOT)
    tmp_dir = media_root / "tmp"

    if not tmp_dir.is_dir():
        logger.debug("tmp directory does not exist, skipping: %s", tmp_dir)
        return {"removed": 0, "failed": 0, "skipped": True}

    import time

    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    failed = 0

    for entry in tmp_dir.rglob("*"):
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError:
            failed += 1

    logger.info("Cleaned tmp/: removed=%d failed=%d max_age_hours=%d", removed, failed, max_age_hours)
    return {"removed": removed, "failed": failed, "skipped": False}


def cleanup_export_files(max_age_days: int = 7) -> dict[str, Any]:
    """Remove files older than *max_age_days* from ``MEDIA_ROOT/exports/``.

    Returns a summary dict with counts of removed/failed files.
    """
    media_root = Path(settings.MEDIA_ROOT)
    exports_dir = media_root / "exports"

    if not exports_dir.is_dir():
        logger.debug("exports directory does not exist, skipping: %s", exports_dir)
        return {"removed": 0, "failed": 0, "skipped": True}

    import time

    cutoff = time.time() - max_age_days * 86400
    removed = 0
    failed = 0

    for entry in exports_dir.rglob("*"):
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError:
            failed += 1

    logger.info("Cleaned exports/: removed=%d failed=%d max_age_days=%d", removed, failed, max_age_days)
    return {"removed": removed, "failed": failed, "skipped": False}


def check_disk_space(warning_pct: float = 85.0, critical_pct: float = 95.0) -> dict[str, Any]:
    """Check disk usage of the volume containing MEDIA_ROOT.

    Returns a dict with usage info and status ('ok', 'warning', 'critical').
    """
    warning_pct = float(warning_pct) if warning_pct else 85.0
    critical_pct = float(critical_pct) if critical_pct else 95.0
    media_root = str(settings.MEDIA_ROOT)

    try:
        stat = os.statvfs(media_root)
    except OSError:
        logger.error("Cannot statvfs %s", media_root)
        return {"status": "error", "path": media_root}

    total = stat.f_blocks * stat.f_frsize
    available = stat.f_bavail * stat.f_frsize
    used_pct = ((total - available) / total) * 100 if total > 0 else 0

    if used_pct >= critical_pct:
        status = "critical"
        logger.critical("Disk usage %.1f%% >= %.1f%%: %s", used_pct, critical_pct, media_root)
    elif used_pct >= warning_pct:
        status = "warning"
        logger.warning("Disk usage %.1f%% >= %.1f%%: %s", used_pct, warning_pct, media_root)
    else:
        status = "ok"

    return {
        "status": status,
        "used_pct": round(used_pct, 1),
        "total_gb": round(total / (1024**3), 2),
        "available_gb": round(available / (1024**3), 2),
        "path": media_root,
    }


# ---------------------------------------------------------------------------
# 定时任务调度注册
# ---------------------------------------------------------------------------


def _register_schedules() -> None:
    """注册文件清理和磁盘监控定时任务。

    S20-04（2026-11-23 二轮审计）：原实现把三条注册包在**一个** try 里，任一条
    （尤其第一条）抛错就静默丢弃其余两条，且只留一行 ``logger.debug``（默认日志
    级别不落盘）——结果是三条定时任务消失而无人知道。现在逐条隔离：单条失败只
    记 warning 并继续下一条，末尾把未注册清单再喊一次。
    """
    from apps.core.tasking import ScheduleQueryService

    svc = ScheduleQueryService()
    schedules = [
        ("apps.core.tasking.cleanup_tasks.cleanup_temp_files", "core:cleanup_temp_files", 60),
        ("apps.core.tasking.cleanup_tasks.cleanup_export_files", "core:cleanup_export_files", 1440),
        ("apps.core.tasking.cleanup_tasks.check_disk_space", "core:check_disk_space", 60),
    ]
    unregistered: list[str] = []
    for func, name, minutes in schedules:
        try:
            if not svc.schedule_exists(name):
                svc.create_interval_schedule(func=func, name=name, minutes=minutes)
                logger.info("已注册定时任务: %s", name)
        except Exception:
            logger.warning("定时任务注册失败: %s（继续注册其余任务）", name, exc_info=True)
            unregistered.append(name)

    if unregistered:
        logger.warning("定时任务未注册（磁盘/tmp 将无人清理）: %s", ", ".join(unregistered))
