from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation"
    verbose_name = "自动化工具"
    
    def ready(self):
        """应用启动时的配置"""
        from django.contrib import admin
        from .admin.scraper.scraper_admin_site import customize_admin_index
        
        # 自定义 admin 首页，添加爬虫工具分组
        customize_admin_index(admin.site)
        
        # 导入信号处理器（确保信号被注册）
        from . import signals  # noqa: F401
        
        # 启动时自动恢复未完成的法院短信处理任务
        self._recover_court_sms_tasks()
    
    def _recover_court_sms_tasks(self):
        """启动时恢复未完成的法院短信处理任务"""
        import logging
        from django.conf import settings
        
        logger = logging.getLogger("apps.automation")
        
        # 使用统一配置管理器获取配置
        try:
            if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
                get_unified_config = getattr(settings, 'get_unified_config', None)
                if get_unified_config:
                    auto_recovery_enabled = get_unified_config('features.court_sms.auto_recovery', True)
                else:
                    # 回退到传统方式
                    court_sms_config = getattr(settings, 'COURT_SMS_PROCESSING', {})
                    auto_recovery_enabled = court_sms_config.get('AUTO_RECOVERY', True)
            else:
                # 回退到传统方式
                court_sms_config = getattr(settings, 'COURT_SMS_PROCESSING', {})
                auto_recovery_enabled = court_sms_config.get('AUTO_RECOVERY', True)
        except Exception as e:
            logger.warning(f"获取法院短信自动恢复配置失败，使用默认值: {e}")
            auto_recovery_enabled = True
        
        if not auto_recovery_enabled:
            logger.debug("法院短信任务自动恢复已禁用")
            return
        
        # 防止重复执行：检查是否已经安排过恢复任务
        if hasattr(self, '_recovery_scheduled'):
            logger.debug("法院短信任务恢复已安排，跳过重复执行")
            return
        
        # 使用 threading.Timer 延迟执行，完全避免在应用初始化时的数据库操作
        try:
            import threading
            
            logger.debug("安排延迟恢复未完成的法院短信处理任务...")
            
            # 延迟10秒执行恢复任务，确保应用完全启动
            timer = threading.Timer(10.0, _delayed_recovery_task)
            timer.daemon = True  # 设为守护线程，不阻止程序退出
            timer.start()
            
            # 标记已安排，防止重复执行
            self._recovery_scheduled = True
            logger.info("法院短信任务恢复已安排延迟执行（10秒后）")
            
        except Exception as e:
            # 恢复失败不应该影响应用启动
            logger.error(f"安排法院短信任务恢复失败: {str(e)}", exc_info=True)


def _delayed_recovery_task(*args, **kwargs):
    """延迟执行的恢复任务（使用线程定时器，避免应用初始化时的数据库查询）"""
    import logging
    from django.core.management import call_command
    
    logger = logging.getLogger("apps.automation")
    
    try:
        logger.debug("开始执行延迟的法院短信任务恢复...")
        
        # 调用管理命令进行恢复
        call_command(
            'recover_court_sms_tasks',
            '--reset',  # 重置卡住的任务
            '--max-age-hours', '24',  # 只恢复24小时内的任务
            verbosity=0  # 静默输出，减少日志
        )
        
        logger.debug("延迟的法院短信任务恢复完成")
        
    except Exception as e:
        logger.error(f"延迟的法院短信任务恢复失败: {str(e)}", exc_info=True)
