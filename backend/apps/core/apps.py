"""Core 应用配置"""

import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "核心系统"

    def ready(self) -> None:  # pragma: no cover
        from apps.core.utils.startup_db import allow_startup_db, run_startup_db_sync

        try:
            from .tasking.qcluster_shutdown import (
                patch_django_q_cluster_stop_for_macos,
                patch_django_q_sig_handler_for_finalizing,
            )
            from .tasking.qcluster_spawn import patch_django_q_mp_context_for_macos

            patch_django_q_mp_context_for_macos()
            patch_django_q_cluster_stop_for_macos()
            # 必须早于任何 q.start()（start() 会把当时的 sig_handler 绑进 signal.signal）
            patch_django_q_sig_handler_for_finalizing()
        except Exception:
            logger.debug("django-q spawn/shutdown patch 跳过（未就绪）")

        # ninja Schema 序列化性能补丁（列表接口字段级缓存，结构不符时自动跳过）
        try:
            from .infrastructure.ninja_perf import patch_django_getter_for_perf

            patch_django_getter_for_perf()
        except Exception:
            logger.debug("ninja DjangoGetter 性能补丁跳过（未就绪）", exc_info=True)

        # 注册文件清理定时任务。
        #
        # 必须经 run_startup_db_sync 摆渡：ASGI 部署下 ready() 在事件循环线程里跑，
        # 直接查调度表抛 SynchronousOnlyOperation，被下面的 except 吞成 debug——
        # 文件清理/磁盘监控三条定时任务于是从来没注册上过。
        try:
            from .tasking.cleanup_tasks import _register_schedules

            def _register_cleanup_schedules() -> None:
                with allow_startup_db():
                    _register_schedules()

            run_startup_db_sync(_register_cleanup_schedules)
        except Exception as exc:
            # S48-31（2026-11-23 二轮审计）：原实现用 logger.debug 吞掉这里的任何异常，
            # 默认日志级别下不落盘 —— 三条定时任务（tmp 清理 / exports 清理 /
            # 磁盘监控）没注册上时，运维看到的是「某天临时文件永不清理 / 磁盘无人监控」，
            # 而不是一条告警。→ 现在升到 warning 并带 exc_info。
            # 不打异常栈：ready() 阶段无 DB 时会被 CI 的 mypy fail-closed 门禁误判为「mypy 崩了」。
            logger.warning(
                "cleanup_tasks 调度注册失败（定时任务可能未注册）: %s（%s: %s）",
                "core:cleanup_*",
                type(exc).__name__,
                exc,
            )

        # 启动期迁移健康检查（只在 DEBUG 下 WARNING，不阻断启动）。
        #
        # 三次 `column ... does not exist` 事故的共同点：迁移文件生成了、开发库
        # 没跑 migrate，而单测/CI 全绿（测试库自己建表）。CI 层有
        # `scripts/check_migrations.sh` 三道闸门，这里补最后一道：一启动就喊出来。
        if "test" not in sys.argv and "pytest" not in sys.modules:
            try:

                def _warn_migrations() -> None:
                    with allow_startup_db():
                        from .utils.migration_health import warn_if_unapplied

                        warn_if_unapplied()

                run_startup_db_sync(_warn_migrations)
            except (ImportError, RuntimeError, AttributeError, OSError):
                # 具体类型而非宽捕获：本仓有「宽异常捕获」棘轮门禁
                # （tests/ci/structure/test_exception_ratchet.py）；数据库错误已在
                # warn_if_unapplied 内部吞掉，这里只兜「模块/ASGI 未就绪」。
                logger.debug("启动期迁移健康检查跳过（未就绪）", exc_info=True)

        # 注册 post_migrate 信号,首次 migrate 后自动加载种子数据
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._on_post_migrate, sender=self)

    def _on_post_migrate(self, sender, **kwargs):  # type: ignore[no-untyped-def]
        """数据库迁移完成后自动加载种子数据(仅表为空时)."""
        if "test" in sys.argv or "pytest" in sys.modules:
            return
        try:
            from .services.seed_data_loader import load_cause_seed_data, load_court_seed_data

            load_cause_seed_data()
            load_court_seed_data()
        except Exception as e:
            logger.warning("种子数据自动加载跳过: %s", e)
