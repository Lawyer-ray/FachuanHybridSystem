from django.apps import AppConfig


class PdfSplittingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pdf_splitting"
    verbose_name = "PDF 拆解"

    def ready(self) -> None:
        from . import signals

        # 看门狗调度注册：让 sweep_stale_jobs 真正定时跑起来。
        #
        # 这一步此前是缺失的 —— 看门狗函数与管理命令都写好了，但 Django-Q 的
        # 计划任务表里没有任何一条在调度它，于是「断网/合盖/worker 被杀后任务
        # 自动恢复」这个承诺实际上没兑现，只能人工跑命令。
        # 详见 services/recovery_schedule.py 的模块 docstring。
        try:
            from apps.core.utils.startup_db import allow_startup_db

            from .services.recovery_schedule import register_watchdog_schedule

            with allow_startup_db():
                register_watchdog_schedule()
        except Exception:
            # 启动期数据库未就绪（首次 migrate / 容器刚起）时静默跳过，下次启动再试。
            # 这里不能让异常冒出 ready()：那会让整个 app 加载失败，比没有看门狗严重得多。
            import logging

            logging.getLogger("apps.pdf_splitting").debug("pdf_split 看门狗调度注册跳过", exc_info=True)
