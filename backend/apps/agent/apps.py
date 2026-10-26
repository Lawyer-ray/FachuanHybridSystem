"""Django app configuration."""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgentConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.agent"
    verbose_name = "Agent 运行时（pi）"

    def ready(self) -> None:
        """注册记忆相关的周期任务。

        与 ``apps/core/apps.py`` 同一模式：启动时补注册一次，用
        ``schedule_exists`` 守卫避免重复部署产生重复任务。

        为什么要现在注册：「行为推断」是记忆三条来源里唯一零成本、零幻觉的
        一条（读 ``AgentApproval`` / ``AgentRun`` 的既有审计数据），但它的
        产出只有在**定期跑**时才有意义。落地时它只是一个能被调用的函数，
        没挂 schedule 就等于不存在——这是本轮补上的缺口。

        失败只降级不阻断：调度表可能尚未 migrate，这时 app 仍要能启动。
        """
        try:
            from apps.core.utils.startup_db import allow_startup_db

            from .services.memory_tasks import _register_schedules

            with allow_startup_db():
                _register_schedules()
        except Exception:
            logger.debug("记忆定时任务注册跳过（未就绪）", exc_info=True)
