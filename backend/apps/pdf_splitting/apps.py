import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


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
        #
        # 必须经 run_startup_db_sync 摆渡：ASGI 部署下 ready() 在事件循环线程里跑，
        # 直接查调度表抛 SynchronousOnlyOperation，看门狗同样静默不注册。
        try:
            from apps.core.utils.startup_db import allow_startup_db, run_startup_db_sync

            from .services.recovery_schedule import register_watchdog_schedule

            def _register_watchdog() -> None:
                with allow_startup_db():
                    register_watchdog_schedule()

            run_startup_db_sync(_register_watchdog)
        except Exception as exc:
            # 启动期数据库未就绪（首次 migrate / 容器刚起）时跳过注册，下次启动再试。
            # 这里不能让异常冒出 ready()：那会让整个 app 加载失败，比没有看门狗严重得多。
            #
            # S18-b-01（2026-11-23 二轮审计）：原来这里是 `logger.debug`，而生产
            # `apps.*` 的日志级别是 INFO（apps/core/infrastructure/logging.py），于是
            # 「看门狗没注册」这件事在日志里一个字都看不到——`sweep_stale_jobs` 三年
            # 不跑也没人知道。现在提到 warning + exc_info：既保留「不让异常冒出
            # ready()」，又让失败必经日志/WARNING 告警面，可与「已注册定时任务
            # pdf_split:watchdog」那条 info 成对核对。
            # 不打异常栈（刻意不用 exc_info=True）：本函数在 `ready()` 里跑，任何「没有数据库」的
            # django.setup() 都会走到这里（CI 的 mypy 全量扫描 / 只读诊断命令 / 容器初始化早期）。
            # exc_info 会向 stderr 打 `Traceback (most recent call last)`，而 CI 的 mypy
            # fail-closed 门禁正是 grep 这个字样判「mypy 崩了」→ 误判为红（2026-11-23 实测）。
            # 异常类型+消息内联成一行，诊断信息不丢、也不污染子进程输出。
            logger.warning(
                "pdf_split 看门狗调度注册跳过（数据库未就绪或调度表异常）: %s",
                type(exc).__name__,
            )
