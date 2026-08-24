import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_RESUME_SCHEDULE_NAME = "labor_arbitration_auto_resume"
_RESUME_SCHEDULE_FUNC = "apps.labor_arbitration.tasks.auto_resume_crawl"


class LaborArbitrationConfig(AppConfig):
    """劳动仲裁文书爬虫应用配置。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.labor_arbitration"
    verbose_name = "劳动仲裁文书爬虫"

    def ready(self) -> None:
        from apps.labor_arbitration.models.signals import register_signals

        register_signals()
        self._register_resume_schedule()

    def _register_resume_schedule(self) -> None:
        """注册自愈续爬定时任务（每 30 分钟，幂等）。

        网络中断导致爬取任务失败后，Django-Q 的 retry 会在 20 分钟后自动重试
        （最多 max_attempts 次）；本定时任务兜底长期中断——周期扫描失败/未完成的
        来源并自动触发增量续爬。
        """
        try:
            from apps.core.tasking import ScheduleQueryService

            svc = ScheduleQueryService()
            existing = svc.get_schedule_by_name(_RESUME_SCHEDULE_NAME)
            if existing is None:
                svc.create_interval_schedule(
                    func=_RESUME_SCHEDULE_FUNC,
                    name=_RESUME_SCHEDULE_NAME,
                    minutes=30,
                )
                logger.info("已注册劳动仲裁自愈续爬定时任务: %s", _RESUME_SCHEDULE_NAME)
            elif existing.func != _RESUME_SCHEDULE_FUNC:
                existing.func = _RESUME_SCHEDULE_FUNC
                existing.save(update_fields=["func"])
                logger.info("已更新自愈续爬任务 func: %s", _RESUME_SCHEDULE_FUNC)
        except Exception:
            logger.debug("劳动仲裁自愈续爬定时任务注册跳过（未就绪）")
