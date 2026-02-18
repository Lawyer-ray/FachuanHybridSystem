from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation"
    verbose_name = "自动化工具"

    def ready(self) -> None:
        """应用启动时的配置"""
        from django.contrib import admin

        from .admin.scraper.scraper_admin_site import customize_admin_index

        customize_admin_index(admin.site)
        from . import signals

        self._recover_court_sms_tasks()

    def _recover_court_sms_tasks(self) -> None:
        """启动时恢复未完成的法院短信处理任务"""
        import logging

        from django.conf import settings

        logger = logging.getLogger("apps.automation")
        try:
            if getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
                get_unified_config = getattr(settings, "get_unified_config", None)
                if get_unified_config:
                    auto_recovery_enabled = get_unified_config("features.court_sms.auto_recovery", True)
                else:
                    court_sms_config = getattr(settings, "COURT_SMS_PROCESSING", {})
                    auto_recovery_enabled = court_sms_config.get("AUTO_RECOVERY", True)
            else:
                court_sms_config = getattr(settings, "COURT_SMS_PROCESSING", {})
                auto_recovery_enabled = court_sms_config.get("AUTO_RECOVERY", True)
        except Exception as e:
            logger.warning(f"获取法院短信自动恢复配置失败，使用默认值: {e}")
            auto_recovery_enabled = True
        if not auto_recovery_enabled:
            logger.debug("法院短信任务自动恢复已禁用")
            return
        if hasattr(self, "_recovery_scheduled"):
            logger.debug("法院短信任务恢复已安排，跳过重复执行")
            return
        try:
            import threading

            logger.debug("安排延迟恢复未完成的法院短信处理任务...")
            timer = threading.Timer(10.0, _delayed_recovery_task)
            timer.daemon = True
            timer.start()
            self._recovery_scheduled = True
            logger.info("法院短信任务恢复已安排延迟执行（10秒后）")
        except Exception as e:
            logger.error(f"安排法院短信任务恢复失败: {str(e)}", exc_info=True)


def _delayed_recovery_task(*args, **kwargs) -> None:
    """延迟执行的恢复任务（使用线程定时器，避免应用初始化时的数据库查询）"""
    import logging

    from django.core.management import call_command

    logger = logging.getLogger("apps.automation")
    try:
        logger.debug("开始执行延迟的法院短信任务恢复...")
        call_command("recover_court_sms_tasks", "--reset", "--max-age-hours", "24", verbosity=0)
        logger.debug("延迟的法院短信任务恢复完成")
    except Exception as e:
        logger.error(f"延迟的法院短信任务恢复失败: {str(e)}", exc_info=True)
