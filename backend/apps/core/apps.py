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
        self._patch_django_q_mp_context_for_macos()

        # 恢复因 runserver auto-reload 中断的 OAuth device code 轮询
        try:
            from .cloud_storage.admin import resume_pending_device_code_polls

            resume_pending_device_code_polls()
        except Exception:
            # 数据库未就绪（如 migrate 阶段）时静默跳过
            logger.debug("跳过 device code 恢复（数据库可能未就绪）")

        # 注册文件清理定时任务
        try:
            from .tasking.cleanup_tasks import _register_schedules

            _register_schedules()
        except Exception:
            logger.debug("cleanup_tasks 调度注册跳过（未就绪）")

        # 注册 post_migrate 信号,首次 migrate 后自动加载种子数据
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._on_post_migrate, sender=self)

    @staticmethod
    def _patch_django_q_mp_context_for_macos() -> None:
        """macOS 上将 django-q 子进程创建方式从 fork 切换为 spawn。

        django-q 的 cluster.py 硬编码 get_context("fork")，会绕过
        manage.py 里设置的全局 set_start_method("spawn")。fork 在 macOS 上
        会触发 ObjC 运行时竞态崩溃（+[NSNumber initialize] may have been
        in progress in another thread when fork() was called）。
        而 OBJC_DISABLE_INITIALIZE_FORK_SAFETY 由 libobjc 在进程启动早期
        读取，Python 运行时设置无效，因此必须直接替换 context 工厂函数。
        django-q 的 sentinel/worker/pusher/monitor 入口均自带 django.setup()，
        spawn 模式完全兼容。
        """
        if sys.platform != "darwin":
            return
        try:
            import multiprocessing

            from django_q import cluster as django_q_cluster
        except ImportError:
            logger.debug("django_q 不可用，跳过 spawn patch")
            return

        original = django_q_cluster.get_mp_context
        if getattr(original, "_fachuan_spawn_patched", False):
            return

        def _spawn_context() -> "multiprocessing.context.BaseContext":
            return multiprocessing.get_context("spawn")

        _spawn_context._fachuan_spawn_patched = True  # type: ignore[attr-defined]
        django_q_cluster.get_mp_context = _spawn_context
        logger.info("macOS 检测：django-q 子进程改用 spawn 启动，规避 fork ObjC 崩溃")

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
