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
        logger.info("tmp directory does not exist, skipping: %s", tmp_dir)
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
        logger.info("exports directory does not exist, skipping: %s", exports_dir)
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
