"""看门狗调度：让 `sweep_stale_jobs` 真正定时跑起来。

## 为什么需要这个模块

`sweep_stale_jobs`（看门狗）写得很完整：三种收尾动作、心跳判活、重排次数上限，
`docs` 里也讲清了每条设计取舍。但它此前**只有一个管理命令入口**
（`manage.py sweep_stale_pdf_splits`），而 Django-Q 的计划任务表里**没有任何一条
在调度它**。

后果很具体：律师的笔记本合盖、公司网络瞬断、worker 被 OOM 杀掉——任务就永远
停在 `processing`，进度条卡在某个百分比，前端只能显示「已 N 分钟无响应」，
**必须有人想起来去手工跑命令**。而文档承诺的是「恢复之后任务应该自动恢复」。

这不是锦上添花：164 页双引擎跑一次十几分钟，中途被打断的概率不低，
且重跑的代价是两次完整云端费用。

## 调度频率怎么定

每 5 分钟扫一次。判死阈值 `STALE_SECONDS = 1800`（30 分钟）决定了扫描频率的
下界——扫得太勤没有意义（任务还不够「足够久没心跳」），扫得稀疏则恢复延迟过长。

5 分钟意味着：最坏情况下任务被打断后 30 + 5 = 35 分钟自动恢复。对一份要跑
十几分钟的卷宗来说可以接受，且远好于「永远不恢复」。

## 为什么要用 `allow_startup_db`

与 `core/tasking/cleanup_tasks.py` 的注册同一处境：app ready 阶段数据库可能
还没就绪（首次 `migrate`、容器刚起）。用同一个守卫包住，未就绪时静默跳过——
下次启动会再试。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.pdf_splitting")

#: 计划任务在 Django-Q 里的名字。幂等注册靠它去重。
WATCHDOG_SCHEDULE_NAME = "pdf_split:watchdog"

#: 巡检间隔（分钟）。见模块 docstring 里与 STALE_SECONDS 的关系。
WATCHDOG_INTERVAL_MINUTES = 5

#: Django-Q 调用的入口点（无参，结果写日志即可）。
WATCHDOG_FUNC = "apps.pdf_splitting.services.recovery_schedule.run_watchdog"


def run_watchdog() -> dict[str, object]:
    """看门狗的定时入口：扫一次卡死任务并记日志。

    刻意**不抛异常**：这是后台定时任务，抛了只会让 Django-Q 记一条失败，
    对恢复毫无帮助，反而可能在 `max_attempts` 内反复重试同一个扫描。
    真正的失败信息已经由 `sweep_stale_jobs` 逐任务写进日志与 `error_message`。
    """
    from apps.pdf_splitting.services import job_recovery

    try:
        result = job_recovery.sweep_stale_jobs()
    except Exception:
        logger.exception("pdf_split_watchdog_failed")
        return {"error": "sweep_failed"}

    actions = result.get("actions") or []
    if actions:
        # 只在真处理了任务时记 warning：定时任务每 5 分钟一条 INFO 会把日志淹掉
        logger.warning("pdf_split_watchdog_acted", extra={"count": len(actions), "actions": actions})
    return result


def register_watchdog_schedule() -> None:
    """把看门狗注册进 Django-Q 计划任务（幂等）。

    与 `core/tasking/cleanup_tasks._register_schedules` 同一套路：
    已存在则跳过，不重复建、也不覆盖用户改过的间隔。
    """
    try:
        from apps.core.tasking import ScheduleQueryService

        svc = ScheduleQueryService()
        if svc.schedule_exists(WATCHDOG_SCHEDULE_NAME):
            return
        svc.create_interval_schedule(
            func=WATCHDOG_FUNC,
            name=WATCHDOG_SCHEDULE_NAME,
            minutes=WATCHDOG_INTERVAL_MINUTES,
        )
        logger.info("已注册定时任务: %s（每 %d 分钟）", WATCHDOG_SCHEDULE_NAME, WATCHDOG_INTERVAL_MINUTES)
    except Exception:
        # app ready 阶段数据库可能未就绪（首次 migrate / 容器刚起），下次启动会再试。
        #
        # S18-b-01（2026-11-23 二轮审计）：这里原为 `logger.debug`，而生产 `apps.*`
        # 的日志级别是 INFO——「看门狗没进调度表」于是在日志里一个字都没有（它才是
        # 真正吃掉异常的那一层，apps.py 外层的 except 根本轮不到）。现在提为
        # warning + exc_info：不影响「不冒泡到 ready()」的取舍，但失败必经告警面。
        logger.warning("pdf_split 看门狗调度注册跳过（数据库未就绪或调度表异常）", exc_info=True)
