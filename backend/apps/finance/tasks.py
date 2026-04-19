"""Finance app定时任务.

提供LPR数据自动同步等定时任务功能.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def sync_lpr_rates() -> dict:
    """同步LPR利率数据的定时任务.

    每月20日（遇节假日顺延）从央行官网获取最新LPR数据。

    Returns:
        同步结果
    """
    logger.info("[LPRSchedule] Starting scheduled LPR sync task")

    try:
        from apps.finance.services.lpr import LPRSyncService

        service = LPRSyncService()
        result = service.sync_latest()

        logger.info(f"[LPRSchedule] LPR sync completed: {result}")
        return result

    except Exception as e:
        logger.error(f"[LPRSchedule] LPR sync failed: {e}")
        raise


def setup_lpr_sync_schedule() -> None:
    """设置LPR同步定时任务.

    在系统启动时调用，创建每月20日的定时同步任务。
    """
    from apps.core.tasking import ScheduleQueryService

    schedule_svc = ScheduleQueryService()

    # 检查是否已存在
    if schedule_svc.schedule_exists("lpr_monthly_sync"):
        logger.info("[LPRSchedule] LPR sync schedule already exists")
        return

    # 创建定时任务：每月20日 9:30 执行
    # 央行通常在每月20日9:15公布LPR
    schedule_svc.create_monthly_schedule(
        name="lpr_monthly_sync",
        func="apps.finance.tasks.sync_lpr_rates",
        next_run=datetime.now().replace(day=20, hour=9, minute=30, second=0, microsecond=0),
        repeats=-1,
    )

    logger.info("[LPRSchedule] LPR monthly sync schedule created")
